import sqlite3
import time
import pytest
from labapp import store,paper,paper_monitor


@pytest.fixture
def ledger(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'STATE',tmp_path);monkeypatch.setattr(store,'LOGS',tmp_path/'logs')
    store.init();paper.init()
    with store.connect() as db:db.execute("UPDATE paper_control SET venue='gate',enabled=1,state='running'")
    store.heartbeat('paper_engine','running')
    path=paper.ledger_path()
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE trades(id INTEGER PRIMARY KEY,pair TEXT,is_open INTEGER,is_short INTEGER,
            amount REAL,stake_amount REAL,open_rate REAL,close_rate REAL,close_profit_abs REAL,
            open_date TEXT,close_date TEXT,leverage REAL,funding_fees REAL,fee_open REAL,fee_close REAL);
            CREATE TABLE orders(id INTEGER PRIMARY KEY,ft_trade_id INTEGER,side TEXT,status TEXT,
            filled REAL,remaining REAL,amount REAL,price REAL,average REAL,order_date TEXT);
            INSERT INTO trades VALUES(1,'BTC/USDT:USDT',1,0,0.01,100,10000,NULL,NULL,'2026-10-17 00:00:00',NULL,1,0,0.001,0.001);
            INSERT INTO trades VALUES(2,'BTC/USDT:USDT',1,1,0.01,100,10000,NULL,NULL,'2026-10-17 00:00:00',NULL,1,0,0.001,0.001);
            INSERT INTO trades VALUES(3,'BTC/USDT:USDT',0,1,0.01,100,10000,9900,0.8,'2026-10-16 00:00:00','2026-10-17 00:00:00',1,0,0.001,0.001);
            INSERT INTO orders VALUES(1,1,'buy','closed',0.01,0,0.01,10000,10000,'2026-10-17 00:00:00');
            INSERT INTO orders VALUES(2,2,'sell','closed',0.01,0,0.01,10000,10000,'2026-10-17 00:00:00');
            INSERT INTO orders VALUES(3,3,'buy','closed',0.01,0,0.01,9900,9900,'2026-10-17 00:00:00');
            INSERT INTO orders VALUES(4,1,'sell','canceled',0,0.01,0.01,10200,NULL,'2026-10-17 00:00:00');''')
    return path


def control():
    return {'enabled':True,'state':'running','checks_stale':False,
        'checks':{'ok':True,'mark_price':10100,'received_at':time.time()}}


def test_live_multiside_fills_and_net_pnl_read_only(ledger):
    original=ledger.read_bytes();s=paper_monitor.snapshot(control())
    assert s['engine_healthy'] and s['state']=='running'
    assert [t['is_short'] for t in s['positions']]==[1,0]
    values={t['id']:t['unrealized_pnl'] for t in s['positions']}
    assert values[1]==pytest.approx(.799) and values[2]==pytest.approx(-1.201)
    assert s['realized_pnl']==.8 and s['closed_count']==1
    assert s['total_orders']==4 and s['filled_orders']==3
    assert [o['action'] for o in s['recent_orders']]==['平多','平空','开空','开多']
    assert s['recent_orders'][0]['status']=='canceled'
    assert ledger.read_bytes()==original


def test_stale_prices_or_engine_are_not_reported_healthy(ledger):
    c=control();c['checks_stale']=True
    with store.connect() as db:db.execute("UPDATE services SET heartbeat=? WHERE name='paper_engine'",(time.time()-60,))
    s=paper_monitor.snapshot(c)
    assert not s['engine_healthy'] and s['state']=='reconnecting'
    assert s['mark_price'] is None and s['unrealized_pnl'] is None
    assert s['realized_pnl']==.8


def test_pending_entry_is_not_a_filled_position(ledger):
    with sqlite3.connect(ledger) as db:db.execute('UPDATE orders SET filled=0 WHERE ft_trade_id=2')
    s=paper_monitor.snapshot(control())
    assert not s['positions'][0]['entry_filled'] and s['positions'][0]['unrealized_pnl'] is None
    assert s['unrealized_pnl']==pytest.approx(.799)


def test_unreadable_ledger_is_not_zero_trades(ledger):
    ledger.write_bytes(b'invalid database')
    s=paper_monitor.snapshot(control())
    assert s['ledger_error'] and s['total_orders'] is None and s['realized_pnl'] is None
