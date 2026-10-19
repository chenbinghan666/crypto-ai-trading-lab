"""Explicit infrastructure fault injection; does not start a trading engine."""
import json
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import urlopen

import psutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from labapp.control import running_process


def status():
    with urlopen('http://127.0.0.1:8080/api/status',timeout=3) as r:return json.load(r)


def wait_until(check,seconds=45):
    deadline=time.time()+seconds
    while time.time()<deadline:
        try:
            result=check()
            if result:return result
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError('Recovery timeout')


def main():
    s=status()
    if s['mode']!='infrastructure_only' or s['paper_enabled'] or s['live_enabled']:
        raise RuntimeError('Fault test allowed only with trading disabled')
    supervisor=running_process()
    if supervisor is None:raise RuntimeError('No supervisor')
    worker=next(p for p in supervisor.children() if 'labapp.market' in p.cmdline())
    old_worker=worker.pid
    timestamp=s['market']['received_at']
    worker.kill()
    def worker_recovered():
        children=running_process().children()
        found=[p for p in children if 'labapp.market' in p.cmdline() and p.pid!=old_worker]
        fresh=status()['market']['received_at']>timestamp
        return found[0].pid if found and fresh else None
    new_worker=wait_until(worker_recovered)
    old_supervisor=supervisor.pid
    supervisor.kill()
    def supervisor_recovered():
        p=running_process()
        if p and p.pid!=old_supervisor:
            s=status()
            if s['market'] and not s['market']['stale']:
                return p.pid
    new_supervisor=wait_until(supervisor_recovered)
    after=status()
    report={'at_utc':datetime.now(timezone.utc).isoformat(),
            'worker_restart':{'before':old_worker,'after':new_worker,'passed':True},
            'supervisor_restart_by_windows_watchdog':{'before':old_supervisor,'after':new_supervisor,'passed':True},
            'persistent_candles_present':len(after['candles'])>0,
            'live_enabled':after['live_enabled'],'paper_enabled':after['paper_enabled']}
    (ROOT/'reports/evidence/phase2/recovery_test.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
