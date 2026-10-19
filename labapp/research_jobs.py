"""Durable manually requested AI research jobs. Never produces trading orders."""
import json
import time
import uuid
from labapp import store, integrations, ai_connection, ai_costs


def init():
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS research_jobs(id TEXT PRIMARY KEY,at REAL,updated REAL,state TEXT,
                   cancel INTEGER,payload TEXT,error TEXT,result TEXT,progress INTEGER)''')


def blockers():
    init()
    reasons=[]
    validation=ai_connection.status()
    if validation.get('state')!='verified' or validation.get('verification_stale'):
        reasons.append('请在 API 配置中验证 DeepSeek 密钥和模型。')
    costs=ai_costs.summary()
    if ai_costs._dates()[1]>ai_costs.VALID_UNTIL:
        reasons.append('计费价格核验已过期，需要维护后再运行。')
    if costs['remaining_cny']<=0:
        reasons.append('本月可用预算不足。')
    if costs['daily_remaining_cny']<=0:
        reasons.append('今日 1 元研究预算已用完。')
    if validation.get('selected_model') and validation['selected_model'] not in ai_costs.PRICES:
        reasons.append('所选模型暂无核验价格，暂不能发起付费研究。')
    with store.connect() as db:
        row=db.execute("SELECT * FROM services WHERE name='research'").fetchone()
    if not row or row['state']!='running' or time.time()-row['heartbeat']>30:
        reasons.append('TradingAgents 独立研究服务未就绪。')
    return reasons


def create():
    init()
    reasons=blockers()
    if reasons:
        raise ValueError('\n'.join(reasons))
    snapshot=store.snapshot()
    if not snapshot['market'] or snapshot['market']['stale'] or len(snapshot['candles'])<20:
        raise ValueError('需要至少 20 根已收盘 K 线和未过期的公开行情，请先恢复采集。')
    closes=[r['close'] for r in snapshot['candles']]
    analysis={'count':len(closes),'return_pct':(closes[-1]/snapshot['candles'][0]['open']-1)*100,
              'high':max(r['high'] for r in snapshot['candles']),'low':min(r['low'] for r in snapshot['candles']),
              'sma20':sum(closes[-20:])/20,'volume':sum(r['volume'] for r in snapshot['candles'])}
    rows=snapshot['candles'][-24:]
    config=integrations.read()
    payload={'symbol':snapshot['settings']['symbol'],'model':config['model'],
             'credential_fingerprint':ai_connection.fingerprint(config),
             'market_type':snapshot['market'].get('market_type'),'analysis':analysis,
             'candles':[{k:r[k] for k in ('open_ms','open','high','low','close','volume')} for r in rows],
             'source':snapshot['market']['source'],'cutoff_ms':snapshot['candles'][-1]['close_ms'],
             'run_limit_cny':.5,'max_output_tokens':512,'research_only':True}
    identifier=uuid.uuid4().hex
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        active=db.execute("SELECT id FROM research_jobs WHERE state IN ('queued','running')").fetchone()
        if active:
            raise ValueError('已有研究任务正在执行，请等待完成或先停止。')
        latest=db.execute('SELECT at FROM research_jobs ORDER BY at DESC LIMIT 1').fetchone()
        if latest and time.time()-latest['at']<300:
            raise ValueError('研究冷却时间为 5 分钟，请稍后再试。')
        db.execute('INSERT INTO research_jobs VALUES(?,?,?,?,?,?,?,?,?)',
                   (identifier,time.time(),time.time(),'queued',0,json.dumps(payload),None,None,0))
    store.event('research','info','已排队手动 AI 研究；仅公开行情；单次研究上限 0.5 元；不产生订单')
    return {'id':identifier,'state':'queued','message':'AI 研究已排队，单次研究上限 0.5 元；不会产生交易订单。'}


def latest():
    init()
    with store.connect() as db:
        row=db.execute('SELECT * FROM research_jobs ORDER BY at DESC LIMIT 1').fetchone()
        if not row:
            return None
        data=dict(row)
        costs=db.execute("SELECT coalesce(sum(CASE WHEN state='settled' THEN actual_micro ELSE reserved_micro END),0) FROM ai_cost_ledger WHERE substr(request_id,1,?)=?",(len(row['id'])+1,row['id']+':')).fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_cost_ledger'").fetchone() else 0
    payload=json.loads(data.pop('payload'))
    return {**data,'result':json.loads(data['result']) if data['result'] else None,
            'symbol':payload['symbol'],'model':payload['model'],'source':payload['source'],
            'cutoff_ms':payload['cutoff_ms'],'cost_cny':costs/1e6,'run_limit_cny':.5}


def create_optimization(identifier,manifest,frame,incumbent):
    """Internal frozen development-only research; no account secrets or holdout."""
    init();reasons=blockers()
    if reasons:raise ValueError('\n'.join(reasons))
    from labapp.optimizer import validate_params
    config=integrations.read();development=frame.iloc[:manifest['development_end']]
    rows=development.tail(24)
    payload={'purpose':'optimization','optimization_id':identifier,'symbol':'BTC/USDT','model':config['model'],
        'credential_fingerprint':ai_connection.fingerprint(config),'source':'Gate frozen development dataset',
        'market_type':'gate_usdt_perpetual','cutoff_ms':int(manifest['development_cutoff']*1000)-1,
        'analysis':{'count':len(development),'return_pct':(development.close.iloc[-1]/development.open.iloc[0]-1)*100,
                    'high':float(development.high.max()),'low':float(development.low.min()),
                    'sma20':float(development.close.tail(20).mean()),'timeframe':'1h'},
        'candles':[{'open_ms':int(r.date.timestamp()*1000),'open':r.open,'high':r.high,'low':r.low,'close':r.close,'volume':r.volume} for r in rows.itertuples()],
        'review':manifest['review'],'incumbent':validate_params(incumbent['params']),
        'research_only':True,'run_limit_cny':.5}
    job_id=__import__('uuid').uuid4().hex
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM research_jobs WHERE state IN ('queued','running')").fetchone():raise ValueError('已有 AI 研究任务，自动优化延后。')
        db.execute('INSERT INTO research_jobs VALUES(?,?,?,?,?,?,?,?,?)',(job_id,time.time(),time.time(),'queued',0,json.dumps(payload),None,None,0))
        db.execute('UPDATE optimizer_runs SET research_id=? WHERE id=?',(job_id,identifier))
    return job_id


def cancel():
    init()
    with store.connect() as db:
        db.execute("UPDATE research_jobs SET cancel=1,updated=? WHERE state IN ('queued','running')",(time.time(),))
    return {'ok':True,'message':'已请求停止研究；正在发出的请求可能仍产生费用，系统不会自动重试。'}


def finish(identifier,state,result=None,error=None):
    with store.connect() as db:
        db.execute('UPDATE research_jobs SET state=?,updated=?,result=?,error=? WHERE id=? AND state=\'running\'',
                   (state,time.time(),json.dumps(result,ensure_ascii=False) if result else None,error,identifier))


def recover():
    init()
    with store.connect() as db:
        db.execute("UPDATE research_jobs SET state='interrupted',updated=?,error='研究服务曾中断；不自动重发付费请求，请人工检查费用后重新发起。' WHERE state='running'",(time.time(),))
