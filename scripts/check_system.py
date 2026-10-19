"""Read-only acceptance witness. Can run after closing Codex, never runs trading."""
import argparse
import json
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import urlopen,Request
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]


def get(path):
    with urlopen('http://127.0.0.1:8080'+path,timeout=5) as r:return json.load(r)


def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=30)
    args=p.parse_args()
    if not 1 <= args.seconds <= 3600:raise ValueError('seconds must be 1..3600')
    before=get('/api/status')
    time.sleep(args.seconds)
    after=get('/api/status')
    tests={
        'market_updates_without_client_session':after['market']['received_at']>before['market']['received_at'],
        'quote_is_fresh':not after['market']['stale'],
        'all_services_healthy':all(s['state']=='running' for s in after['services'] if s['name'] not in ('paper_engine','fast_ai','fast_rule')) and {'supervisor','market','dashboard','frequi','research','paper','training','optimizer','fast_manager'}<={s['name'] for s in after['services']},
        'paper_disabled':after['paper_enabled'] is False,
        'live_disabled':after['live_enabled'] is False,
        'candles_unique':len({(c['symbol'],c['timeframe'],c['open_ms']) for c in after['candles']})==len(after['candles']),
    }
    for endpoint in ('start','forceenter','backtest'):
        try:
            urlopen(Request('http://127.0.0.1:8081/api/v1/'+endpoint,data=b'{}',headers={'Content-Type':'application/json'}),timeout=5)
            tests[endpoint+'_disabled']=False
        except HTTPError as e:tests[endpoint+'_disabled']=e.code==403
    result={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'observation_seconds':args.seconds,
            'tests':tests,'passed':all(tests.values()),'codex_application_closed':'not_observable_by_this_script',
            'ai_training_simulation':'not_run_as_requested'}
    target=ROOT/'reports/evidence/phase2/system_acceptance.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
