import json
import time
import hashlib
import hmac
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient
from labapp import accounts, store, web


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('LAB_SECRETS_DIR',str(tmp_path/'secrets'))
    monkeypatch.setattr(store,'STATE',tmp_path/'state')
    monkeypatch.setattr(store,'LOGS',tmp_path/'logs')
    store.init()
    (store.STATE/'frequi-auth.json').write_text(json.dumps({'password':'test-admin'}))
    monkeypatch.setattr(accounts,'CACHE',{'state':'not_configured'})
    monkeypatch.setattr(accounts,'REVISION',0)
    web.SESSIONS.clear()
    web.ATTEMPTS.clear()
    return tmp_path


def client_login():
    client=TestClient(web.app,base_url='http://localhost')
    response=client.post('/api/account/login',json={'password':'test-admin'},headers={'Origin':'http://localhost'})
    assert response.status_code==200
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=strict' in response.headers['set-cookie']
    return client


def test_private_routes_require_auth_and_origin(isolated):
    c=TestClient(web.app,base_url='http://localhost')
    assert c.get('/api/account').status_code==401
    assert c.post('/api/account/connect',json={},headers={'Origin':'http://localhost'}).status_code==401
    assert c.post('/api/account/login',json={'password':'test-admin'},headers={'Origin':'https://evil.example'}).status_code==403
    c=client_login()
    assert c.get('/api/account').headers['cache-control']=='no-store'
    assert c.post('/api/account/disconnect',json={}).status_code==403
    assert 'positions' not in c.get('/api/status').json()
    assert c.post('/api/account/order',json={}).status_code==404
    assert c.post('/api/account/logout',json={},headers={'Origin':'http://localhost'}).status_code==200
    assert c.get('/api/account').status_code==401


def test_session_expiry_and_rate_limit(isolated):
    c=client_login()
    for token in web.SESSIONS:web.SESSIONS[token]=0
    assert c.get('/api/account').status_code==401
    for _ in range(4):
        assert c.post('/api/account/login',json={'password':'wrong'},headers={'Origin':'http://localhost'}).status_code==401
    assert c.post('/api/account/login',json={'password':'wrong'},headers={'Origin':'http://localhost'}).status_code==429


def test_encrypted_storage_and_no_secret_echo(isolated):
    c=client_login()
    payload={'key':'K'*64,'secret':'S'*64}
    response=c.post('/api/account/connect',json=payload,headers={'Origin':'http://localhost'})
    assert response.status_code==200
    encrypted=(accounts.secret_dir()/'binance.enc').read_bytes()
    assert b'K'*64 not in encrypted and b'S'*64 not in encrypted
    assert accounts.credentials()==payload
    assert (accounts.secret_dir()/'binance.enc').stat().st_mode & 0o777 == 0o600
    assert 'S'*64 not in c.get('/api/account').text
    assert 'key' not in c.get('/api/account').json()
    payload['secret']='BAD SECRET DO NOT ECHO'
    response=c.post('/api/account/connect',json=payload,headers={'Origin':'http://localhost'})
    assert response.status_code==400 and payload['secret'] not in response.text
    c.post('/api/account/disconnect',json={},headers={'Origin':'http://localhost'})
    assert accounts.credentials() is None
    assert 'totals' not in accounts.snapshot()


def test_endpoint_allowlist_and_signature(monkeypatch):
    observed=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return b'{}'
    class Opener:
        def open(self,req,timeout):
            observed.append(req)
            return Response()
    monkeypatch.setattr(accounts,'build_opener',lambda *args:Opener())
    accounts.request('/fapi/v3/account',{'key':'key','secret':'secret'},123)
    req=observed[0]
    assert req.method=='GET'
    expected=hmac.new(b'secret',b'timestamp=123&recvWindow=5000',hashlib.sha256).hexdigest()
    assert req.full_url.endswith('signature='+expected)
    assert req.get_header('X-mbx-apikey')=='key'
    with pytest.raises(ValueError):accounts.request('/fapi/v1/order',{'key':'key','secret':'secret'},123)
    with pytest.raises(ValueError):accounts.request('https://evil.example')
    assert accounts.NoRedirect().redirect_request(None,None,302,None,None,None) is None


