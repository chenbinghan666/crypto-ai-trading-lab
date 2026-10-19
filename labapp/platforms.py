"""Observed deployment state, separate from whether research/trading can run."""
import importlib.metadata
import json
import time
from labapp import store


def status():
    from labapp import paper
    p=paper.status()
    with store.connect() as db:
        services={r['name']:dict(r) for r in db.execute('SELECT * FROM services')}
    def online(name):
        value=services.get(name,{})
        return value.get('state')=='running' and time.time()-value.get('heartbeat',0)<30
    try:
        version=importlib.metadata.version('freqtrade')
    except importlib.metadata.PackageNotFoundError:
        version=None
    try:
        manifest=json.loads((store.STATE/'deployment-tradingagents.json').read_text())
    except (OSError,ValueError):
        manifest={}
    return {
        'freqtrade':{'installed':version is not None,'version':version,'online':online('frequi'),
                     'mode':'dry_run' if p['enabled'] else 'webserver','trading_worker_running':p['state']=='running',
                     'note':'官方实时模拟生命周期与历史回测已接通；实际模拟状态：'+p['state']},
        'tradingagents':{'installed':bool(manifest.get('installed')),'version':manifest.get('version'),
                         'online':online('research'),'graph_compiled':bool(manifest.get('graph_compiled')),
                         'source_commit':manifest.get('source_commit'),'provider':'DeepSeek',
                         'execution_enabled':False,'checked_at':manifest.get('checked_at'),
                         'note':'手动研究及自动优化已接通费用闸门；自动候选通过独立检验后应用模拟。手动方向报告仍需批准'},
        'next_steps':['在网页查看历史回测结果','检查实时合约连接','保存研究过滤模式并手动启用模拟'],
        'live_enabled':False,'simulation_enabled':p['enabled']}
