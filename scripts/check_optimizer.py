"""Witness an idle optimizer restart, persisted results and no paid replay."""
import json
import time
import psutil
from labapp import store,optimizer,paper,ai_costs


def main():
    before=optimizer.status();cost=ai_costs.summary();p=paper.status()
    if not before['run'] or before['run']['state'] in ('queued','running'):
        raise RuntimeError('Wait for the active cycle to finish before restart verification')
    matches=[]
    for proc in psutil.process_iter(['pid','cmdline','cwd']):
        if (proc.info['cmdline'] and 'labapp.optimizer_service' in proc.info['cmdline']
                and proc.info['cwd']==str(store.ROOT)):matches.append(proc)
    if len(matches)!=1:raise RuntimeError('Expected one exact optimizer service')
    oldpid=matches[0].pid;matches[0].terminate()
    replacement=None;deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        for proc in psutil.process_iter(['pid','cmdline','cwd']):
            if (proc.info['pid']!=oldpid and proc.info['cmdline']
                    and 'labapp.optimizer_service' in proc.info['cmdline']
                    and proc.info['cwd']==str(store.ROOT)):replacement=proc.info['pid']
        if replacement and optimizer.status()['service_ready']:break
        time.sleep(1)
    after=optimizer.status();a=ai_costs.summary();q=paper.status()
    tests={'independent_service_restarted':bool(replacement),'service_healthy':after['service_ready'],
        'switch_preserved':before['enabled']==after['enabled'],
        'active_version_preserved':before['active']==after['active'],
        'completed_cycle_preserved':before['run']==after['run'],
        'no_paid_replay':a['calls']==cost['calls'] and a['spent_cny']==cost['spent_cny'],
        'paper_not_started':p['enabled'] is False and q['enabled'] is False,
        'paper_acceptance_passes':q['engineering_accepted'],
        'real_cycle_completed':bool(before['run']['result'] and 'candidate' in before['run']['result'])}
    result={'at':time.time(),'passed':all(tests.values()),'tests':tests,
        'cycle':before['run'],'costs':a,'codex_application_closed':'not_observed',
        'real_time_paper':'not_started_user_requested_manual_start','live_enabled':False}
    path=store.ROOT/'reports/evidence/phase3/optimizer-acceptance.json'
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'tests':tests,'spent_cny':a['spent_cny']},indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
