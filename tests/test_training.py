import json
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from labapp import store,training,training_runner
from strategies.FreqaiCpuResearch import features,HORIZON


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'STATE',tmp_path/'state');monkeypatch.setattr(store,'LOGS',tmp_path/'logs')
    monkeypatch.setenv('LAB_SECRETS_DIR',str(tmp_path/'secrets'));store.init();training.init()
    return tmp_path


def candles(count=1000):
    close=100+np.sin(np.arange(count)/12)*3+np.arange(count)*.001
    return pd.DataFrame({'date':pd.date_range('2025-01-01',periods=count,freq='h',tz='UTC'),
        'open':close,'high':close+1,'low':close-1,'close':close,'volume':np.arange(count)%24+1.0})


def test_feature_causality_and_purged_time_split():
    frame=candles();full=features(frame)
    for end in (80,300,700):
        prefix=features(frame.iloc[:end]);pd.testing.assert_frame_equal(prefix,full.iloc[:end])
    train,test,cols=training_runner.partition(frame)
    assert train.date.iloc[-1]+pd.Timedelta(hours=HORIZON)<test.date.iloc[0]
    assert all(c.startswith('%') and '&' not in c for c in cols)
    with pytest.raises(ValueError):training_runner.partition(candles(100))


def test_jobs_dedup_cancel_and_recovery(isolated):
    store.heartbeat('training','running')
    def enqueue(_):
        try:return training.enqueue('gate')['id']
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(enqueue,range(3)))
    assert sum(bool(x) for x in results)==1
    training.cancel();assert training.latest()['cancel']==1
    with store.connect() as db:db.execute("UPDATE training_jobs SET state='running'")
    training.recover();assert training.latest()['state']=='interrupted'


def test_freqai_train_save_reload_without_network_or_trading(isolated,monkeypatch):
    monkeypatch.setattr(training_runner,'load_data',lambda source:(candles(),{'venue':'gate','kind':'synthetic_test_only'}))
    result=training_runner.execute('offline-test','gate')
    assert result['reload_verified'] and result['trading_enabled'] is False
    assert result['paid_ai_calls']==0 and result['train_rows']>=600
    assert result['test_rows']>=150 and result['threads']==2
    assert 0<=result['direction_accuracy']<=1
    assert 'cpu_lightgbm_model.joblib' in result['artifacts']
    assert not (store.STATE/'futures-paper-gate.sqlite').exists()
    assert not (store.STATE/'futures-paper.sqlite').exists()


def test_training_routes_auth_csrf_and_manual_only(isolated):
    from labapp import web
    c=TestClient(web.app,base_url='http://localhost');origin={'Origin':'http://localhost'}
    assert c.get('/api/account/training').status_code==401
    assert c.post('/api/account/training-action',json={'action':'start'},headers=origin).status_code==401
    (store.STATE/'frequi-auth.json').write_text(json.dumps({'password':'local-training-test'}))
    assert c.post('/api/account/login',json={'password':'local-training-test'},headers=origin).status_code==200
    assert c.post('/api/account/training-action',json={'action':'start'}).status_code==403
    assert c.post('/api/account/training-action',json={'action':'start'},headers=origin).status_code==409
    store.heartbeat('training','running')
    assert c.post('/api/account/training-action',json={'action':'start','source':'evil'},headers=origin).status_code==409
    assert c.post('/api/account/training-action',json={'action':'start','source':'gate'},headers=origin).status_code==200
    assert c.get('/api/account/training').json()['job']['state']=='queued'
    assert c.post('/api/account/training-action',json={'action':'stop'},headers=origin).status_code==200
    assert c.get('/api/status').json()['live_enabled'] is False
