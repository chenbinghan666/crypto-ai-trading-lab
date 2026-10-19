import json
import time
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
from importlib import reload
import pytest
from fastapi.testclient import TestClient
from labapp import store,paper,risk_gate,paper_runtime


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'STATE',tmp_path/'state')
    monkeypatch.setattr(store,'LOGS',tmp_path/'logs')
    monkeypatch.setenv('LAB_SECRETS_DIR',str(tmp_path/'secrets'))
    store.init();paper.init()
    return tmp_path


def accepted():
    (store.STATE/'futures-acceptance.json').write_text(json.dumps({'passed':True,'strategy_hash':paper.fingerprint()}))
    with store.connect() as db:
        db.execute('INSERT INTO paper_checks VALUES(1,?,?,?)',(time.time(),1,json.dumps({'ok':True,'message':'test'})))
    store.heartbeat('paper','running')


def test_start_stop_persist_dedup_after_reload(isolated):
    accepted();paper.settings({'capital':1000,'agent_mode':'baseline_fallback'})
    paper.start();paper.start()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results=list(executor.map(lambda _:paper.claim_entry('BTC/USDT:USDT',100,'long'),range(4)))
    assert sum(results)==1
    reload(paper)
    assert paper.status()['enabled']
    assert not paper.claim_entry('BTC/USDT:USDT',100,'long')
    paper.stop();assert not paper.status()['enabled']
    assert not paper.claim_entry('BTC/USDT:USDT',200,'long')


def test_fails_closed_network_stale_and_no_agent(isolated):
    accepted()
    with pytest.raises(ValueError,match='合约 AI'):paper.start()
    paper.settings({'capital':1000,'agent_mode':'baseline_fallback'})
    with store.connect() as db:db.execute('UPDATE paper_checks SET at=?',(time.time()-121,))
    with pytest.raises(ValueError,match='过期'):paper.start()
    assert not paper.status()['enabled']


def test_code_change_invalidates_acceptance(isolated):
    (store.STATE/'futures-acceptance.json').write_text(json.dumps({'passed':True,'strategy_hash':'old'}))
    assert not paper.acceptance()


def test_network_error_sanitized_no_spot_fallback(isolated,monkeypatch):
    def fail(*a,**k):raise TimeoutError('secret-content-do-not-return')
    monkeypatch.setattr(paper,'urlopen',fail)
    result=paper.check_connection()
    assert not result['ok'] and 'secret-content' not in json.dumps(result)
    assert not paper.status()['checks']['ok']


def test_spot_and_expired_ai_rejected(isolated):
    from labapp import research_jobs
    research_jobs.init()
    with store.connect() as db:
        db.execute('INSERT INTO research_jobs VALUES(?,?,?,?,?,?,?,?,?)',('test',time.time(),time.time(),'completed',0,'{}',None,
            json.dumps({'symbol':'BTC/USDT','market_type':'spot_reference','rating':'BUY','cutoff_ms':int(time.time()*1000)}),0))
    with pytest.raises(ValueError,match='现货参考'):paper.approve_research('test')
    with store.connect() as db:
        db.execute('UPDATE research_jobs SET result=?',(json.dumps({'symbol':'BTC/USDT','market_type':'usd_m_futures','rating':'BUY','cutoff_ms':int((time.time()-8000)*1000)}),))
    with pytest.raises(ValueError,match='过期'):paper.approve_research('test')
    assert paper.signal() is None


def record(now,pnl,stake=200,days=0):
    close=now-timedelta(days=days,minutes=2)
    return {'open_date':close-timedelta(hours=1),'close_date':close,'profit':pnl,'stake':stake}


def test_risk_sizes_stop_and_exposure():
    assert risk_gate.stake(1000,1000)==200
    assert risk_gate.stake(10,10,5)==0
    assert risk_gate.stake(float('nan'),1000)==0
    now=datetime(2025,1,10,12,tzinfo=timezone.utc)
    assert risk_gate.check(1000,1000,[],[],now,200)==(True,'allowed')
    assert not risk_gate.check(1000,1000,[],[],now,201)[0]
    assert not risk_gate.check(1000,1000,[],[{}],now,200)[0]
    assert risk_gate.check(1000,970,[record(now,-30)],[],now,190)[1]=='daily_loss_stop'
    assert risk_gate.check(1000,890,[record(now,-110,days=1)],[],now,170)[1]=='drawdown_stop'
    assert risk_gate.check(1000,997,[record(now,-1) for _ in range(3)],[],now,190)[1]=='loss_streak_cooldown'
    assert risk_gate.check(1000,1000,[record(now,0) for _ in range(5)],[],now,200)[1]=='daily_new_risk_limit'


