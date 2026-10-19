import json
import socket
import ssl
from urllib.error import HTTPError, URLError

import pytest
from labapp import network


@pytest.mark.parametrize('error,code',[
    (URLError(socket.gaierror(-2,'sensitive details')),'dns_failed'),
    (URLError(TimeoutError('sensitive details')),'connection_timeout'),
    (URLError(ssl.SSLCertVerificationError('sensitive details')),'tls_certificate_failed'),
    (HTTPError('sensitive-url',451,'sensitive details',{},None),'region_restricted'),
    (HTTPError('sensitive-url',429,'sensitive details',{},None),'rate_limited'),
])
def test_network_errors_are_specific_and_sanitized(error,code):
    result=network.explain_error(error)
    assert result[0]==code
    assert 'sensitive' not in json.dumps(result)


def test_dns_failure_does_not_attempt_https(monkeypatch):
    def fail(*args,**kwargs):raise socket.gaierror(-2,'offline')
    def forbidden(*args,**kwargs):raise AssertionError('DNS failure should stop before HTTPS')
    monkeypatch.setattr(network.socket,'getaddrinfo',fail)
    monkeypatch.setattr(network,'urlopen',forbidden)
    result=network.probe(('合约','https://fapi.binance.com/fapi/v1/time'))
    assert result['code']=='dns_failed' and result['addresses']==[]


@pytest.mark.parametrize('payload,ok',[(b'{"serverTime":123}',True),(b'{"unexpected":"page"}',False)])
def test_probe_requires_binance_time_response(monkeypatch,payload,ok):
    monkeypatch.setattr(network.socket,'getaddrinfo',lambda *args,**kwargs:[(0,0,0,'',('192.0.2.1',443))])
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return payload
    monkeypatch.setattr(network,'urlopen',lambda *args,**kwargs:Response())
    assert network.probe(('test','https://fapi.binance.com/fapi/v1/time'))['ok'] is ok
