"""Official FreqUI in WEBSERVER mode only; no trading worker is created."""
import json
import os
import secrets
import sys

from labapp.store import ROOT, STATE, LOGS, init


def make_config():
    if any(k.startswith('FREQTRADE__') for k in os.environ):
        raise ValueError('Unexpected Freqtrade environment override')
    authfile = STATE/'frequi-auth.json'
    if not authfile.exists():
        fd = os.open(authfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump({'username':'localadmin','password':secrets.token_urlsafe(18),
                       'jwt_secret_key':secrets.token_hex(32)},f)
    auth = json.loads(authfile.read_text())
    c = json.loads((ROOT/'configs/paper/freqtrade.json').read_text())
    from scripts.safety import validate_config
    validate_config(c,os.environ)
    c.update({'dry_run':True,'initial_state':'stopped','force_entry_enable':False,
              'bot_name':'本地研究工作台 · 交易未启用','strategy':'NoTradeStrategy',
              'strategy_path':str(ROOT/'strategies'),
              'api_server':{'enabled':True,'listen_ip_address':os.environ.get('LAB_BIND','127.0.0.1'),
                            'listen_port':8081,'verbosity':'error','enable_openapi':False,
                            'CORS_origins':[], **auth}})
    path = STATE/'frequi-config.json'
    fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(c,f)
    return path


def main():
    init()
    config = make_config()
    from freqtrade.rpc.api_server.webserver import ApiServer
    from starlette.responses import JSONResponse
    original = ApiServer.configure_app
    def configure(self,app,config):
        original(self,app,config)
        @app.middleware('http')
        async def infrastructure_only(request,call_next):
            if request.method not in ('GET','HEAD','OPTIONS') and request.url.path not in (
                    '/api/v1/token/login','/api/v1/token/refresh','/api/v1/pair_history'):
                return JSONResponse({'detail':'当前仅系统搭建；训练、回测与交易尚未启用。'},status_code=403)
            return await call_next(request)
    ApiServer.configure_app = configure
    # Prevent private Binance operations even if a downstream component requests one.
    import ccxt
    import ccxt.async_support as async_ccxt
    for cls in (ccxt.binance,async_ccxt.binance):
        original_sign = cls.sign
        def sign(self,path,api='public',method='GET',params=None,headers=None,body=None,_fn=original_sign):
            if api != 'public' or method != 'GET':
                raise RuntimeError('Private Binance APIs disabled')
            return _fn(self,path,api,method,params or {},headers,body)
        cls.sign = sign
    from freqtrade.main import Arguments, setup_logging_pre, asyncio_setup, gc_set_threshold, set_mp_start_method
    setup_logging_pre(); asyncio_setup(); gc_set_threshold(); set_mp_start_method()
    args = Arguments(['webserver','--config',str(config),'--userdir',str(ROOT/'user_data'),
                      '--datadir',str(ROOT/'data/binance'),'--logfile',str(LOGS/'frequi.log')]).get_parsed_arg()
    return args['func'](args)


if __name__ == '__main__':
    sys.exit(main())
