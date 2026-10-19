"""Official Freqtrade Backtesting engine, offline reference market metadata only.

No live acceptance: these market limits are declared test assumptions, never
reused by the real-time dry-run. No external network is permitted here.
"""
import hashlib
import json
import logging
import socket
import sys
from pathlib import Path
from labapp import store, risk_gate
from labapp.paper_runtime import config,PAIR,validate as validate_config


def verify_data():
    folder=store.STATE/'futures-history';manifest=json.loads((folder/'manifest.json').read_text())
    for p in manifest['products']:
        path=folder/p['name']
        if path.resolve().parent!=(folder/'futures').resolve() or hashlib.sha256(path.read_bytes()).hexdigest()!=p['sha256']:
            raise ValueError('History integrity rejected')
    return folder,manifest


def run(window='holdout',capital=1000):
    folder,manifest=verify_data()
    if window not in manifest['split']:raise ValueError('Invalid evaluation split')
    c=config(capital);validate_config(c)
    from freqtrade.enums import RunMode
    from freqtrade.configuration import Configuration
    # Configuration fills upstream defaults and path types without connecting.
    configfile=store.STATE/'backtest-config.json';configfile.write_text(json.dumps(c))
    c=Configuration({'config':[str(configfile)],'strategy':'FuturesBaseline',
          'strategy_path':str(store.ROOT/'strategies'),'datadir':str(folder),
          'user_data_dir':str(store.ROOT/'user_data'),'timerange':manifest['split'][window],
          'cache':'none','export':'none'},RunMode.BACKTEST).get_config()
    c['fee']=0.001 # Each side includes 5 bps fee + conservative 5 bps slippage allowance.
    c['enable_protections']=False
    from freqtrade.exchange import Binance
    from freqtrade.optimize.backtesting import Backtesting
    import ccxt
    exchange=Binance(c,validate=False,load_leverage_tiers=True)
    market={'id':'BTCUSDT','symbol':PAIR,'base':'BTC','quote':'USDT','settle':'USDT',
        'active':True,'spot':False,'swap':True,'future':False,'contract':True,'linear':True,
        'inverse':False,'type':'swap','contractSize':1.0,
        'precision':{'amount':0.001,'price':0.1},
        'limits':{'amount':{'min':0.001,'max':1000},'price':{'min':0.1,'max':None},
                  'cost':{'min':5.0,'max':None},'leverage':{'min':1,'max':1}},
        'maker':0.0002,'taker':0.0005,'info':{}}
    exchange._markets={PAIR:market}
    exchange._api.set_markets([market]);exchange._api_async.set_markets([market])
    exchange._last_markets_refresh=10**16
    # Backtesting may request refresh: keep only this explicit, local test fixture.
    exchange.reload_markets=lambda *a,**k:None
    original_connect=socket.socket.connect
    def blocked(*args,**kwargs):raise RuntimeError('Backtest network access blocked')
    socket.socket.connect=blocked
    try:
        bt=Backtesting(c,exchange=exchange);bt.start()
        results=bt.results['strategy']['FuturesBaseline']
        trades=results.pop('trades',[])
        summary={'window':window,'timerange':manifest['split'][window],
            'starting_balance':capital,'final_balance':results.get('final_balance'),
            'total_trades':results.get('total_trades'),'profit_total':results.get('profit_total'),
            'profit_total_abs':results.get('profit_total_abs'),'max_drawdown_account':results.get('max_drawdown_account'),
            'wins':results.get('wins'),'losses':results.get('losses'),
            'funding_fees':sum(float(t.get('funding_fees',0) or 0) for t in trades),
            'trades':trades,'engine':'Freqtrade '+__import__('freqtrade').__version__,
            'market':'Binance USD-M perpetual','pair':PAIR,'strategy':'FuturesBaseline',
            'risk_version':risk_gate.VERSION,'network_connections':0,
            'cost_per_side':0.001,'leverage':1,'rules_verified_for_live':False,
            'limitations':['历史回测，不是实时模拟或收益预测','交易规则采用离线测试假设，未验证当前交易所限制',
                          '手续费和滑点按每侧合计 0.1% 扣减；资金费率使用官方历史记录',
                          '规则基线未用 AI；当前现货研究结论不得用于历史合约回测']}
        target=store.STATE/'futures-history'/f'backtest-{window}.json'
        target.write_text(json.dumps(summary,indent=2,default=str))
        return summary
    finally:
        socket.socket.connect=original_connect
        exchange.close()


if __name__=='__main__':
    logging.basicConfig(level=logging.WARNING)
    result=run(sys.argv[1] if len(sys.argv)>1 else 'holdout',float(sys.argv[2]) if len(sys.argv)>2 else 1000)
    print(json.dumps({k:v for k,v in result.items() if k!='trades'},ensure_ascii=False))
