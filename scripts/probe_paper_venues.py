"""Read-only public connectivity survey; never opens exchange accounts."""
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen

URLS={'binance':'https://fapi.binance.com/fapi/v1/time',
      'bybit':'https://api.bybit.com/v5/market/time',
      'okx':'https://www.okx.com/api/v5/public/time',
      'gate':'https://api.gateio.ws/api/v4/futures/usdt/contracts/BTC_USDT'}

def probe(item):
    name,url=item
    try:
        with urlopen(url,timeout=8) as r:data=json.loads(r.read(50000))
        return {'venue':name,'ok':True,'response':data}
    except Exception as exc:
        from labapp.network import explain_error
        return {'venue':name,'ok':False,'message':explain_error(exc)[2]}

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=4) as pool:
        print(json.dumps(list(pool.map(probe,URLS.items())),ensure_ascii=False,indent=2))
