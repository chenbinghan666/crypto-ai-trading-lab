"""Read-only acceptance witness for independently running 15m workers."""
import json
import time
from labapp import store,paper,fast_experiment as exp,fast_runtime,ai_costs


def main():
    s=exp.snapshot();original=paper.status();root=exp.folder()
    checks={'both_official_workers_online':all(s['arms'][a]['online'] for a in exp.ARMS),
        'original_one_hour_account_running':original['enabled'] and original['state']=='running',
        'original_engineering_acceptance_intact':original['engineering_accepted'],
        'separate_ledgers':exp.ledger('ai')!=exp.ledger('rule') and all(exp.ledger(a)!=paper.ledger_path() for a in exp.ARMS),
        'trained_on_15m':bool(s['model'] and s['model']['timeframe']=='15m' and s['model']['horizon_minutes']==90),
        'saved_reload_verified':(root/'ready.json').exists(),
        'only_paper_experiment':s['experimental'] and not s['live_enabled'] and not s['model']['profitability_accepted']}
    for arm in exp.ARMS:
        c=json.loads((root/(arm+'-config.json')).read_text());fast_runtime.validate(c,arm)
        checks[arm+'_dry_run_no_credentials']=c['dry_run'] and not c['exchange']['key'] and not c['exchange']['secret'] and not c['api_server']['enabled']
        checks[arm+'_fixed_cost_capital_timeframe']=c['fee']==.00125 and c['dry_run_wallet']==1000 and c['timeframe']=='15m'
    result={'at':time.time(),'passed':all(checks.values()),'checks':checks,'experiment':s,
        'ai_cost_ledger':ai_costs.summary(),'codex_application_closed':'not_observed',
        'first_actual_fill_observed':any(any(o['filled']>0 for o in s['arms'][a]['orders']) for a in exp.ARMS)}
    (store.ROOT/'reports/evidence/phase3/fast-experiment-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':result['passed'],'checks':checks,'actual_fill_observed':result['first_actual_fill_observed']},ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
