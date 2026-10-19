"""Local AI connection configuration. Never starts paid inference or training."""
import json
import os
import re
import time
import math
from labapp import accounts, store


def read():
    with accounts.LOCK:
        path=accounts.secret_dir()/'deepseek.enc'
        return json.loads(accounts.cipher().decrypt(path.read_bytes())) if path.exists() else None


def status():
    try:
        config=read()
    except Exception:
        return {'configured':True,'error':'本机配置无法解密，请清除后重新配置。'}
    from labapp import ai_connection,ai_costs
    return {'configured':bool(config),'provider':'DeepSeek','model':config['model'] if config else '',
            'budget_cny':config['budget_cny'] if config else 30,'automatic_research_enabled':ai_costs.summary()['automatic_inference_enabled'],
            'validation':ai_connection.status(),'costs':ai_costs.summary(),
            'note':'密钥验证仅查询模型列表；研究可手动发起或由自动优化调度，预算在每次推理前检查。'}


def save(data):
    key=data.get('key')
    model=data.get('model')
    budget=data.get('budget_cny')
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,256}',key):
        raise ValueError('请输入有效的 AI API Key。')
    if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,100}',model):
        raise ValueError('请输入模型 ID（英文字母、数字及常见分隔符）。')
    if type(budget) not in (int,float) or not 1<=budget<=10000:
        raise ValueError('月预算须在 1 至 10000 元之间。')
    with accounts.LOCK:
        path=accounts.secret_dir()/'deepseek.enc'
        temp=path.with_suffix('.tmp')
        payload=accounts.cipher().encrypt(json.dumps({'key':key,'model':model,'budget_cny':budget}).encode())
        with os.fdopen(os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'wb') as f:
            f.write(payload)
        temp.replace(path)
    return status()


def delete():
    with accounts.LOCK:
        (accounts.secret_dir()/'deepseek.enc').unlink(missing_ok=True)


def readiness():
    from labapp import research_jobs, paper, training
    research_blockers=research_jobs.blockers()
    return {
        'analysis':{'title':'行情数据分析','ready':True,'blockers':[]},
        'research':{'title':'AI 研究','ready':not research_blockers,'blockers':research_blockers,
                    'description':'官方 TradingAgents 多角色研究；每次预算上限 0.5 元，每日 1 元；不产生订单。'},
        'training':training.readiness(),
        'simulation':paper.readiness(),
        'live':{'title':'真实合约交易','ready':False,'blockers':['实盘执行器未接入','独立风控及重复订单保护尚未验收','尚无独立验收记录及有效人工授权']}}


def last_analysis():
    with store.connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS analysis_runs(id INTEGER PRIMARY KEY,at REAL,payload TEXT)')
        row=c.execute('SELECT payload FROM analysis_runs ORDER BY id DESC LIMIT 1').fetchone()
    return json.loads(row[0]) if row else None


def analyze():
    snapshot=store.snapshot()
    rows=snapshot['candles']
    if len(rows)<20:
        raise ValueError('至少需要 20 根已收盘 K 线；请先采集行情。')
    closes=[r['close'] for r in rows]
    if not all(math.isfinite(x) and x>0 for x in closes):
        raise ValueError('行情数据无效，未生成分析。')
    result={'at':time.time(),'symbol':snapshot['settings']['symbol'],
            'source':(snapshot['market'] or {}).get('source'),'count':len(rows),
            'from_ms':rows[0]['open_ms'],'to_ms':rows[-1]['close_ms'],
            'return_pct':(closes[-1]/rows[0]['open']-1)*100,
            'high':max(r['high'] for r in rows),'low':min(r['low'] for r in rows),
            'sma20':sum(closes[-20:])/20,'volume':sum(r['volume'] for r in rows),
            'note':'仅对已收盘历史数据做描述统计，不是 AI 研究、预测或下单信号。'}
    last_analysis()
    with store.connect() as c:
        c.execute('INSERT INTO analysis_runs(at,payload) VALUES(?,?)',(time.time(),json.dumps(result)))
        c.execute('DELETE FROM analysis_runs WHERE id < (SELECT max(id)-99 FROM analysis_runs)')
    store.event('analysis','info',f"已完成 {result['symbol']} 的 {len(rows)} 根已收盘 K 线描述统计；未触发交易")
    return result