def test_snapshot_maps_hedged_positions_without_leaking_raw_account(monkeypatch):
    def fake(path, *args):
        if path.endswith('/time'):return {'serverTime':123}
        if path.endswith('/account'):return {'totalWalletBalance':'100','privateField':'hidden','assets':[{'asset':'USDT','walletBalance':'100'},{'asset':'BNB','walletBalance':'0'}]}
        return [{'symbol':'BTCUSDT','positionSide':'LONG','positionAmt':'0.1','entryPrice':'100','unRealizedProfit':'2'}, {'symbol':'BTCUSDT','positionSide':'SHORT','positionAmt':'-0.2'}, {'symbol':'ETHUSDT','positionAmt':'0'}]
    monkeypatch.setattr(accounts,'request',fake)
    result=accounts.fetch_account({'key':'fake','secret':'fake'})
    assert len(result['positions'])==2
    assert len(result['assets'])==1
    assert result['totals']['totalWalletBalance']=='100'
    assert 'privateField' not in json.dumps(result)


def test_stale_failure_and_inflight_disconnect(isolated,monkeypatch):
    accounts.configure('K'*64,'S'*64)
    monkeypatch.setattr(accounts,'fetch_account',lambda auth:{'state':'connected','updated_at':time.time()-100,'totals':{'totalWalletBalance':'100'}})
    accounts.sync_once()
    assert accounts.snapshot()['stale']
    def fail(auth):raise RuntimeError('secret signed URL DO NOT LOG')
    monkeypatch.setattr(accounts,'fetch_account',fail)
    accounts.sync_once()
    assert accounts.snapshot()['totals']['totalWalletBalance']=='100'
    assert 'DO NOT LOG' not in json.dumps(accounts.snapshot())
    def race(auth):
        accounts.disconnect()
        return {'state':'connected','totals':{'totalWalletBalance':'100'}}
    monkeypatch.setattr(accounts,'fetch_account',race)
    accounts.sync_once()
    assert accounts.snapshot()['state']=='not_configured'
    assert 'totals' not in accounts.snapshot()


def test_account_rate_limit_backoff(isolated,monkeypatch):
    accounts.configure('K'*64,'S'*64)
    def limited(auth):raise HTTPError('secret-url',429,'secret-message',{},None)
    monkeypatch.setattr(accounts,'fetch_account',limited)
    assert accounts.sync_once()==300
    assert 'secret' not in json.dumps(accounts.snapshot())


def test_market_controls_persist_and_are_authenticated(isolated):
    from labapp import controls
    c=TestClient(web.app,base_url='http://localhost')
    headers={'Origin':'http://localhost'}
    assert c.post('/api/account/market-control',json={'paused':True},headers=headers).status_code==401
    c=client_login()
    assert c.post('/api/account/market-control',json={'symbol':'ETH/USDT','source':'futures','interval':10,'paused':True},headers=headers).status_code==200
    assert controls.read()['symbol']=='ETH/USDT'
    assert store.snapshot()['settings']['paused'] is True
    assert c.post('/api/account/market-control',json={'refresh':True},headers=headers).status_code==400
    assert c.post('/api/account/market-control',json={'source':'https://evil.example'},headers=headers).status_code==400
    assert c.post('/api/account/market-control',json={'live_enabled':True},headers=headers).status_code==400
    c.post('/api/account/market-control',json={'paused':False},headers=headers)
    assert controls.read()['paused'] is False


def test_ai_configuration_encrypted_and_modules_fail_closed(isolated):
    from labapp import integrations
    c=client_login();headers={'Origin':'http://localhost'}
    payload={'key':'fake-test-key-'+'A'*32,'model':'test-model','budget_cny':30}
    r=c.post('/api/account/ai-config',json=payload,headers=headers)
    assert r.status_code==200 and payload['key'] not in r.text
    assert payload['key'].encode() not in (accounts.secret_dir()/'deepseek.enc').read_bytes()
    assert integrations.read()['key']==payload['key']
    assert payload['key'] not in c.get('/api/account/workspace').text
    for module in ('research','training','simulation','live'):
        r=c.post('/api/account/module-action',json={'module':module,'action':'start'},headers=headers)
        assert r.status_code==409 and r.json()['detail']['blockers']
    assert store.snapshot()['live_enabled'] is False
    c.post('/api/account/ai-delete',json={},headers=headers)
    assert integrations.read() is None


def test_descriptive_analysis_persists_without_orders(isolated):
    from labapp import integrations
    with store.connect() as db:
        db.executemany('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?)',[
            ('BTC/USDT','1m',i*60000,i*60000+59999,100,102,99,101,3) for i in range(25)])
    c=client_login()
    r=c.post('/api/account/module-action',json={'module':'analysis','action':'start'},headers={'Origin':'http://localhost'})
    assert r.status_code==200
    assert r.json()['analysis']['sma20']==101
    assert r.json()['analysis']['return_pct']==pytest.approx(1)
    assert integrations.last_analysis()['count']==25
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM order_intents').fetchone()[0]==0
