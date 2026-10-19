import json
import time
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from labapp import store, market
from scripts.safety import validate_config


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('LAB_SECRETS_DIR',str(tmp_path/'secrets'))
    monkeypatch.setattr(store,'STATE',tmp_path/'data')
    monkeypatch.setattr(store,'LOGS',tmp_path/'logs')
    store.init()
    return tmp_path


def rows():
    return [[60000,'10','12','9','11','5',119999],[120000,'11','13','10','12','4',179999]]


def test_unclosed_candle_excluded():
    assert len(market.validate_candles(rows(),150000)) == 1


@pytest.mark.parametrize('change', ['gap','duplicate','nan','negative','bounds','stale'])
def test_invalid_market_data_rejected(change):
    data=rows()
    if change == 'gap':data[1][0]=240000;data[1][6]=299999
    if change == 'duplicate':data[1]=data[0][:]
    if change == 'nan':data[0][4]='nan'
    if change == 'negative':data[0][5]='-1'
    if change == 'bounds':data[0][2]='1'
    with pytest.raises(ValueError):
        market.validate_candles(data,500000 if change=='stale' else 200000)


def test_candle_dedup_survives_reopen(isolated):
    values=market.validate_candles(rows(),200000)
    for _ in range(2):
        with store.connect() as c:
            c.executemany('INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?,?,?,?,?)',values)
    with store.connect() as c:
        assert c.execute('SELECT count(*) FROM candles').fetchone()[0]==2


def test_snapshot_marks_stale(isolated):
    with store.connect() as c:
        c.execute('INSERT INTO quotes VALUES(?,?,?)',('BTC/USDT',time.time()-40,'{}'))
        c.execute('INSERT INTO services VALUES(?,?,?,?)',('market','running',time.time()-100,'test'))
    s=store.snapshot()
    # An empty payload is not a valid collector output. Use a real-shaped payload.
    with store.connect() as c:
        c.execute('UPDATE quotes SET payload=?',(json.dumps({'mid':10}),))
    s=store.snapshot()
    assert s['market']['stale']
    assert s['services'][0]['state']=='stale'
    assert s['paper_enabled'] is False and s['live_enabled'] is False


def test_slow_poll_interval_does_not_falsely_expire(isolated):
    with store.connect() as c:
        c.execute('INSERT INTO quotes VALUES(?,?,?)',('BTC/USDT',time.time()-35,json.dumps({'mid':10,'poll_interval':30})))
    assert store.snapshot()['market']['stale'] is False
    with store.connect() as c:
        c.execute('UPDATE quotes SET received=?',(time.time()-70,))
    assert store.snapshot()['market']['stale'] is True


@pytest.mark.parametrize('change',['live','key','env','endpoint','force','remote'])
def test_unsafe_config_rejected(change):
    c=json.loads((store.ROOT/'configs/paper/freqtrade.json').read_text())
    env={}
    if change=='live':c['dry_run']=False
    if change=='key':c['exchange']['key']='test-not-a-real-key'
    if change=='env':env['FREQTRADE__DRY_RUN']='false'
    if change=='endpoint':c['exchange']['ccxt_config']['urls']['api']['public']='https://example.com'
    if change=='force':c['force_entry_enable']=True
    if change=='remote':c['api_server']={'enabled':True}
    with pytest.raises(ValueError):validate_config(c,env)


def test_read_only_dashboard(isolated):
    from labapp.web import app
    with TestClient(app,base_url='http://localhost') as client:
        assert client.get('/health').status_code==200
        assert client.get('/style.css').headers['content-type'].startswith('text/css')
        assert client.get('/app.js').headers['content-type'].startswith('text/javascript')
        assert client.get('/api/status').json()['mode']=='infrastructure_only'
        assert client.post('/api/status').status_code==405
        assert client.get('/api/status',headers={'host':'evil.example'}).status_code==400


def test_connection_error_does_not_replace_good_quote(isolated,monkeypatch):
    with store.connect() as c:
        c.execute('INSERT INTO quotes VALUES(?,?,?)',('BTC/USDT',1,json.dumps({'mid':10})))
    def fail(*args):raise TimeoutError('offline')
    monkeypatch.setattr(market,'fetch',fail)
    with pytest.raises(TimeoutError):market.collect()
    assert store.snapshot()['market']['mid']==10
    assert store.snapshot()['market']['stale']


def test_market_fallback_is_labeled_and_never_mixes_candles(isolated,monkeypatch):
    monkeypatch.setattr(market,'FUTURES_RETRY',0)
    monkeypatch.setattr(market.time,'time',lambda:150)
    def fake(endpoint):
        if market.ACTIVE_BASE==market.FUTURES:raise TimeoutError()
        if endpoint=='time':return {'serverTime':150000}
        if endpoint.startswith('ticker'):return {'bidPrice':'10','askPrice':'11'}
        return rows()
    monkeypatch.setattr(market,'fetch',fake)
    with store.connect() as c:
        c.execute('INSERT INTO quotes VALUES(?,?,?)',('BTC/USDT',1,json.dumps({'source':market.FUTURES})))
        c.execute('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?)',('BTC/USDT','1m',0,59999,1,1,1,1,1))
    market.collect()
    s=store.snapshot()
    assert s['market']['market_type']=='spot_reference'
    assert s['market']['fallback_reason']
    assert s['market']['current_candle']['unclosed']
    assert s['market']['next_poll_at']==153
    assert [r['open_ms'] for r in s['candles']]==[60000]


def test_futures_market_uses_futures_source(isolated,monkeypatch):
    monkeypatch.setattr(market,'FUTURES_RETRY',0)
    monkeypatch.setattr(market.time,'time',lambda:150)
    def fake(endpoint):
        assert market.ACTIVE_BASE==market.FUTURES
        if endpoint=='time':return {'serverTime':150000}
        if endpoint.startswith('ticker'):return {'bidPrice':'10','askPrice':'11'}
        return rows()
    monkeypatch.setattr(market,'fetch',fake)
    market.collect()
    assert store.snapshot()['market']['market_type']=='usd_m_futures'
    assert store.snapshot()['market']['fallback_reason'] is None
