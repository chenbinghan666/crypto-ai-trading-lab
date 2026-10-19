import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
import pytest
from labapp import store,integrations,ai_connection,ai_costs,research_jobs
from labapp.research_gateway import Gateway


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'STATE',tmp_path/'state')
    monkeypatch.setattr(store,'LOGS',tmp_path/'logs')
    monkeypatch.setenv('LAB_SECRETS_DIR',str(tmp_path/'secrets'))
    monkeypatch.setattr(ai_costs,'_dates',lambda:('2026-10','2026-10-16'))
    store.init()
    integrations.save({'key':'fake-test-key-'+'K'*32,'model':'deepseek-v4-pro','budget_cny':50})
    return tmp_path


def fake_models(monkeypatch,ids=None):
    ids=ids or ['deepseek-v4-pro','deepseek-flash']
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return json.dumps({'data':[{'id':i} for i in ids]}).encode()
    class Opener:
        def open(self,request,timeout):
            assert request.method=='GET' and request.full_url=='https://api.deepseek.com/models'
            return Response()
    monkeypatch.setattr(ai_connection,'build_opener',lambda *args:Opener())


def test_key_verification_is_get_only_and_never_echoes_key(isolated,monkeypatch):
    fake_models(monkeypatch)
    result=ai_connection.validate()
    assert result['state']=='verified' and result['generation_calls']==0
    assert integrations.read()['key'] not in json.dumps(result)
    assert ai_connection.status()['state']=='verified'
    integrations.save({'key':'different-fake-key-'+'K'*32,'model':'deepseek-v4-pro','budget_cny':50})
    assert ai_connection.status()['state']=='unverified'


def test_invalid_model_cannot_start_research(isolated,monkeypatch):
    fake_models(monkeypatch,['deepseek-flash'])
    assert ai_connection.validate()['state']=='model_unavailable'
    assert research_jobs.blockers()


def test_conservative_prices_and_cached_usage(isolated):
    assert ai_costs.quote_micro('deepseek-v4-pro',1000,100)==11700
    assert ai_costs.quote_micro('deepseek-v4-pro',1000,100,500)==7350
    with pytest.raises(ValueError):ai_costs.quote_micro('unpriced-model',1,1)
    with pytest.raises(ValueError):ai_costs.quote_micro('deepseek-v4-pro',1,-1)


def test_duplicate_and_unknown_requests_survive_reopen(isolated):
    ai_costs.reserve('one','deepseek-v4-pro',1000,100)
    ai_costs.mark_unknown('one')
    assert ai_costs.summary()['reserved_cny']==pytest.approx(.0117)
    with pytest.raises(ValueError):ai_costs.reserve('one','deepseek-v4-pro',1000,100)
    ai_costs.settle('one',1000,100)
    assert ai_costs.summary()['reserved_cny']==0
    assert ai_costs.summary()['spent_cny']==pytest.approx(.0117)
    with pytest.raises(ValueError):ai_costs.settle('one',1000,100)


def test_daily_budget_is_atomic_under_concurrency(isolated):
    def attempt(i):
        try:ai_costs.reserve(str(i),'deepseek-v4-pro',50000,1000);return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert sum(pool.map(attempt,range(3)))==2
    assert ai_costs.summary()['reserved_cny']==pytest.approx(.954)


def test_per_run_and_expired_prices_fail_closed(isolated,monkeypatch):
    ai_costs.reserve('run:1','deepseek-v4-pro',40000,1000,run_id='run')
    with pytest.raises(ValueError):ai_costs.reserve('run:2','deepseek-v4-pro',40000,1000,run_id='run')
    monkeypatch.setattr(ai_costs,'_dates',lambda:('2026-10','2026-10-24'))
    with pytest.raises(ValueError):ai_costs.reserve('new','deepseek-v4-pro',1,1)


def test_research_queue_prevents_duplicates_and_recovers_running(isolated,monkeypatch):
    fake_models(monkeypatch);ai_connection.validate()
    store.heartbeat('research','running','test')
    now=time.time();start=int(now//60)*60000-30*60000
    with store.connect() as db:
        db.execute('INSERT INTO quotes VALUES(?,?,?)',('BTC/USDT',now,json.dumps({'mid':100,'source':'https://data-api.binance.vision/api/v3/','market_type':'spot_reference'})))
        db.executemany('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?)',[
            ('BTC/USDT','1m',start+i*60000,start+i*60000+59999,100,102,99,101,3) for i in range(25)])
    job=research_jobs.create()
    assert job['state']=='queued'
    with pytest.raises(ValueError):research_jobs.create()
    with store.connect() as db:db.execute("UPDATE research_jobs SET state='running' WHERE id=?",(job['id'],))
    research_jobs.recover()
    assert research_jobs.latest()['state']=='interrupted'
    assert store.snapshot()['live_enabled'] is False


def test_gateway_enforces_caps_and_records_real_usage(isolated):
    research_jobs.init()
    with store.connect() as db:
        db.execute('INSERT INTO research_jobs VALUES(?,?,?,?,?,?,?,?,?)',('test',time.time(),time.time(),'running',0,'{}',None,None,0))
    captured=[]
    def transport(body,key):
        captured.append(body)
        return {'usage':{'prompt_tokens':100,'completion_tokens':20}}
    config=integrations.read()
    with Gateway('test',config['model'],ai_connection.fingerprint(config),transport=transport) as gate:
        gate.complete({'model':config['model'],'messages':[{'role':'user','content':'test'}],'max_tokens':50000,'max_completion_tokens':50000})
    assert captured[0]['max_tokens']==512 and captured[0]['reasoning_effort']=='none'
    assert 'max_completion_tokens' not in captured[0]
    assert ai_costs.summary()['spent_cny']==pytest.approx(.00144)
