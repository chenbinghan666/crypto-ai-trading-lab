"""Strict public-only Freqtrade worker with a separate lock and ledger per arm."""
import fcntl
import json
import os
import sys
from labapp import store,fast_experiment as exp
from labapp.paper_runtime import config as base,validate as validate_base,public_only,restrict_gate_tiers


def config(arm):
    if arm not in exp.ARMS:raise ValueError('Invalid arm')
    c=base(1000,'gate');validate_base(c)
    c.update(strategy='FuturesFastExperiment',timeframe='15m',db_url='sqlite:///'+str(exp.ledger(arm)),
        bot_name='15m 独立实验 '+arm,_lab_fast_arm=arm)
    # Conservative slippage represented as additional per-side paper cost, identical in both arms.
    c['fee']=.00125
    return c


def validate(c,arm):
    if any(k.startswith('FREQTRADE__') for k in os.environ) or c!=config(arm):raise ValueError('Unsafe experiment configuration')


def main(arm):
    if not exp.state()['enabled'] or not (exp.folder()/'ready.json').exists():raise RuntimeError('Experiment not ready or enabled')
    root=exp.folder();lock=(root/(arm+'.lock')).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    c=config(arm);validate(c,arm);public_only();restrict_gate_tiers()
    path=root/(arm+'-config.json');path.write_text(json.dumps(c));path.chmod(0o600)
    from freqtrade.main import Arguments,setup_logging_pre,asyncio_setup,gc_set_threshold,set_mp_start_method
    setup_logging_pre();asyncio_setup();gc_set_threshold();set_mp_start_method()
    args=Arguments(['trade','--config',str(path),'--userdir',str(store.ROOT/'user_data'),
        '--logfile',str(store.LOGS/('fast-'+arm+'.log'))]).get_parsed_arg()
    try:return args['func'](args)
    finally:store.heartbeat('fast_'+arm,'stopped','独立实验引擎已停止，账本保留')


if __name__=='__main__':sys.exit(main(sys.argv[1]))
