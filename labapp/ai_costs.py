"""Durable cost reservations for future inference; no provider calls here.

Amounts are integer micro-CNY. Unknown outcomes remain reserved on restart.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from zoneinfo import ZoneInfo
import json
import time
from labapp import store, integrations

PRICES={'deepseek-flash':{'input':2,'cached_input':.04,'output':8},
        'deepseek-v4-pro':{'input':9,'cached_input':.30,'output':27}}
VERIFIED_ON='2026-10-16'
VALID_UNTIL='2026-10-23'
PRICE_URL='https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'
ZONE=ZoneInfo('Asia/Singapore')
MAX_CALL_MICRO=500000
DAILY_MICRO=1000000


def init():
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS ai_cost_ledger(request_id TEXT PRIMARY KEY,at REAL,month TEXT,day TEXT,
                   model TEXT,reserved_micro INTEGER,actual_micro INTEGER,state TEXT,usage TEXT)''')


def money_micro(value):
    return int((Decimal(str(value))*1000000).to_integral_value(rounding=ROUND_CEILING))


def quote_micro(model,input_tokens,output_tokens,cached_tokens=0):
    if model not in PRICES:
        raise ValueError('模型暂无核验价格，禁止付费调用。')
    if any(type(n) is not int or n<0 for n in (input_tokens,output_tokens,cached_tokens)) or cached_tokens>input_tokens:
        raise ValueError('Token 用量无效。')
    price=PRICES[model]
    return int((Decimal(str(price['input']))*(input_tokens-cached_tokens)+Decimal(str(price['cached_input']))*cached_tokens+Decimal(str(price['output']))*output_tokens).to_integral_value(rounding=ROUND_CEILING))


def _dates():
    now=datetime.now(ZONE)
    return now.strftime('%Y-%m'),now.strftime('%Y-%m-%d')


def summary():
    init()
    month,day=_dates()
    config=integrations.read()
    limit=money_micro(config['budget_cny'] if config else 30)
    with store.connect() as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM ai_cost_ledger WHERE month=?',(month,))]
        auto=bool(db.execute('SELECT enabled FROM optimizer_control WHERE id=1').fetchone()[0]) if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='optimizer_control'").fetchone() else False
    spent=sum(r['actual_micro'] or 0 for r in rows if r['state']=='settled')
    reserved=sum(r['reserved_micro'] for r in rows if r['state'] in ('reserved','unknown'))
    daily=sum((r['actual_micro'] or 0) if r['state']=='settled' else r['reserved_micro'] if r['state'] in ('reserved','unknown') else 0 for r in rows if r['day']==day)
    return {'month':month,'month_limit_cny':limit/1e6,'spent_cny':spent/1e6,'reserved_cny':reserved/1e6,
            'remaining_cny':max(0,limit-spent-reserved)/1e6,'calls':len(rows),
            'daily_limit_cny':1,'single_call_limit_cny':.5,'price_checked_on':VERIFIED_ON,
            'daily_remaining_cny':max(0,DAILY_MICRO-daily)/1e6,
            'price_valid_until':VALID_UNTIL,'price_source':PRICE_URL,
            'estimation':'按核验的高峰价格保守计费；服务商账单为准。','automatic_inference_enabled':auto}


def reserve(request_id,model,max_input_tokens,max_output_tokens,run_id=None):
    init()
    if not isinstance(request_id,str) or not 1<=len(request_id)<=100:
        raise ValueError('请求 ID 无效。')
    month,day=_dates()
    if day>VALID_UNTIL:
        raise ValueError('价格核验已过期，禁止新增付费调用。')
    config=integrations.read()
    if not config or config['model']!=model:
        raise ValueError('请先配置匹配的模型。')
    estimated=quote_micro(model,max_input_tokens,max_output_tokens)
    if not 0<estimated<=MAX_CALL_MICRO:
        raise ValueError('单次预估费用超过 0.5 元上限。')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM ai_cost_ledger WHERE request_id=?',(request_id,)).fetchone():
            raise ValueError('重复请求已拒绝，不得再次发送。')
        charged="CASE WHEN state='settled' THEN actual_micro WHEN state IN ('reserved','unknown') THEN reserved_micro ELSE 0 END"
        total=db.execute('SELECT coalesce(sum('+charged+'),0) FROM ai_cost_ledger WHERE month=?',(month,)).fetchone()[0]
        daily=db.execute('SELECT coalesce(sum('+charged+'),0) FROM ai_cost_ledger WHERE day=?',(day,)).fetchone()[0]
        if total+estimated>money_micro(config['budget_cny']) or daily+estimated>DAILY_MICRO:
            raise ValueError('预算额度不足，调用已阻止。')
        if run_id:
            if not request_id.startswith(run_id+':'):
                raise ValueError('研究请求归属无效。')
            run_total=db.execute('SELECT coalesce(sum('+charged+'),0) FROM ai_cost_ledger WHERE substr(request_id,1,?)=?',
                                 (len(run_id)+1,run_id+':')).fetchone()[0]
            if run_total+estimated>MAX_CALL_MICRO:
                raise ValueError('本次研究达到 0.5 元预算上限，已停止新增推理。')
        db.execute('INSERT INTO ai_cost_ledger VALUES(?,?,?,?,?,?,NULL,?,NULL)',
                   (request_id,time.time(),month,day,model,estimated,'reserved'))
    return estimated


def settle(request_id,input_tokens,output_tokens,cached_tokens=0):
    init()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM ai_cost_ledger WHERE request_id=?',(request_id,)).fetchone()
        if not row or row['state'] not in ('reserved','unknown'):
            raise ValueError('该请求不存在或已经结算。')
        actual=quote_micro(row['model'],input_tokens,output_tokens,cached_tokens)
        usage=json.dumps({'input_tokens':input_tokens,'output_tokens':output_tokens,'cached_tokens':cached_tokens})
        db.execute("UPDATE ai_cost_ledger SET actual_micro=?,state='settled',usage=? WHERE request_id=?",(actual,usage,request_id))
    return actual


def mark_unknown(request_id):
    init()
    with store.connect() as db:
        db.execute("UPDATE ai_cost_ledger SET state='unknown' WHERE request_id=? AND state='reserved'",(request_id,))
