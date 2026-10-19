import json
import time
import pytest
from labapp import store, platforms, integrations


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'STATE',tmp_path/'state')
    monkeypatch.setattr(store,'LOGS',tmp_path/'logs')
    store.init()


def test_installed_is_not_confused_with_running_or_enabled(isolated):
    (store.STATE/'deployment-tradingagents.json').write_text(json.dumps({
        'installed':True,'version':'0.6.0','graph_compiled':True,'checked_at':time.time()}))
    status=platforms.status()
    assert status['tradingagents']['installed']
    assert not status['tradingagents']['online']
    assert not status['tradingagents']['execution_enabled']
    store.heartbeat('research','running','test')
    assert platforms.status()['tradingagents']['online']
    assert not platforms.status()['live_enabled']
    assert not integrations.readiness()['simulation']['ready']


def test_missing_or_invalid_manifest_never_claims_deployed(isolated):
    assert not platforms.status()['tradingagents']['installed']
    (store.STATE/'deployment-tradingagents.json').write_text('invalid')
    assert not platforms.status()['tradingagents']['installed']
