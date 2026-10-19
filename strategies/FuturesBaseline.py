"""Frozen 1h long/short baseline. Research candidate, no profitability claim."""
import math
from datetime import datetime, timezone
from pandas import DataFrame
from freqtrade.strategy import IStrategy
from freqtrade.persistence import Trade
from labapp import risk_gate


class FuturesBaseline(IStrategy):
    INTERFACE_VERSION=3
    timeframe='1h'
    can_short=True
    startup_candle_count=100
    process_only_new_candles=True
    stoploss=-0.02
    minimal_roi={'0':0.04}
    use_exit_signal=True
    position_adjustment_enable=False
    trailing_stop=False

    def bot_start(self, **kwargs):
        if self.config.get('dry_run') is not True or str(self.config.get('trading_mode'))!='futures':
            raise RuntimeError('Only dry-run futures is supported')
        self._seen=set()

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage,
                 entry_tag, side, **kwargs):
        return 1.0

    def bot_loop_start(self, current_time, **kwargs):
        if getattr(self.config.get('runmode'),'value',self.config.get('runmode'))=='dry_run':
            from labapp import store
            store.heartbeat('paper_engine','running','官方 Freqtrade Dry-run 主循环；实盘禁止')

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        from labapp.optimizer import BASE,validate_params
        mode=getattr(self.config.get('runmode'),'value',self.config.get('runmode'))
        version={'id':'baseline','params':self.config.get('_lab_optimizer_params',BASE),'bundle':self.config.get('_lab_optimizer_bundle')}
        if mode=='dry_run' and self.config.get('exchange',{}).get('name')=='gate':
            from labapp.optimizer import active
            version=active()
        params=validate_params(version['params']);self._optimizer_params=params;self._optimizer_version=version['id']
        dataframe['fast']=dataframe.close.rolling(params['fast']).mean()
        dataframe['slow']=dataframe.close.rolling(params['slow']).mean()
        if params['model_filter']:
            if not version['bundle']:raise RuntimeError('Verified model bundle required')
            from labapp.optimizer_inference import infer
            dataframe['_forecast'],dataframe['_predict_ok']=infer(dataframe,version['bundle'])
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['enter_long']=((dataframe.fast>dataframe.slow)&(dataframe.fast.shift(1)<=dataframe.slow.shift(1))&(dataframe.volume>0)).astype(int)
        dataframe['enter_short']=((dataframe.fast<dataframe.slow)&(dataframe.fast.shift(1)>=dataframe.slow.shift(1))&(dataframe.volume>0)).astype(int)
        p=getattr(self,'_optimizer_params',{'model_filter':False})
        if p['model_filter']:
            dataframe['enter_long']&=((dataframe['_predict_ok']==1)&(dataframe['_forecast']>p['prediction_threshold'])).astype(int)
            dataframe['enter_short']&=((dataframe['_predict_ok']==1)&(dataframe['_forecast']<-p['prediction_threshold'])).astype(int)
        dataframe['enter_tag']='version_'+getattr(self,'_optimizer_version','baseline')
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['exit_long']=(dataframe.fast<dataframe.slow).astype(int)
        dataframe['exit_short']=(dataframe.fast>dataframe.slow).astype(int)
        return dataframe

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        return risk_gate.stake(self.wallets.get_total_stake_amount(),max_stake,min_stake)

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time: datetime, entry_tag, side, **kwargs):
        mode=getattr(self.config.get('runmode'),'value',self.config.get('runmode'))
        if mode not in ('backtest','dry_run') or self.config.get('dry_run') is not True:
            return False
        if side not in ('long','short') or pair!='BTC/USDT:USDT':return False
        if not all(math.isfinite(v) and v>0 for v in (amount,rate)):return False
        closed=Trade.get_trades_proxy(is_open=False)
        records=[{'open_date':t.open_date_utc,'close_date':t.close_date_utc,
                  'profit':t.close_profit_abs or 0.0,'stake':t.stake_amount} for t in closed]
        ok,reason=risk_gate.check(float(self.config['dry_run_wallet']),
            self.wallets.get_total_stake_amount(),records,Trade.get_trades_proxy(is_open=True),
            current_time,amount*rate)
        if not ok:return False
        # Backtesting is isolated; persistent idempotency belongs only to the dry-run.
        if mode=='dry_run':
            from labapp import paper
            if self.config.get('exchange',{}).get('name')=='gate':
                from labapp.optimizer import active
                if active()['id']!=getattr(self,'_optimizer_version','baseline'):return False
            if paper.entry_blockers(side):return False
            frame,_=self.dp.get_analyzed_dataframe(pair,self.timeframe)
            if frame.empty:return False
            candle=frame.iloc[-1].date.to_pydatetime().astimezone(timezone.utc)
            if not 3600<=(current_time-candle).total_seconds()<3900:return False
            return paper.claim_entry(pair,int(candle.timestamp()),side)
        return True
