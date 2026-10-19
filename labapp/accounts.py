"""Local encrypted credentials and a strictly GET-only USD-M account reader.

No trading client, order endpoint, or credential access by Freqtrade exists here.
"""
import hashlib
import hmac
import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from cryptography.fernet import Fernet
from labapp import store
from labapp.network import explain_error

INTERVAL = 30
LOCK = threading.RLock()
WAKE = threading.Event()
STOP = threading.Event()
REVISION = 0
CACHE = {'state': 'not_configured'}
ALLOWED = {'/fapi/v1/time', '/fapi/v3/account', '/fapi/v3/positionRisk'}


def secret_dir():
    path = Path(os.environ.get('LAB_SECRETS_DIR', Path.home()/'.local/share/crypto-ai-trading-lab/secrets'))
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def cipher():
    path = secret_dir()/'vault.key'
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, 'wb') as f:
            f.write(Fernet.generate_key())
    return Fernet(path.read_bytes())


def credentials():
    path = secret_dir()/'binance.enc'
    return json.loads(cipher().decrypt(path.read_bytes())) if path.exists() else None


def configure(key, secret):
    global REVISION, CACHE
    if not all(isinstance(x, str) and re.fullmatch(r'[A-Za-z0-9]{16,256}', x) for x in (key, secret)):
        raise ValueError('请输入有效的 Binance HMAC API Key 和 Secret；本版本不支持 RSA/Ed25519。')
    with LOCK:
        encrypted = cipher().encrypt(json.dumps({'key':key, 'secret':secret}).encode())
        path = secret_dir()/'binance.enc'
        temp = path.with_suffix('.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(encrypted)
        temp.replace(path)
        REVISION += 1
        CACHE = {'state':'connecting', 'configured':True}
        WAKE.set()


def disconnect():
    global REVISION, CACHE
    with LOCK:
        (secret_dir()/'binance.enc').unlink(missing_ok=True)
        REVISION += 1
        CACHE = {'state':'not_configured', 'configured':False}
        WAKE.set()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(path, auth=None, timestamp=None):
    if path not in ALLOWED or (path != '/fapi/v1/time' and auth is None):
        raise ValueError('Endpoint not allowed')
    headers = {'User-Agent':'CryptoLab/read-only'}
    query = ''
    if auth:
        query = urlencode({'timestamp':timestamp, 'recvWindow':5000})
        query += '&signature=' + hmac.new(auth['secret'].encode(), query.encode(), hashlib.sha256).hexdigest()
        headers['X-MBX-APIKEY'] = auth['key']
    req = Request('https://fapi.binance.com'+path+('?' + query if query else ''), headers=headers, method='GET')
    # Never forward authenticated requests through an HTTP redirect.
    with build_opener(NoRedirect()).open(req, timeout=10) as response:
        return json.load(response)


def fetch_account(auth):
    clock = int(request('/fapi/v1/time')['serverTime'])
    started = time.monotonic()
    account = request('/fapi/v3/account', auth, clock)
    positions = request('/fapi/v3/positionRisk', auth, clock+int((time.monotonic()-started)*1000))
    fields = ('totalWalletBalance','totalUnrealizedProfit','totalMarginBalance','availableBalance',
              'totalInitialMargin','totalMaintMargin','totalPositionInitialMargin','totalOpenOrderInitialMargin')
    asset_fields = ('asset','walletBalance','unrealizedProfit','marginBalance','availableBalance')
    position_fields = ('symbol','positionSide','positionAmt','entryPrice','breakEvenPrice','markPrice',
                       'unRealizedProfit','liquidationPrice','notional','isolatedMargin','initialMargin','maintMargin','marginAsset')
    return {'totals':{k:account.get(k) for k in fields},
            'assets':[{k:a.get(k) for k in asset_fields} for a in account.get('assets',[]) if float(a.get('walletBalance',0)) or float(a.get('unrealizedProfit',0))],
            'positions':[{k:p.get(k) for k in position_fields} for p in positions if float(p.get('positionAmt',0))],
            'updated_at':time.time(), 'state':'connected', 'configured':True,
            'scope':'USD-M', 'read_only':True}


def error_message(exc):
    if isinstance(exc, HTTPError):
        if exc.code in (401,403):
            return '币安拒绝访问：检查 API 读取权限、IP 白名单及账户所在地区的服务可用性。'
        if exc.code in (418,429):
            return '币安请求限流，已暂停请求并退避重试。'
        if exc.code == 400:
            return '币安请求验证失败：检查 HMAC 密钥、合约权限和本机时间。'
        if exc.code == 451:
            return '币安合约服务在当前网络所在地区不可用。'
        return '币安账户接口暂不可用，请稍后重试。'
    return explain_error(exc)[2]


def sync_once():
    global CACHE
    with LOCK:
        revision = REVISION
        try:
            auth = credentials()
        except Exception:
            CACHE = {'state':'error','configured':True,'error':'本机密钥无法解密，请解除绑定后重新配置。'}
            return INTERVAL
        if not auth:
            CACHE = {'state':'not_configured', 'configured':False}
            return INTERVAL
    delay = INTERVAL
    try:
        result = fetch_account(auth)
    except Exception as exc:
        if isinstance(exc, HTTPError) and exc.code in (418,429):
            delay = 300
        with LOCK:
            result = {**CACHE, 'state':'error','configured':True,'error':error_message(exc)}
    with LOCK:
        if revision == REVISION:
            CACHE = {**result, 'next_poll_at':time.time()+delay}
    return delay


def snapshot():
    with LOCK:
        data = dict(CACHE)
    age = time.time()-data['updated_at'] if data.get('updated_at') else None
    return {**data, 'age_seconds':age, 'stale':age is None or age > 65, 'interval':INTERVAL}


def run():
    while not STOP.is_set():
        WAKE.clear()
        delay = sync_once()
        WAKE.wait(delay)


def start():
    STOP.clear()
    thread = threading.Thread(target=run, name='read-only-account', daemon=True)
    thread.start()
    return thread
