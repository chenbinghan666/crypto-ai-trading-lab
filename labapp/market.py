"""Independent read-only Binance collector with durable deduplication and backoff."""
import json
import math
import signal
import threading
import time
from urllib.request import Request, urlopen

from labapp.store import connect, event, heartbeat, init
from labapp import controls
from labapp.network import explain_error

BASE = 'https://data-api.binance.vision/api/v3/'
FUTURES = 'https://fapi.binance.com/fapi/v1/'
INTERVAL = 3
FUTURES_RETRY = 0
FUTURES_ERROR = '合约接口暂不可达'
ACTIVE_BASE = BASE
STOP = threading.Event()


def fetch(endpoint):
    with urlopen(Request(ACTIVE_BASE+endpoint,headers={'User-Agent':'CryptoLab/0.2-public-research'}),timeout=5) as r:
        return json.load(r)


def validate_candles(rows, server_ms):
    good = []
    previous = None
    for row in rows:
        ts, closing = int(row[0]), int(row[6])
        values = [float(v) for v in row[1:6]]
        o,h,l,c,v = values
        if not all(math.isfinite(x) for x in values) or min(o,h,l,c) <= 0 or v < 0 or h < max(o,l,c) or l > min(o,h,c):
            raise ValueError('Invalid Binance OHLCV')
        if ts % 60000 or closing != ts + 59999 or (previous is not None and ts-previous != 60000):
            raise ValueError('Duplicate/gapped/misaligned Binance candle')
        previous = ts
        if closing < server_ms:
            good.append(('BTC/USDT','1m',ts,closing,*values))
    if not good or server_ms-good[-1][3] > 120000:
        raise ValueError('Stale closed candles')
    return good


def collect(settings=None):
    global ACTIVE_BASE, FUTURES_RETRY, FUTURES_ERROR
    settings=settings or controls.read()
    symbol=settings['symbol']
    interval=settings['interval']
    source=settings['source']
    fallback = False
    if source=='spot':
        ACTIVE_BASE=BASE
        fallback=True
    elif source=='futures' or time.time() >= FUTURES_RETRY:
        ACTIVE_BASE = FUTURES
        try:
            result = fetch('time')
        except Exception as exc:
            FUTURES_ERROR=explain_error(exc)[2]
            if source=='futures':
                raise
            FUTURES_RETRY = time.time()+60
            ACTIVE_BASE = BASE
            fallback = True
        else:
            result = int(result['serverTime'])
    else:
        ACTIVE_BASE = BASE
        fallback = True
    server_ms = int(fetch('time')['serverTime']) if fallback else result
    if abs(server_ms-time.time()*1000) > 60000:
        raise ValueError('Clock skew exceeds 60 seconds')
    pair=symbol.replace('/','')
    book = fetch('ticker/bookTicker?symbol='+pair)
    raw = fetch('klines?symbol='+pair+'&interval=1m&limit=120')
    candles = [(symbol,*row[1:]) for row in validate_candles(raw,server_ms)]
    current = None
    last = raw[-1]
    if int(last[0]) <= server_ms <= int(last[6]):
        current = dict(zip(('open','high','low','close','volume'),map(float,last[1:6])))
        current.update(open_ms=int(last[0]),close_ms=int(last[6]),unclosed=True)
    bid,ask = float(book['bidPrice']),float(book['askPrice'])
    if not (math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask):
        raise ValueError('Invalid bid/ask')
    market = {'symbol':symbol,'bid':bid,'ask':ask,'mid':(bid+ask)/2,
              'spread_bps':(ask-bid)/((bid+ask)/2)*10000,'server_ms':server_ms,
              'received_at':time.time(),'source':ACTIVE_BASE,'timeframe':'1m',
              'market_type':'spot_reference' if fallback else 'usd_m_futures',
              'fallback_reason':('已选择现货参考行情' if source=='spot' else FUTURES_ERROR+' 当前显示现货参考价格。') if fallback else None,
              'current_candle':current,'poll_interval':interval,'next_poll_at':time.time()+interval,
              'purpose':'display_only_not_strategy_timeframe'}
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT payload FROM settings WHERE name='market'").fetchone()
        if row and json.loads(row[0])['revision']!=settings['revision']:
            return 0
        previous = c.execute('SELECT payload FROM quotes WHERE symbol=?',(symbol,)).fetchone()
        if previous and json.loads(previous[0]).get('source') != ACTIVE_BASE:
            c.execute('DELETE FROM candles WHERE symbol=?',(symbol,))
        c.execute('INSERT INTO quotes VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET received=excluded.received,payload=excluded.payload',
                  (symbol,time.time(),json.dumps(market)))
        c.executemany('INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?,?,?,?,?)',candles)
        # Bound storage to seven days. Primary key survives worker restarts.
        c.execute('DELETE FROM candles WHERE open_ms < ?', (server_ms-7*86400000,))
    return len(candles)


def main():
    global FUTURES_RETRY
    init()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:STOP.set())
    failures = 0
    due=0
    revision=-1
    heartbeat('market','starting','连接币安公共实时行情')
    while not STOP.is_set():
        settings=controls.read()
        if settings['revision']!=revision:
            revision=settings['revision']
            due=0
            FUTURES_RETRY=0
        if settings['paused']:
            heartbeat('market','paused','用户暂停公共行情采集；交易仍关闭')
            STOP.wait(1)
            continue
        if time.time()<due:
            STOP.wait(.5)
            continue
        try:
            count = collect(settings)
            if failures:
                event('market','info','币安行情连接恢复')
            failures = 0
            heartbeat('market','running',f'公共行情正常；本次 {count} 根已收盘 K 线；交易关闭')
            due=time.time()+settings['interval']
        except Exception as exc:
            failures += 1
            detail = f'{type(exc).__name__}: {str(exc)[:200]}'
            heartbeat('market','reconnecting',detail)
            if failures == 1 or failures % 10 == 0:
                event('market','warning','行情获取失败，退避重连：'+detail)
            due=time.time()+min(60,2**min(failures,6))
    heartbeat('market','stopped','采集服务已停止')


if __name__ == '__main__':
    main()
