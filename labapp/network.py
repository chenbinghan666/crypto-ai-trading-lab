"""Public-only network diagnostics; never changes DNS, proxies, or TLS checks."""
import json
import socket
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


def explain_error(exc):
    if isinstance(exc, HTTPError):
        if exc.code == 451:
            return 'region_restricted','http','接口明确拒绝当前地区访问，请确认币安服务在账户及网络所在地区的可用性。'
        if exc.code in (418,429):
            return 'rate_limited','http','接口限流，请等待退避重试。'
        if exc.code in (401,403):
            return 'http_rejected','http','请求已到达接口，但被拒绝；检查访问限制。'
        return 'http_error','http',f'接口返回 HTTP {exc.code}，请稍后重试。'
    reason=exc.reason if isinstance(exc,URLError) else exc
    if isinstance(reason,socket.gaierror):
        return 'dns_failed','dns','DNS 解析失败：当前运行环境未取得币安域名的有效地址，请联系网络管理员或运营商核查解析与访问策略。'
    if isinstance(reason,ssl.SSLCertVerificationError):
        return 'tls_certificate_failed','tls','HTTPS 证书验证失败：检查系统时间、证书和网络拦截情况。'
    if isinstance(reason,ssl.SSLError):
        return 'tls_failed','tls','HTTPS 握手失败：检查网络连接及 TLS 支持。'
    if isinstance(reason,(TimeoutError,socket.timeout)):
        return 'connection_timeout','connection','连接超时：域名已解析，但 HTTPS 未在时限内完成；检查防火墙和网络访问策略。'
    return 'connection_failed','connection','网络连接失败，请检查运行环境的网络可达性。'


def probe(item):
    name,url=item
    host=urlsplit(url).hostname
    started=time.monotonic()
    addresses=[]
    try:
        addresses=sorted({r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})
        with urlopen(url,timeout=5) as response:
            payload=json.loads(response.read(4096))
            if not isinstance(payload,dict) or not isinstance(payload.get('serverTime'),int):
                return {'name':name,'host':host,'ok':False,'code':'invalid_response','phase':'response',
                        'message':'收到的响应不是预期的币安时间数据，连接未通过验证。','addresses':addresses,
                        'latency_ms':round((time.monotonic()-started)*1000)}
        result={'ok':True,'code':'ok','phase':'complete','message':'DNS 解析、HTTPS 证书及币安时间响应验证通过。'}
    except Exception as exc:
        code,phase,message=explain_error(exc)
        # Do not return raw exceptions, signed URLs, request headers or credentials.
        result={'ok':False,'code':code,'phase':phase,'message':message}
        if isinstance(exc,HTTPError):
            result['http_status']=exc.code
    return {**result,'name':name,'host':host,'addresses':addresses,
            'latency_ms':round((time.monotonic()-started)*1000)}
