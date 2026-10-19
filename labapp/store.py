import json
import os
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get('LAB_STATE_DIR', ROOT/'data/system')).resolve()
LOGS = Path(os.environ.get('LAB_LOG_DIR', ROOT/'logs')).resolve()


def process_identity(pid):
    # WSL may adjust wall-clock boot time. /proc start ticks + boot ID remain stable.
    fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()+':'+fields[19]


def connect():
    STATE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(STATE/'system.sqlite', timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA busy_timeout=10000')
    return db


def init():
    LOGS.mkdir(parents=True,exist_ok=True)
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS services(name TEXT PRIMARY KEY, state TEXT NOT NULL, heartbeat REAL NOT NULL, detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS quotes(symbol TEXT PRIMARY KEY, received REAL NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candles(symbol TEXT NOT NULL, timeframe TEXT NOT NULL, open_ms INTEGER NOT NULL, close_ms INTEGER NOT NULL, open REAL, high REAL, low REAL, close REAL, volume REAL, PRIMARY KEY(symbol,timeframe,open_ms));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at REAL NOT NULL, source TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS order_intents(idempotency_key TEXT PRIMARY KEY, state TEXT NOT NULL, created REAL NOT NULL);
        ''')


def heartbeat(name, state, detail=''):
    with connect() as c:
        c.execute('INSERT INTO services VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET state=excluded.state, heartbeat=excluded.heartbeat, detail=excluded.detail',
                  (name,state,time.time(),detail))


def event(source, level, message):
    with connect() as c:
        c.execute('INSERT INTO events(at,source,level,message) VALUES(?,?,?,?)',(time.time(),source,level,message[:1000]))
        c.execute('DELETE FROM events WHERE id < (SELECT max(id)-2000 FROM events)')


def snapshot():
    from labapp.controls import read
    settings=read()
    with connect() as c:
        services = [dict(x) for x in c.execute('SELECT * FROM services ORDER BY name')]
        quote = c.execute('SELECT * FROM quotes WHERE symbol=?',(settings['symbol'],)).fetchone()
        candles = [dict(x) for x in c.execute('SELECT * FROM (SELECT * FROM candles WHERE symbol=? ORDER BY open_ms DESC LIMIT 120) ORDER BY open_ms',(settings['symbol'],))]
        events = [dict(x) for x in c.execute('SELECT * FROM events ORDER BY id DESC LIMIT 120')]
    now = time.time()
    for service in services:
        service['age_seconds'] = round(now-service['heartbeat'],1)
        if service['state'] in ('running','starting') and service['age_seconds'] > 90:
            service['state'] = 'stale'
    market = json.loads(quote['payload']) if quote else None
    if market:
        market['age_seconds'] = round(now-quote['received'],1)
        market['stale_after_seconds'] = max(30,market.get('poll_interval',3)*2+5)
        market['stale'] = market['age_seconds'] > market['stale_after_seconds']
    return {'now':now,'mode':'infrastructure_only','live_enabled':False,'paper_enabled':False,
            'market':market,'services':services,'candles':candles,'events':events,'settings':settings,
            'modules':{'ai':'not_configured','training':'not_enabled','decision':'not_enabled',
                       'risk':'entry_blocked','execution':'disabled','review':'not_enabled'},
            'performance':{'pnl':None,'trades':0,'note':'交易引擎未启动，无收益数据'},
            'budget':{'month_limit_cny':30,'spent_cny':0,'calls':0,'enabled':False}}
