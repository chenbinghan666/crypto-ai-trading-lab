"""Durable, bounded controls for public market collection only."""
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from labapp import store
from labapp.network import probe

DEFAULT = {'symbol':'BTC/USDT','source':'auto','interval':3,'paused':False,'revision':0,'refresh':0}
DIAG_LOCK = threading.Lock()
DIAG_CACHE = {}


def read():
    with store.connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        row=c.execute("SELECT payload FROM settings WHERE name='market'").fetchone()
    return {**DEFAULT, **json.loads(row[0])} if row else dict(DEFAULT)


def change(data):
    if set(data)-{'symbol','source','interval','paused','refresh'}:
        raise ValueError('不支持该操作。')
    if 'symbol' in data and data['symbol'] not in ('BTC/USDT','ETH/USDT','SOL/USDT'):
        raise ValueError('仅支持 BTC、ETH、SOL 对 USDT。')
    if 'source' in data and data['source'] not in ('auto','futures','spot'):
        raise ValueError('行情来源无效。')
    if 'interval' in data and (type(data['interval']) is not int or data['interval'] not in (3,5,10,30)):
        raise ValueError('采集间隔仅支持 3、5、10、30 秒。')
    if 'paused' in data and type(data['paused']) is not bool:
        raise ValueError('暂停状态无效。')
    if 'refresh' in data and data['refresh'] is not True:
        raise ValueError('刷新操作无效。')
    read()
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT payload FROM settings WHERE name='market'").fetchone()
        current={**DEFAULT,**json.loads(row[0])} if row else dict(DEFAULT)
        if data.get('refresh'):
            if current['paused']:
                raise ValueError('请先恢复采集，再立即刷新。')
            if time.time()-current['refresh'] < 3:
                raise ValueError('刷新过于频繁，请稍后再试。')
            current['refresh']=time.time()
        current.update({k:v for k,v in data.items() if k!='refresh'})
        current['revision']+=1
        c.execute("INSERT INTO settings VALUES('market',?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",(json.dumps(current),))
    store.event('controls','info',f"行情设置已更新：{current['symbol']} / {current['source']} / {current['interval']} 秒 / {'暂停' if current['paused'] else '采集中'}")
    return current


def diagnostics():
    with DIAG_LOCK:
        if time.time()-DIAG_CACHE.get('at',0)<30:
            return DIAG_CACHE
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(probe,[('币安 U 本位合约','https://fapi.binance.com/fapi/v1/time'),('币安现货公共行情','https://data-api.binance.vision/api/v3/time')]))
        DIAG_CACHE.update(at=time.time(),results=results)
        return DIAG_CACHE
