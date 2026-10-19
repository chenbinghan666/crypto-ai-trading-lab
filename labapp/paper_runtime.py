"""Actual Freqtrade dry-run entrypoint. All private/non-GET CCXT calls blocked."""
import json
import os
import sys
import fcntl
from copy import deepcopy
from labapp import store

PAIR='BTC/USDT:USDT'


def acquire_worker_lock():
    store.STATE.mkdir(parents=True,exist_ok=True)
    lock=(store.STATE/'paper-worker.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('Another simulation worker is already running') from None
    return lock


def config(capital=1000,venue='binance'):
    if venue not in ('binance','gate'):raise ValueError('Unsupported simulation venue')
    c=json.loads((store.ROOT/'configs/paper/freqtrade.json').read_text())
    options={'defaultType':'future','fetchMarkets':{'types':['linear']},'fetchCurrencies':False}
    c.update(dry_run=True,dry_run_wallet=capital,trading_mode='futures',margin_mode='isolated',
             timeframe='1h',fee=0.0005,initial_state='running',strategy='FuturesBaseline',
             strategy_path=str(store.ROOT/'strategies'),stake_amount='unlimited',
             max_open_trades=1,force_entry_enable=False,bot_name='BTC 合约 · 仅模拟',
             db_url='sqlite:///'+str(store.STATE/'futures-paper.sqlite'),
             api_server={'enabled':False,'listen_ip_address':'127.0.0.1','listen_port':8083,
                         'username':'disabled','password':'disabled'},
             telegram={'enabled':False,'token':'','chat_id':''},
             order_types={'entry':'market','exit':'market','stoploss':'market','stoploss_on_exchange':False})
    c['entry_pricing']['use_order_book']=False;c['exit_pricing']['use_order_book']=False
    c['exchange']={'name':'binance','key':'','secret':'','enable_ws':False,
        'pair_whitelist':[PAIR],'pair_blacklist':[],
        'ccxt_config':{'enableRateLimit':True,'timeout':10000,'options':deepcopy(options)},
        'ccxt_async_config':{'enableRateLimit':True,'timeout':10000,'options':deepcopy(options)}}
    if venue=='gate':
        c['exchange']['name']='gate'
        for key in ('ccxt_config','ccxt_async_config'):
            c['exchange'][key]['options']={'defaultType':'swap','fetchMarkets':{'types':['swap']},'fetchCurrencies':False}
        c['order_types']['entry']='limit';c['order_types']['exit']='limit'
        c['entry_pricing']['use_order_book']=True;c['exit_pricing']['use_order_book']=True
        c['fee']=0.00075
        c['db_url']='sqlite:///'+str(store.STATE/'futures-paper-gate.sqlite')
        c['bot_name']='Gate BTC 永续 · 仅本地模拟'
    return c


def validate(c):
    if any(k.startswith('FREQTRADE__') for k in os.environ):raise ValueError('Environment overrides forbidden')
    expected=config(c.get('dry_run_wallet',0),c.get('exchange',{}).get('name'))
    for key in ('dry_run','trading_mode','margin_mode','max_open_trades','force_entry_enable',
                'strategy','timeframe','exchange','api_server','telegram','order_types','stake_amount','fee','db_url','entry_pricing','exit_pricing'):
        if c.get(key)!=expected[key]:raise ValueError('Unsafe dry-run configuration: '+key)
    capital=c.get('dry_run_wallet')
    if type(capital) not in (int,float) or not 10<=capital<=1_000_000:raise ValueError('Invalid virtual capital')


def public_only():
    import ccxt
    import ccxt.async_support as async_ccxt
    import ccxt.pro as pro
    for cls in (ccxt.binance,async_ccxt.binance,pro.binance,ccxt.gate,async_ccxt.gate,pro.gate):
        if getattr(cls.sign,'_lab_public_guard',False):continue
        original=cls.sign
        is_gate=cls.__name__=='gate'
        def sign(self,path,api='public',method='GET',params=None,headers=None,body=None,_fn=original,_gate=is_gate):
            allowed=(isinstance(api,(list,tuple)) and len(api)==2 and api[0]=='public' and api[1] in ('spot','futures')) if _gate else api in ('public','fapiPublic','fapiPublicV2','fapiPublicV3')
            if method!='GET' or not allowed:
                raise RuntimeError('Private and non-GET exchange APIs are forbidden')
            if any(getattr(self,k,None) for k in ('apiKey','secret','password')):
                raise RuntimeError('Credentials forbidden in simulation process')
            return _fn(self,path,api,method,params or {},headers,body)
        sign._lab_public_guard=True
        cls.sign=sign


def restrict_gate_tiers():
    # This application has one fixed pair; avoid hundreds of unrelated tier requests.
    from freqtrade.exchange import Gate
    def tiers(self):
        if self._config.get('dry_run') is not True or self._config['exchange']['pair_whitelist']!=[PAIR]:
            raise RuntimeError('Unexpected Gate tier request')
        return {PAIR:self._api.fetch_market_leverage_tiers(PAIR)}
    Gate.load_leverage_tiers=tiers


def main():
    # Includes direct CLI invocations: never allow two engines on the same ledger.
    lock=acquire_worker_lock()
    from labapp import paper
    state=paper.status()
    if not state['enabled']:raise RuntimeError('Simulation not authorized')
    if state['checks_stale'] or not state['checks'].get('ok') or not paper.acceptance():
        raise RuntimeError('Market or engineering checks not ready')
    c=config(state['capital'],state['venue']);validate(c);public_only();restrict_gate_tiers()
    # Trading worker serves a separate authenticated read-only official FreqUI.
    auth=json.loads((store.STATE/'frequi-auth.json').read_text())
    c['api_server'].update(enabled=True,listen_ip_address=os.environ.get('LAB_BIND','127.0.0.1'),**auth)
    from freqtrade.rpc.api_server.webserver import ApiServer
    from starlette.responses import JSONResponse
    original=ApiServer.configure_app
    def configure(self,app,config):
        original(self,app,config)
        @app.middleware('http')
        async def read_only(request,call_next):
            if request.method not in ('GET','HEAD','OPTIONS') and request.url.path not in ('/api/v1/token/login','/api/v1/token/refresh'):
                return JSONResponse({'detail':'模拟仅由本机管理页面控制；强制开仓和实盘禁止'},status_code=403)
            return await call_next(request)
    ApiServer.configure_app=configure
    path=store.STATE/'futures-paper-config.json';path.write_text(json.dumps(c));path.chmod(0o600)
    from freqtrade.main import Arguments,setup_logging_pre,asyncio_setup,gc_set_threshold,set_mp_start_method
    setup_logging_pre();asyncio_setup();gc_set_threshold();set_mp_start_method()
    args=Arguments(['trade','--config',str(path),'--userdir',str(store.ROOT/'user_data'),
                    '--logfile',str(store.LOGS/'futures-paper.log')]).get_parsed_arg()
    return args['func'](args)


if __name__=='__main__':sys.exit(main())
