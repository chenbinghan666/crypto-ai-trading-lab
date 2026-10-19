"""Autonomous paper-only candidate lifecycle, immutable risk limits."""
import hashlib
import json
import math
import time
import uuid
from labapp import store

BASE={'fast':20,'slow':60,'model_filter':False,'prediction_threshold':0.0}
INTERVAL=6*3600
FRESH_HOLDOUT=7*24*3600


def validate_params(p):
    if not isinstance(p,dict) or set(p)!=set(BASE):raise ValueError('候选参数字段不合法。')
    if type(p['fast']) is not int or p['fast'] not in (10,20,30):raise ValueError('快均线超出可验证范围。')
    if type(p['slow']) is not int or p['slow'] not in (40,60,90):raise ValueError('慢均线超出可验证范围。')
    if type(p['model_filter']) is not bool:raise ValueError('模型过滤开关无效。')
    if type(p['prediction_threshold']) not in (int,float) or p['prediction_threshold'] not in (0,.002,.005):raise ValueError('预测阈值无效。')
    if not p['model_filter'] and p['prediction_threshold']!=0:raise ValueError('未启用模型时阈值须为零。')
    return dict(p)


def init():
    with store.connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS optimizer_control(id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER,
            next_due REAL,consumed_until REAL,active TEXT,pending TEXT,message TEXT,updated REAL);
        INSERT OR IGNORE INTO optimizer_control VALUES(1,0,0,0,'baseline',NULL,'自动优化尚未启用',0);
        CREATE TABLE IF NOT EXISTS optimizer_runs(id TEXT PRIMARY KEY,at REAL,state TEXT,stage TEXT,
            cancel INTEGER,research_id TEXT,result TEXT,error TEXT);
        CREATE TABLE IF NOT EXISTS optimizer_versions(id TEXT PRIMARY KEY,at REAL,params TEXT,bundle TEXT,
            parent TEXT,state TEXT,metrics TEXT,promoted REAL,trade_watermark INTEGER DEFAULT 0);
        ''')
        db.execute("INSERT OR IGNORE INTO optimizer_versions(id,at,params,parent,state) VALUES('baseline',0,?,NULL,'active')",(json.dumps(BASE),))


def active():
    init()
    with store.connect() as db:
        r=db.execute('SELECT v.* FROM optimizer_versions v JOIN optimizer_control c ON c.active=v.id').fetchone()
    return {**dict(r),'params':validate_params(json.loads(r['params'])),'bundle':json.loads(r['bundle']) if r['bundle'] else None}


def status():
    init()
    with store.connect() as db:
        c=dict(db.execute('SELECT * FROM optimizer_control WHERE id=1').fetchone())
        r=db.execute('SELECT * FROM optimizer_runs ORDER BY at DESC LIMIT 1').fetchone()
        versions=[dict(v) for v in db.execute('SELECT id,at,state,parent,promoted FROM optimizer_versions ORDER BY at DESC LIMIT 20')]
        service=db.execute("SELECT * FROM services WHERE name='optimizer'").fetchone()
    return {**c,'enabled':bool(c['enabled']),'active_version':active(),'versions':versions,
            'run':{**dict(r),'result':json.loads(r['result']) if r['result'] else None} if r else None,
            'service_ready':bool(service and service['state']=='running' and time.time()-service['heartbeat']<30),
            'interval_hours':6,'fresh_holdout_days':7,'live_enabled':False}


def configure(enabled):
    if type(enabled) is not bool:raise ValueError('自动优化开关无效。')
    init()
    from labapp import research_jobs
    research_jobs.init()
    with store.connect() as db:
        db.execute('UPDATE optimizer_control SET enabled=?,next_due=?,message=?,updated=? WHERE id=1',
            (int(enabled),time.time(), '自动优化已启用，候选通过检验后自动切换模拟版本' if enabled else '自动优化已暂停，当前策略保留',time.time()))
        if not enabled:
            db.execute("UPDATE optimizer_runs SET cancel=1 WHERE state IN ('queued','running')")
            ids=[r[0] for r in db.execute("SELECT research_id FROM optimizer_runs WHERE cancel=1 AND research_id IS NOT NULL")]
            for identifier in ids:
                db.execute("UPDATE research_jobs SET cancel=1 WHERE id=? AND state IN ('queued','running')",(identifier,))
    store.event('optimizer','info','自动优化'+('启用' if enabled else '暂停')+'；仅模拟；风险上限及实盘禁令固定')
    return {'message':'自动优化'+('已启用；按现有 API 预算执行，通过后自动切换模拟策略。' if enabled else '已暂停；当前策略与已有持仓继续由模拟引擎管理。')}


def update(identifier,stage):
    with store.connect() as db:db.execute('UPDATE optimizer_runs SET stage=? WHERE id=?',(stage,identifier))


def finish(identifier,state,result=None,error=None):
    with store.connect() as db:
        changed=db.execute('UPDATE optimizer_runs SET state=?,stage=?,result=?,error=? WHERE id=? AND state IN (\'queued\',\'running\')',
            (state,state,json.dumps(result,ensure_ascii=False) if result else None,error,identifier))
        if changed.rowcount:
            label={'rejected':'候选未通过，原版保留','accepted':'候选通过，等待空仓自动切换',
                'waiting_forward':'候选已冻结，自动等待未来验证数据','waiting_data':'等待全新最终检验数据'}.get(state,state)
            db.execute('UPDATE optimizer_control SET message=?,updated=? WHERE id=1',(error or '本轮自动优化：'+label,time.time()))


def judge(candidate,baseline,model_metrics,params):
    validate_params(params);reasons=[]
    for window in ('validation','holdout'):
        c=candidate[window];b=baseline[window]
        numbers=[c[k] for k in ('profit','drawdown','trades')]+[b[k] for k in ('profit','drawdown')]
        if not all(type(v) in (int,float) and math.isfinite(v) for v in numbers):return False,['评估数据无效']
        if c['trades']<5:reasons.append(window+' 至少需要 5 笔交易')
        if c['profit']<=0 or c['profit']<b['profit']+1:reasons.append(window+' 扣除成本后未优于原版至少 1 USDT')
        if c['drawdown']>.05 or c['drawdown']>max(b['drawdown'],.005):reasons.append(window+' 回撤不满足要求')
    if params['model_filter'] and not model_metrics.get('beats_zero_baseline'):reasons.append('FreqAI 预测未优于零预测基线')
    return not reasons,reasons


def propose_version(identifier,params,bundle,metrics,consumed_until,parent):
    validate_params(params);init()
    passed,_=judge(metrics['candidate'],metrics['incumbent'],metrics['model_metrics'],params)
    if not passed or not metrics.get('passed'):raise ValueError('候选未通过独立比较，不能应用。')
    if params['model_filter'] and not bundle:raise ValueError('候选缺少已验证模型。')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        c=db.execute('SELECT * FROM optimizer_control WHERE id=1').fetchone()
        run=db.execute('SELECT * FROM optimizer_runs WHERE id=?',(identifier,)).fetchone()
        if not c['enabled'] or not run or run['cancel'] or c['active']!=parent:raise ValueError('优化已停止或基础版本变化，候选不应用。')
        db.execute('INSERT INTO optimizer_versions(id,at,params,bundle,parent,state,metrics) VALUES(?,?,?,?,?,?,?)',
            (identifier,time.time(),json.dumps(params),json.dumps(bundle) if bundle else None,parent,'pending',json.dumps(metrics)))
        db.execute('UPDATE optimizer_control SET pending=?,consumed_until=? WHERE id=1',(identifier,consumed_until))


def reconcile():
    """Promotion/rollback only when flat; a position keeps its original exit logic."""
    from labapp import paper
    s=paper.status()
    if s['venue']!='gate' or s['open_trades'] is None:return
    a=active()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        control=db.execute('SELECT * FROM optimizer_control WHERE id=1').fetchone()
        if a['id']!='baseline' and a['promoted']:
            closed=[t for t in s['trades'] if not t['is_open'] and t['id']>a['trade_watermark']]
            if len(closed)>=3 and sum(t['close_profit_abs'] or 0 for t in closed)<=-s['capital']*.01 and not s['open_trades']:
                parent=a['parent'] or 'baseline'
                db.execute("UPDATE optimizer_versions SET state='rolled_back' WHERE id=?",(a['id'],))
                db.execute("UPDATE optimizer_versions SET state='active',promoted=?,trade_watermark=? WHERE id=?",
                    (time.time(),max((t['id'] for t in s['trades']),default=0),parent))
                row=db.execute('SELECT result FROM training_jobs WHERE id=?',(a['id'],)).fetchone()
                if row and row['result']:
                    value=json.loads(row['result']);value['deployment']='rolled_back'
                    db.execute('UPDATE training_jobs SET result=? WHERE id=?',(json.dumps(value),a['id']))
                db.execute("UPDATE optimizer_control SET active=?,pending=NULL,message='模拟表现触发回退，恢复上一版本',updated=? WHERE id=1",(parent,time.time()))
                return
        if control['enabled'] and control['pending'] and not s['open_trades']:
            pending=db.execute("SELECT * FROM optimizer_versions WHERE id=? AND state='pending'",(control['pending'],)).fetchone()
            if not pending:return
            if time.time()-pending['at']>48*3600:
                db.execute("UPDATE optimizer_versions SET state='expired' WHERE id=?",(pending['id'],))
                db.execute("UPDATE optimizer_control SET pending=NULL,message='待应用候选超过 48 小时，保留原版' WHERE id=1")
                return
            validate_params(json.loads(pending['params']))
            db.execute("UPDATE optimizer_versions SET state='superseded' WHERE id=?",(control['active'],))
            watermark=max((t['id'] for t in s['trades']),default=0)
            db.execute("UPDATE optimizer_versions SET state='active',promoted=?,trade_watermark=? WHERE id=?",(time.time(),watermark,pending['id']))
            db.execute("UPDATE optimizer_control SET active=?,pending=NULL,message='候选已通过并自动切换；模拟启停状态不变',updated=? WHERE id=1",(pending['id'],time.time()))
            if json.loads(pending['params'])['model_filter']:
                row=db.execute('SELECT result FROM training_jobs WHERE id=?',(pending['id'],)).fetchone()
                if row and row['result']:
                    value=json.loads(row['result']);value['deployment']='paper_active'
                    db.execute('UPDATE training_jobs SET result=? WHERE id=?',(json.dumps(value),pending['id']))
