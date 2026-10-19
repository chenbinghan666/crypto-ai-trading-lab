import json
import time
import pytest
from fastapi.testclient import TestClient
from labapp import store,paper,fast_experiment as exp,fast_runtime


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'STATE',tmp_path);monkeypatch.setattr(store,'LOGS',tmp_path/'logs')
    monkeypatch.setenv('LAB_SECRETS_DIR',str(tmp_path/'secrets'));store.init();paper.init();exp.init()


def test_two_accounts_are_isolated_and_cannot_trade_live(isolated):
    exp.configure(True)
    c=fast_runtime.config('ai');b=fast_runtime.config('rule')
    fast_runtime.validate(c,'ai');fast_runtime.validate(b,'rule')
    assert c['timeframe']==b['timeframe']=='15m'
    assert c['db_url']!=b['db_url'] and str(paper.ledger_path()) not in c['db_url']
    assert c['dry_run_wallet']==b['dry_run_wallet']==1000
    assert c['fee']==b['fee']==.00125 and c['dry_run'] and not c['force_entry_enable']
    assert not c['exchange']['key'] and not c['api_server']['enabled']
    c['dry_run']=False
    with pytest.raises(ValueError):fast_runtime.validate(c,'ai')
    assert not paper.status()['enabled']


def test_restart_pause_dedup_and_no_same_account_replay(isolated):
    exp.configure(True);cohort=exp.state()['cohort']
    assert exp.claim('ai',100,'long') and not exp.claim('ai',100,'long')
    assert exp.claim('rule',100,'long')
    exp.configure(False);assert not exp.claim('ai',200,'long')
    exp.configure(True)
    assert exp.state()['cohort']==cohort and not exp.claim('ai',100,'long')
    s=exp.snapshot();assert not s['live_enabled'] and s['experimental']


def test_route_requires_auth_origin_and_no_risk_overrides(isolated):
    from labapp import web
    c=TestClient(web.app,base_url='http://localhost');origin={'Origin':'http://localhost'}
    assert c.get('/api/account/fast-experiment').status_code==401
    (store.STATE/'frequi-auth.json').write_text(json.dumps({'password':'fast-test-local'}))
    c.post('/api/account/login',json={'password':'fast-test-local'},headers=origin)
    assert c.post('/api/account/fast-experiment-action',json={'enabled':True}).status_code==403
    assert c.post('/api/account/fast-experiment-action',json={'enabled':True,'leverage':10},headers=origin).status_code==400
    assert c.post('/api/account/fast-experiment-action',json={'enabled':True},headers=origin).status_code==200
    assert not paper.status()['enabled']


@pytest.mark.parametrize('arm,prediction,expected',[('rule',0,1),('ai',.004,1),('ai',.002,0)])
def test_ai_filter_and_rule_share_same_trend(arm,prediction,expected,isolated,monkeypatch):
    import numpy as np
    import pandas as pd
    from labapp import fast_model
    from strategies.FuturesFastExperiment import FuturesFastExperiment
    exp.configure(True)
    monkeypatch.setattr(fast_model,'infer',lambda df:(np.full(len(df),prediction),np.ones(len(df))))
    strategy=FuturesFastExperiment(fast_runtime.config(arm))
    df=pd.DataFrame({'date':pd.date_range('2026-01-01',periods=150,freq='15min',tz='UTC'),
        'close':np.arange(150)+100.,'volume':1.})
    result=strategy.populate_entry_trend(strategy.populate_indicators(df,{}),{})
    assert result.iloc[-1].enter_long==expected and result.iloc[-1].enter_short==0
    assert strategy.timeframe=='15m' and strategy.leverage(None,None,None,None,None,None,None)==1


def test_only_fresh_forward_candles_can_create_one_intent(isolated,monkeypatch):
    import pandas as pd
    from types import SimpleNamespace
    from datetime import datetime,timezone,timedelta
    from freqtrade.persistence import Trade
    from strategies.FuturesFastExperiment import FuturesFastExperiment
    exp.configure(True);exp.folder().mkdir(parents=True)
    now=datetime.now(timezone.utc);candle=now-timedelta(seconds=905)
    (exp.folder()/'ready.json').write_text(json.dumps({'start_after':candle.timestamp()-900}))
    c=fast_runtime.config('rule');c['runmode']='dry_run';strategy=FuturesFastExperiment(c)
    strategy.dp=SimpleNamespace(get_analyzed_dataframe=lambda *a:(pd.DataFrame({'date':[pd.Timestamp(candle)]}),None))
    strategy.wallets=SimpleNamespace(get_total_stake_amount=lambda:1000.)
    monkeypatch.setattr(Trade,'get_trades_proxy',lambda **kw:[])
    args=('BTC/USDT:USDT','limit',.002,80000,'GTC',now,'experiment15m_rule','long')
    assert strategy.confirm_trade_entry(*args)
    assert not strategy.confirm_trade_entry(*args)
    (exp.folder()/'ready.json').write_text(json.dumps({'start_after':now.timestamp()}))
    assert not strategy.confirm_trade_entry(*args)


def test_unfilled_order_does_not_create_estimated_loss(isolated,monkeypatch):
    import sqlite3
    exp.configure(True);exp.folder().mkdir(parents=True)
    monkeypatch.setattr(paper,'status',lambda:{'venue':'gate','checks_stale':False,'checks':{'ok':True,'mark_price':10100}})
    with sqlite3.connect(exp.ledger('ai')) as db:
        db.executescript('''CREATE TABLE trades(id INTEGER,is_open INTEGER,is_short INTEGER,open_date TEXT,close_date TEXT,
            open_rate REAL,close_rate REAL,close_profit_abs REAL,amount REAL,enter_tag TEXT,exit_reason TEXT,
            funding_fees REAL,fee_open REAL,fee_close REAL);
            CREATE TABLE orders(id INTEGER,ft_trade_id INTEGER,side TEXT,status TEXT,filled REAL,amount REAL,order_date TEXT);
            INSERT INTO trades VALUES(1,1,0,'2026-10-17',NULL,10000,NULL,NULL,0.01,'test',NULL,0,.00125,.00125);
            INSERT INTO orders VALUES(1,1,'buy','open',0,0.01,'2026-10-17');''')
    assert exp.snapshot()['arms']['ai']['floating_estimate']==0
    with sqlite3.connect(exp.ledger('ai')) as db:db.execute("UPDATE orders SET status='closed',filled=.01")
    assert exp.snapshot()['arms']['ai']['floating_estimate']==pytest.approx(.74875)
