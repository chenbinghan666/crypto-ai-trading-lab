"""Durable manual CPU training jobs, never promotes a model or places orders."""
import importlib.metadata
import json
import time
import uuid
from labapp import store


def init():
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS training_jobs(id TEXT PRIMARY KEY,at REAL,updated REAL,
            state TEXT,source TEXT,cancel INTEGER,stage TEXT,result TEXT,error TEXT)''')


def dependencies():
    result={}
    for name in ('freqtrade','lightgbm','scikit-learn','datasieve'):
        try:result[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:result[name]=None
    return result


def readiness():
    init();reasons=[]
    if not all(dependencies().values()):reasons.append('CPU 训练依赖未安装，请运行部署脚本。')
    with store.connect() as db:r=db.execute("SELECT * FROM services WHERE name='training'").fetchone()
    if not r or r['state']!='running' or time.time()-r['heartbeat']>30:reasons.append('独立 CPU 训练服务未就绪。')
    return {'title':'FreqAI 模型训练','ready':not reasons,'blockers':reasons,
            'description':'FreqAI + CPU LightGBM · 2 线程 · 6 小时收益预测 · 时间隔离评估 · 不自动用于交易'}


def latest():
    init()
    with store.connect() as db:r=db.execute('SELECT * FROM training_jobs ORDER BY at DESC LIMIT 1').fetchone()
    return {**dict(r),'result':json.loads(r['result']) if r['result'] else None} if r else None


def enqueue(source=None):
    init()
    reasons=readiness()['blockers']
    if reasons:raise ValueError('\n'.join(reasons))
    if source is None:
        from labapp import paper
        source='gate' if paper.status()['venue']=='gate' else 'binance_history'
    if source not in ('gate','binance_history'):raise ValueError('训练数据源无效。')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM training_jobs WHERE state IN ('queued','running')").fetchone():raise ValueError('已有训练任务，不能重复启动。')
        last=db.execute('SELECT at FROM training_jobs ORDER BY at DESC LIMIT 1').fetchone()
        if last and time.time()-last['at']<60:raise ValueError('训练启动间隔至少 60 秒。')
        identifier=uuid.uuid4().hex
        db.execute('INSERT INTO training_jobs VALUES(?,?,?,?,?,?,?,?,?)',
            (identifier,time.time(),time.time(),'queued',source,0,'排队中',None,None))
    store.event('training','info','已排队 CPU 模型训练；不调用付费 AI，不自动用于交易')
    return {'id':identifier,'message':'CPU 训练已排队，关闭页面后仍由后台执行；新模型仅作为候选保存。'}


def cancel():
    init()
    with store.connect() as db:
        db.execute("UPDATE training_jobs SET cancel=1,updated=? WHERE state IN ('queued','running')",(time.time(),))
    return {'message':'已请求停止训练；原有模型和模拟状态保留。'}


def stage(identifier,message):
    with store.connect() as db:
        db.execute("UPDATE training_jobs SET stage=?,updated=? WHERE id=? AND state='running'",(message,time.time(),identifier))


def finish(identifier,state,result=None,error=None):
    with store.connect() as db:
        db.execute("UPDATE training_jobs SET state=?,stage=?,result=?,error=?,updated=? WHERE id=? AND state='running'",
            (state,{'completed':'训练及评估完成','failed':'训练失败','interrupted':'服务中断','cancelled':'已停止'}.get(state,state),
             json.dumps(result,ensure_ascii=False) if result else None,error,time.time(),identifier))


def recover():
    init()
    with store.connect() as db:
        db.execute("UPDATE training_jobs SET state='interrupted',stage='服务中断，需手动重试',updated=? WHERE state='running' AND source IN ('gate','binance_history')",(time.time(),))
