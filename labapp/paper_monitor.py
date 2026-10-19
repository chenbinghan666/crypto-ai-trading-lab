"""Read-only live paper ledger and worker health. Never issues orders."""
import math
import sqlite3
import time
from contextlib import closing
from labapp import store,paper


def snapshot(control):
    now=time.time()
    with store.connect() as db:
        row=db.execute("SELECT * FROM services WHERE name='paper_engine'").fetchone()
    engine=dict(row) if row else None
    healthy=bool(engine and engine['state']=='running' and 0<=now-engine['heartbeat']<30)
    mark=control['checks'].get('mark_price')
    fresh=not control['checks_stale'] and control['checks'].get('ok')
    mark=float(mark) if fresh and isinstance(mark,(int,float)) and math.isfinite(mark) and mark>0 else None
    result={'received_at':now,'engine':engine,'engine_healthy':healthy,'enabled':control['enabled'],
        'state':control['state'] if not control['enabled'] or healthy else 'reconnecting',
        'ledger_present':paper.ledger_path().exists(),'ledger_error':None,
        'positions':[],'closed_trades':[],'recent_orders':[],'total_orders':0,'filled_orders':0,
        'closed_count':0,'realized_pnl':0.0,'unrealized_pnl':0.0,'mark_price':mark,
        'mark_received_at':control['checks'].get('received_at'),'unrealized_estimated':True}
    if not result['ledger_present']:return result
    try:
        with closing(sqlite3.connect(paper.ledger_path().as_uri()+'?mode=ro',uri=True,timeout=1)) as db, db:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            def columns(table,names):
                available={r['name'] for r in db.execute('PRAGMA table_info('+table+')')}
                return ','.join(n if n in available else 'NULL AS '+n for n in names.split(','))
            fields=columns('trades','id,pair,is_short,amount,stake_amount,open_rate,close_rate,close_profit_abs,open_date,close_date,leverage,funding_fees,fee_open,fee_close,enter_tag,exit_reason')
            result['positions']=[dict(r) for r in db.execute('SELECT '+fields+' FROM trades WHERE is_open=1 ORDER BY id DESC')]
            result['closed_trades']=[dict(r) for r in db.execute('SELECT '+fields+' FROM trades WHERE is_open=0 ORDER BY close_date DESC,id DESC LIMIT 100')]
            fields=columns('orders','id,ft_trade_id,side,ft_order_side,status,order_type,price,average,amount,filled,remaining,order_date,order_filled_date,order_update_date,ft_is_open')
            orders=[dict(r) for r in db.execute('SELECT '+fields+' FROM orders ORDER BY id DESC LIMIT 100')]
            directions={r['id']:bool(r['is_short']) for r in db.execute('SELECT id,is_short FROM trades')}
            for o in orders:
                short=directions.get(o['ft_trade_id']);side=o['side']
                o['action']=('开空' if side=='sell' else '平空') if short is True else ('开多' if side=='buy' else '平多')
                if side not in ('buy','sell') or short is None:o['action']='订单'
            result['recent_orders']=orders
            result['total_orders']=db.execute('SELECT count(*) FROM orders').fetchone()[0]
            result['filled_orders']=db.execute('SELECT count(*) FROM orders WHERE filled>0').fetchone()[0]
            totals=db.execute('SELECT count(*),coalesce(sum(close_profit_abs),0) FROM trades WHERE is_open=0').fetchone()
            result['closed_count'],result['realized_pnl']=totals
            for t in result['positions']:
                t['unrealized_pnl']=None
                entry_side='sell' if t['is_short'] else 'buy'
                filled=db.execute('SELECT coalesce(sum(filled),0) FROM orders WHERE ft_trade_id=? AND side=?',(t['id'],entry_side)).fetchone()[0]
                t['entry_filled']=filled>0
                if mark and t['entry_filled'] and t['open_rate'] and t['amount']:
                    t['unrealized_pnl']=(mark-t['open_rate'])*t['amount']*(-1 if t['is_short'] else 1)+(t['funding_fees'] or 0)-t['amount']*t['open_rate']*(t['fee_open'] or 0)-t['amount']*mark*(t['fee_close'] or 0)
            values=[t['unrealized_pnl'] for t in result['positions'] if t['entry_filled']]
            result['unrealized_pnl']=sum(values) if all(v is not None for v in values) else None
    except sqlite3.Error:
        result.update(ledger_error='模拟账本暂时不可读，不能据此判断没有交易。',positions=[],closed_trades=[],recent_orders=[],
            total_orders=None,filled_orders=None,closed_count=None,realized_pnl=None,unrealized_pnl=None)
    return result
