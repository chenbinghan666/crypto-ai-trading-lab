"""Read-only deployment checks; optional restart of this project's research worker."""
import argparse
import json
import time
from pathlib import Path
from urllib.request import urlopen
import psutil
from labapp import store


def get(url):
    with urlopen(url,timeout=3) as response:
        return json.load(response)


def research_processes():
    return [p for p in psutil.process_iter(['cmdline','cwd'])
            if p.info['cwd']==str(store.ROOT) and (p.info['cmdline'] or [])[-2:]==['-m','labapp.research_service']]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--test-recovery',action='store_true')
    args=parser.parse_args()
    status=get('http://127.0.0.1:8080/api/status')
    research=get('http://127.0.0.1:8082/health')
    platforms=status['platforms']
    checks={'freqtrade_installed':platforms['freqtrade']['version']=='2026.9',
            'frequi_online':platforms['freqtrade']['online'],
            'tradingagents_installed':research['version']=='0.6.0',
            'upstream_graph_compiled':research['graph_compiled'],
            'deepseek_provider':research['provider']=='deepseek',
            'research_not_running':research['research_enabled'] is False,
            'no_paid_llm_calls':research['llm_calls']==0,
            'simulation_not_running':status['paper_enabled'] is False,
            'live_disabled':status['live_enabled'] is False}
    if args.test_recovery:
        processes=research_processes()
        assert len(processes)==1, 'Expected one local research service'
        old_pid=processes[0].pid
        processes[0].kill()
        checks['research_worker_auto_restart']=False
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            time.sleep(1)
            try:
                current=research_processes()
                if current and current[0].pid!=old_pid and get('http://127.0.0.1:8082/health')['graph_compiled']:
                    checks['research_worker_auto_restart']=True
                    break
            except Exception:
                pass
    result={'checked_at':time.time(),'checks':checks,'passed':all(checks.values()),
            'codex_application_closed':'not_observed','simulation_run':False,'live_orders':False}
    target=store.ROOT/'reports/evidence/phase3/platform_acceptance.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':
    main()
