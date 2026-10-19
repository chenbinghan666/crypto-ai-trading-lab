import json
import time
import pytest
from fastapi.testclient import TestClient
from labapp import store,optimizer,paper,training,research_jobs


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'STATE',tmp_path/'state');monkeypatch.setattr(store,'LOGS',tmp_path/'logs')
    monkeypatch.setenv('LAB_SECRETS_DIR',str(tmp_path/'secrets'));store.init();paper.init();optimizer.init();training.init()
    return tmp_path


@pytest.mark.parametrize('bad',[{'fast':1},dict(optimizer.BASE,leverage=10),dict(optimizer.BASE,fast=True),
    dict(optimizer.BASE,slow=1000),dict(optimizer.BASE,prediction_threshold=float('nan')),
    dict(optimizer.BASE,model_filter='yes'),dict(optimizer.BASE,prediction_threshold=.002)])
def test_untrusted_ai_cannot_change_risk_or_code(bad):
    with pytest.raises(ValueError):optimizer.validate_params(bad)


def metrics(profit=4,trades=8,drawdown=.002):
    return {w:{'profit':profit,'trades':trades,'drawdown':drawdown} for w in ('validation','holdout')}


def test_only_costed_unseen_better_candidate_passes():
    assert optimizer.judge(metrics(),metrics(1),{},optimizer.BASE)[0]
    assert not optimizer.judge(metrics(-1),metrics(-5),{},optimizer.BASE)[0]
    assert not optimizer.judge(metrics(trades=2),metrics(1),{},optimizer.BASE)[0]
    assert not optimizer.judge(metrics(drawdown=.06),metrics(1),{},optimizer.BASE)[0]
    p=dict(optimizer.BASE,model_filter=True)
    assert not optimizer.judge(metrics(),metrics(1),{'beats_zero_baseline':False},p)[0]
    assert not optimizer.judge(metrics(float('nan')),metrics(),{},optimizer.BASE)[0]


def candidate():
    with store.connect() as db:
        db.execute("INSERT INTO optimizer_runs VALUES('candidate',?,'running','test',0,NULL,NULL,NULL)",(time.time(),))
    optimizer.configure(True)
    optimizer.propose_version('candidate',{'fast':10,'slow':40,'model_filter':False,'prediction_threshold':0},None,
        {'passed':True,'candidate':metrics(),'incumbent':metrics(1),'model_metrics':{}},100,'baseline')


def test_auto_promotion_waits_flat_and_does_not_start_sim(isolated,monkeypatch):
    candidate()
    monkeypatch.setattr(paper,'status',lambda:{'venue':'gate','open_trades':1,'trades':[],'capital':1000})
    optimizer.reconcile();assert optimizer.active()['id']=='baseline'
    monkeypatch.setattr(paper,'status',lambda:{'venue':'gate','open_trades':0,'trades':[],'capital':1000})
    optimizer.reconcile();assert optimizer.active()['id']=='candidate'
    with store.connect() as db:assert db.execute('SELECT enabled FROM paper_control').fetchone()[0]==0


def test_pause_blocks_promotion_and_rollback_preserves_risk(isolated,monkeypatch):
    candidate();optimizer.configure(False)
    monkeypatch.setattr(paper,'status',lambda:{'venue':'gate','open_trades':0,'trades':[],'capital':1000})
    optimizer.reconcile();assert optimizer.active()['id']=='baseline'
    optimizer.configure(True);optimizer.reconcile();assert optimizer.active()['id']=='candidate'
    monkeypatch.setattr(paper,'status',lambda:{'venue':'gate','open_trades':0,'capital':1000,
        'trades':[{'id':i,'is_open':False,'close_profit_abs':-4} for i in range(1,4)]})
    optimizer.reconcile();assert optimizer.active()['id']=='baseline'


def test_stale_candidate_never_applied(isolated,monkeypatch):
    candidate()
    with store.connect() as db:db.execute("UPDATE optimizer_versions SET at=? WHERE id='candidate'",(time.time()-49*3600,))
    monkeypatch.setattr(paper,'status',lambda:{'venue':'gate','open_trades':0,'trades':[],'capital':1000})
    optimizer.reconcile();assert optimizer.active()['id']=='baseline' and optimizer.status()['pending'] is None


