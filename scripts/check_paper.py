"""Engineering acceptance, actual independent job recovery; never starts dry-run."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from labapp import store,paper


def wait_for(predicate,seconds=40):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.3)
    raise RuntimeError('Independent task did not reach expected state')


def main():
    root=store.STATE;root.mkdir(parents=True,exist_ok=True)
    result=subprocess.run([sys.executable,'-m','pytest','-q','tests/test_paper.py'],cwd=store.ROOT,
                          capture_output=True,text=True,timeout=120)
    if result.returncode:
        print(result.stdout[-4000:]);raise RuntimeError('Paper security/risk tests failed')
    tests={'risk_security_and_causality_tests':True}
    for window in ('development','validation','holdout'):
        r=json.loads((root/'futures-history'/f'backtest-{window}.json').read_text())
        tests[window+'_official_engine']=r['engine'].startswith('Freqtrade ') and r['total_trades']>0
        tests[window+'_one_x']=all(t['leverage']==1 for t in r['trades'])
        tests[window+'_funding_included']=any(abs(t.get('funding_fees',0) or 0)>0 for t in r['trades'])
        tests[window+'_no_network']=r['network_connections']==0
    with tempfile.TemporaryDirectory(prefix='paper-independent-') as temp:
        original_state=store.STATE;original_logs=store.LOGS
        store.STATE=Path(temp)/'state';store.LOGS=Path(temp)/'logs'
        store.init();paper.init()
        shutil.copytree(root/'futures-history',store.STATE/'futures-history')
        env={**os.environ,'LAB_STATE_DIR':str(store.STATE),'LAB_LOG_DIR':str(store.LOGS),
             'LAB_SECRETS_DIR':str(Path(temp)/'secrets')}
        child=None
        try:
            with store.connect() as db:
                db.execute("INSERT INTO paper_jobs(id,at,state,kind,window) VALUES('interrupted-test',?,'running','backtest','holdout')",(time.time(),))
            child=subprocess.Popen([sys.executable,'-m','labapp.paper_service'],cwd=store.ROOT,env=env,
                                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            wait_for(lambda:paper.status()['worker_ready'])
            tests['interrupted_task_not_replayed']=paper.status()['job']['state']=='interrupted'
            job=paper.enqueue('backtest','holdout')
            # No browser or chat client participates after this durable request.
            wait_for(lambda:paper.status()['job']['state'] in ('completed','failed'),90)
            s=paper.status()
            tests['independent_background_job_completed']=s['job']['state']=='completed' and s['job']['id']==job['id']
            tests['simulation_never_started']=not s['enabled'] and not (store.STATE/'futures-paper.sqlite').exists()
            child.kill();child.wait(timeout=5)
            child=subprocess.Popen([sys.executable,'-m','labapp.paper_service'],cwd=store.ROOT,env=env,
                                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            wait_for(lambda:paper.status()['job']['state']=='completed' and child.poll() is None,10)
            tests['completed_report_survives_restart']=paper.status()['job']['result']['total_trades']>0
        finally:
            if child and child.poll() is None:child.terminate();child.wait(timeout=30)
            store.STATE=original_state;store.LOGS=original_logs
    report={'at':time.time(),'passed':all(tests.values()),'tests':tests,'strategy_hash':paper.fingerprint(),
        'scope':'offline_engineering_acceptance_only','real_time_dry_run':'not_started_user_requested_manual_start' if paper.status()['venue']=='gate' else 'not_run_network_blocked',
        'codex_application_closed':'not_observed','orders_on_exchange':0,'paid_ai_calls':0,
        'strategy_profitability_approved':False}
    (root/'futures-acceptance.json').write_text(json.dumps(report,indent=2))
    target=store.ROOT/'reports/evidence/phase3/futures-acceptance.json';target.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    if not report['passed']:raise RuntimeError('Engineering acceptance failed')


if __name__=='__main__':main()