def test_strategy_causal_prefix_and_leverage():
    import numpy as np
    import pandas as pd
    from strategies.FuturesBaseline import FuturesBaseline
    frame=pd.DataFrame({'date':pd.date_range('2025-01-01',periods=200,freq='h',tz='UTC'),
        'open':100+np.sin(np.arange(200)/8)*10,'close':100+np.sin(np.arange(200)/8)*10,
        'high':111,'low':89,'volume':1})
    strategy=FuturesBaseline({'dry_run':True,'trading_mode':'futures'})
    def signals(df):return strategy.populate_exit_trend(strategy.populate_entry_trend(strategy.populate_indicators(df.copy(),{}),{}),{})
    full=signals(frame)
    for end in (80,100,130,160,199):
        prefix=signals(frame.iloc[:end])
        for col in ('enter_long','enter_short','exit_long','exit_short'):
            assert prefix[col].tolist()==full[col].iloc[:end].tolist()
    assert strategy.leverage(None,None,None,100,125,None,'long')==1
    with pytest.raises(RuntimeError):FuturesBaseline({'dry_run':False,'trading_mode':'futures'}).bot_start()


def test_ccxt_blocks_private_and_posts(monkeypatch):
    import ccxt
    import ccxt.async_support as async_ccxt
    import ccxt.pro as pro
    originals=[(cls,cls.sign) for cls in (ccxt.binance,async_ccxt.binance,pro.binance,ccxt.gate,async_ccxt.gate,pro.gate)]
    try:
        paper_runtime.public_only();client=ccxt.binance()
        for api,method in [('fapiPrivate','GET'),('fapiPrivate','POST'),('fapiPublic','POST')]:
            with pytest.raises(RuntimeError):client.sign('order',api,method,{})
        result=client.sign('time','fapiPublic','GET',{})
        assert result['url'].startswith('https://fapi.binance.com/')
        gate=ccxt.gate()
        with pytest.raises(RuntimeError):gate.sign('{settle}/orders',['private','futures'],'POST',{'settle':'usdt'})
        with pytest.raises(RuntimeError):gate.sign('time',['public','spot'],'POST',{})
        assert 'gateio.ws' in gate.sign('time',['public','spot'],'GET',{})['url']
        sign=ccxt.gate.sign;paper_runtime.public_only();assert ccxt.gate.sign is sign
    finally:
        # Other async classes are only exercised by isolated child processes.
        for cls,original in originals:monkeypatch.setattr(cls,'sign',original)


def test_worker_singleton_prevents_cli_duplicate(isolated):
    lock=paper_runtime.acquire_worker_lock()
    try:
        with pytest.raises(RuntimeError,match='already running'):paper_runtime.acquire_worker_lock()
    finally:lock.close()
    paper_runtime.acquire_worker_lock().close()


def test_no_credentials_and_unsafe_override_rejected(monkeypatch):
    c=paper_runtime.config();paper_runtime.validate(c)
    c['dry_run']=False
    with pytest.raises(ValueError):paper_runtime.validate(c)
    c=paper_runtime.config();c['exchange']['key']='private-key'
    with pytest.raises(ValueError):paper_runtime.validate(c)
    monkeypatch.setenv('FREQTRADE__DRY_RUN','false')
    with pytest.raises(ValueError):paper_runtime.validate(paper_runtime.config())


def test_paper_routes_auth_csrf_and_live_blocked(isolated):
    from labapp import web
    c=TestClient(web.app,base_url='http://localhost')
    assert c.get('/api/account/paper').status_code==401
    assert c.post('/api/account/paper-action',json={'action':'start'},headers={'Origin':'http://localhost'}).status_code==401
    (store.STATE/'frequi-auth.json').write_text(json.dumps({'password':'local-test-password'}))
    assert c.post('/api/account/login',json={'password':'local-test-password'},headers={'Origin':'http://localhost'}).status_code==200
    assert c.post('/api/account/paper-action',json={'action':'settings','capital':1000}).status_code==403
    headers={'Origin':'http://localhost'}
    assert c.post('/api/account/paper-action',json={'action':'start'},headers=headers).status_code==409
    assert c.post('/api/account/module-action',json={'module':'live','action':'start'},headers=headers).status_code==409
    assert not c.get('/api/status').json()['paper_enabled']
    assert not c.get('/api/status').json()['live_enabled']


def test_backtest_queue_idempotent_and_cancel(isolated):
    store.heartbeat('paper','running')
    paper.enqueue('prepare')
    with pytest.raises(ValueError):paper.enqueue('prepare')
    paper.cancel_job()
    assert paper.status()['job']['cancel']==1


def test_sim_ledger_is_separate_from_backtest_and_real_account(isolated):
    assert paper.status()['trades']==[] and paper.status()['orders']==0
    assert not (store.STATE/'futures-paper.sqlite').exists()
    assert not paper.status()['enabled']


def test_gate_selection_separates_ledger_and_stale_check(isolated):
    accepted()
    paper.settings({'capital':1000,'agent_mode':'baseline_fallback','venue':'gate'})
    assert paper.status()['checks_stale']
    assert paper.ledger_path().name=='futures-paper-gate.sqlite'
    c=paper_runtime.config(1000,'gate');paper_runtime.validate(c)
    assert c['exchange']['key']=='' and c['fee']==0.00075
    assert c['order_types']['entry']=='limit' and c['dry_run'] is True
    assert not paper.status()['enabled']
    paper.init();assert paper.status()['venue']=='gate'