def test_optimizer_routes_auth_origin_no_live_or_budget_override(isolated):
    from labapp import web
    c=TestClient(web.app,base_url='http://localhost');origin={'Origin':'http://localhost'}
    assert c.get('/api/account/optimizer').status_code==401
    (store.STATE/'frequi-auth.json').write_text(json.dumps({'password':'optimizer-test-local'}))
    assert c.post('/api/account/login',json={'password':'optimizer-test-local'},headers=origin).status_code==200
    assert c.post('/api/account/optimizer-action',json={'enabled':True}).status_code==403
    assert c.post('/api/account/optimizer-action',json={'enabled':True,'leverage':5},headers=origin).status_code==400
    assert c.post('/api/account/optimizer-action',json={'enabled':True},headers=origin).status_code==200
    assert optimizer.status()['enabled'] and not paper.status()['enabled']
    assert c.get('/api/status').json()['live_enabled'] is False


def test_failed_metrics_cannot_be_marked_accepted(isolated):
    candidate()
    with pytest.raises(ValueError):
        optimizer.propose_version('candidate',optimizer.BASE,None,
            {'passed':True,'candidate':metrics(-5),'incumbent':metrics(-10),'model_metrics':{}},200,'baseline')


def test_forward_refresh_waits_for_unseen_data_and_verifies_hashes(isolated,monkeypatch):
    import hashlib
    import pandas as pd
    from labapp import optimizer_data
    folder=store.STATE/'optimizer/runs/forward';fresh=store.STATE/'optimizer/runs/refresh'
    dates=pd.date_range('2026-01-01',periods=48,freq='h',tz='UTC')
    def save(root,days):
        (root/'futures').mkdir(parents=True,exist_ok=True);hashes={}
        for kind in ('futures','mark','funding_rate'):
            ds=days[days.hour%8==0] if kind=='funding_rate' else days
            frame=pd.DataFrame({'date':ds,'open':100.,'high':101.,'low':99.,'close':100.,'volume':1.})
            path=root/'futures'/f'BTC_USDT_USDT-1h-{kind}.feather';frame.to_feather(path)
            hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes
    hashes=save(folder,dates[:24]);save(fresh,dates[:40])
    manifest={'files':hashes,'holdout_end':dates[-1].timestamp()+3600}
    (folder/'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(optimizer_data,'freeze',lambda _: (fresh,{},None))
    assert not optimizer_data.refresh_forward('forward')
    assert optimizer_data.verify(folder)['files']==hashes
    save(fresh,dates)
    assert optimizer_data.refresh_forward('forward')
    result=optimizer_data.verify(folder)
    assert result['files']!=hashes
    assert len(pd.read_feather(folder/'futures/BTC_USDT_USDT-1h-futures.feather'))==48
    with (folder/'futures/BTC_USDT_USDT-1h-mark.feather').open('ab') as f:f.write(b'corrupt')
    with pytest.raises(ValueError):optimizer_data.verify(folder)


def test_deferred_candidate_does_not_reissue_paid_research(isolated,monkeypatch):
    from labapp import optimizer_runner,optimizer_data
    candidate()
    folder=store.STATE/'optimizer/runs/candidate';folder.mkdir(parents=True)
    (folder/'proposal.json').write_text(json.dumps({'parent':'baseline','params':optimizer.BASE}))
    monkeypatch.setattr(optimizer_data,'verify',lambda _: {'holdout_end':time.time()+14*86400})
    monkeypatch.setattr(optimizer_data,'refresh_forward',lambda _:False)
    monkeypatch.setattr(research_jobs,'create_optimization',lambda *a:pytest.fail('Paid research reissued'))
    optimizer_runner.main('candidate')
    assert optimizer.status()['run']['state']=='waiting_forward'
    assert not paper.status()['enabled']


def test_idle_restart_does_not_overwrite_completed_status(isolated):
    candidate();optimizer.finish('candidate','rejected',{'passed':False})
    before=optimizer.status()['message']
    optimizer.finish('candidate','interrupted',error='service stopped')
    assert optimizer.status()['message']==before
    assert optimizer.status()['run']['state']=='rejected'
