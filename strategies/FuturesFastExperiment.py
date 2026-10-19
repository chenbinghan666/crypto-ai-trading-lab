"""Same 15m trend strategy in two accounts; AI arm adds a frozen model filter."""
import json
import math
from datetime import timezone
from freqtrade.persistence import Trade
from strategies.FuturesBaseline import FuturesBaseline
from labapp import risk_gate,store,fast_experiment as exp


class FuturesFastExperiment(FuturesBaseline):
    timeframe='15m'

    def bot_start(self,**kwargs):
        super().bot_start(**kwargs)
        if self.config.get('_lab_fast_arm') not in exp.ARMS or self.timeframe!='15m':raise RuntimeError('Invalid experiment')

    def bot_loop_start(self,current_time,**kwargs):
        store.heartbeat('fast_'+self.config['_lab_fast_arm'],'running','官方 Freqtrade 15m 独立虚拟账户')

    def populate_indicators(self,dataframe,metadata):
        dataframe['fast']=dataframe.close.rolling(10).mean();dataframe['slow']=dataframe.close.rolling(40).mean()
        if self.config['_lab_fast_arm']=='ai':
            from labapp.fast_model import infer
            dataframe['_forecast'],dataframe['_predict_ok']=infer(dataframe)
        return dataframe

    def populate_entry_trend(self,dataframe,metadata):
        dataframe['enter_long']=((dataframe.fast>dataframe.slow)&(dataframe.volume>0)).astype(int)
        dataframe['enter_short']=((dataframe.fast<dataframe.slow)&(dataframe.volume>0)).astype(int)
        arm=self.config['_lab_fast_arm']
        if arm=='ai':
            dataframe['enter_long']&=((dataframe._predict_ok==1)&(dataframe._forecast>.003)).astype(int)
            dataframe['enter_short']&=((dataframe._predict_ok==1)&(dataframe._forecast<-.003)).astype(int)
        dataframe['enter_tag']='experiment15m_'+arm
        if len(dataframe):
            last=dataframe.iloc[-1];direction='long' if last.enter_long else 'short' if last.enter_short else 'hold'
            forecast=float(last['_forecast']) if arm=='ai' and math.isfinite(last['_forecast']) else None
            exp.emit(arm,last.date.timestamp(),direction,forecast,'等待风控检查' if direction!='hold' else 'AI 预测未覆盖 0.30% 门槛或规则没有方向')
        return dataframe

    def confirm_trade_entry(self,pair,order_type,amount,rate,time_in_force,current_time,entry_tag,side,**kwargs):
        arm=self.config['_lab_fast_arm'];s=exp.state()
        mode=getattr(self.config.get('runmode'),'value',self.config.get('runmode'))
        if mode!='dry_run' or self.config.get('dry_run') is not True or not s['enabled']:return False
        if pair!='BTC/USDT:USDT' or side not in ('long','short') or not all(math.isfinite(v) and v>0 for v in (amount,rate)):return False
        frame,_=self.dp.get_analyzed_dataframe(pair,self.timeframe)
        if frame.empty:return False
        candle=frame.iloc[-1].date.to_pydatetime().astimezone(timezone.utc);stamp=candle.timestamp()
        ready=json.loads((exp.folder()/'ready.json').read_text())
        if stamp<ready['start_after'] or not 900<=(current_time-candle).total_seconds()<990:
            exp.emit(arm,stamp,side,None,'等待下一根实验开始后的有效收盘 K 线');return False
        closed=Trade.get_trades_proxy(is_open=False)
        records=[{'open_date':t.open_date_utc,'close_date':t.close_date_utc,'profit':t.close_profit_abs or 0.,'stake':t.stake_amount} for t in closed]
        ok,reason=risk_gate.check(1000.,self.wallets.get_total_stake_amount(),records,Trade.get_trades_proxy(is_open=True),current_time,amount*rate)
        forecast=float(frame.iloc[-1]['_forecast']) if arm=='ai' else None
        exp.emit(arm,stamp,side,forecast,reason)
        return ok and exp.claim(arm,int(stamp),side)
