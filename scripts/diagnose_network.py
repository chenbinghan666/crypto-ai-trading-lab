"""Run inside the application's WSL/container environment; public data only."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from labapp.network import probe
from labapp.store import ROOT


def main():
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(probe,[
            ('币安 U 本位合约','https://fapi.binance.com/fapi/v1/time'),
            ('币安现货公共行情','https://data-api.binance.vision/api/v3/time')]))
    result={'checked_at_utc':datetime.now(timezone.utc).isoformat(),
            'environment':'application_runtime','results':results,
            'credentials_used':False,'network_settings_changed':False}
    target=ROOT/'reports/evidence/phase2/network_diagnostics.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
