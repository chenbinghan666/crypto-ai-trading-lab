"""Two isolated official Freqtrade paper accounts, fixed 15m comparison."""
import hashlib
import json
import time
import uuid
from contextlib import closing
import sqlite3
from labapp import store

ARMS=('rule','ai')


def init():
    with store.connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS fast_control(id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER,cohort TEXT,state TEXT,message TEXT,created REAL);
            INSERT OR IGNORE INTO fast_control VALUES(1,0,'','stopped','尚未启动 15 分钟独立实验',0);
            CREATE TABLE IF NOT EXISTS fast_signals(arm TEXT PRIMARY KEY,at REAL,candle REAL,direction TEXT,prediction REAL,reason TEXT);
            CREATE TABLE IF NOT EXISTS fast_intents(key TEXT PRIMARY KEY,at REAL);
        ''')


def state():
    init()
    with store.connect() as db:return dict(db.execute('SELECT * FROM fast_control WHERE id=1').fetchone())


def folder():
    c=state();return store.STATE/'fast-experiment'/c['cohort']


def ledger(arm):
    if arm not in ARMS:raise ValueError('未知实验组')
    return folder()/(arm+'.sqlite')


def configure(enabled):
    if type(enabled) is not bool:raise ValueError('开关无效')
    c=state()
    with store.connect() as db:
        if enabled and not c['cohort']:
            db.execute("UPDATE fast_control SET cohort=?,created=? WHERE id=1",(uuid.uuid4().hex,time.time()))
        db.execute('UPDATE fast_control SET enabled=?,message=? WHERE id=1',(int(enabled),'已请求启动独立实验' if enabled else '已请求停止两组实验，账本保留'))
    return {'message':'15 分钟独立实验'+('已启用；先训练，再同时启动两组虚拟账户' if enabled else '已停止；账本与模型保留')}


def update(state,message):
    with store.connect() as db:db.execute('UPDATE fast_control SET state=?,message=? WHERE id=1',(state,message))


def emit(arm,candle,direction,prediction,reason):
    with store.connect() as db:db.execute('INSERT OR REPLACE INTO fast_signals VALUES(?,?,?,?,?,?)',(arm,time.time(),candle,direction,prediction,reason))


def claim(arm,candle,side):
    if not state()['enabled']:return False
    key=f"{state()['cohort']}:{arm}:15m:{candle}:{side}"
    with store.connect() as db:
        try:db.execute('INSERT INTO fast_intents VALUES(?,?)',(key,time.time()))
        except sqlite3.IntegrityError:return False
    return True


def snapshot():
    from labapp import paper
    c=state();result={**c,'arms':{},'capital_per_arm':1000,'timeframe':'15m','leverage':1,'experimental':True,'live_enabled':False}
    p=paper.status();mark=p['checks'].get('mark_price') if p['venue']=='gate' and not p['checks_stale'] and p['checks'].get('ok') else None
    with store.connect() as db:
        signals={r['arm']:dict(r) for r in db.execute('SELECT * FROM fast_signals')}
        services={r['name']:dict(r) for r in db.execute("SELECT * FROM services WHERE name LIKE 'fast_%'")}
    try:result['model']=json.loads((folder()/'model.json').read_text())['metrics']
    except (OSError,ValueError):result['model']=None
    for arm in ARMS:
        service=services.get('fast_'+arm)
        value={'online':bool(service and service['state']=='running' and time.time()-service['heartbeat']<30),
            'heartbeat':service['heartbeat'] if service else None,'signal':signals.get(arm),'trades':[],
            'orders':[],'realized_pnl':0,'closed_count':0,'open_count':0,'error':None}
        path=ledger(arm)
        if path.exists():
            try:
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)) as db,db:
                    db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
                    value['trades']=[dict(r) for r in db.execute('SELECT id,is_open,is_short,open_date,close_date,open_rate,close_rate,close_profit_abs,amount,enter_tag,exit_reason,funding_fees,fee_open,fee_close FROM trades ORDER BY id DESC LIMIT 100')]
                    value['orders']=[dict(r) for r in db.execute('SELECT id,ft_trade_id,side,status,filled,amount,order_date FROM orders ORDER BY id DESC LIMIT 100')]
                    value['realized_pnl']=db.execute('SELECT coalesce(sum(close_profit_abs),0) FROM trades WHERE is_open=0').fetchone()[0]
                    value['closed_count']=db.execute('SELECT count(*) FROM trades WHERE is_open=0').fetchone()[0]
                    value['open_count']=db.execute('SELECT count(*) FROM trades WHERE is_open=1').fetchone()[0]
                    for t in value['trades']:
                        if t['is_open']:
                            filled=db.execute('SELECT coalesce(sum(filled),0) FROM orders WHERE ft_trade_id=? AND side=?',(t['id'],'sell' if t['is_short'] else 'buy')).fetchone()[0]
                            t['entry_filled']=filled>0
            except sqlite3.Error:value.update(error='账本暂时不可读',realized_pnl=None,closed_count=None,open_count=None)
        result['arms'][arm]=value
        opened=[t for t in value['trades'] if t['is_open']]
        for t in opened:
            t['floating_estimate']=((mark-t['open_rate'])*t['amount']*(-1 if t['is_short'] else 1)+(t['funding_fees'] or 0)-t['amount']*(t['open_rate']*(t['fee_open'] or 0)+mark*(t['fee_close'] or 0))) if t.get('entry_filled') and mark and t['open_rate'] else None
        filled_positions=[t for t in opened if t.get('entry_filled')]
        value['floating_estimate']=sum(t['floating_estimate'] for t in filled_positions) if not value['error'] and all(t['floating_estimate'] is not None for t in filled_positions) else None
        value['total_pnl_estimate']=value['realized_pnl']+value['floating_estimate'] if value['realized_pnl'] is not None and value['floating_estimate'] is not None else None
    return result
