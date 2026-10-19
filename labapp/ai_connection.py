"""Authenticate only against DeepSeek's fixed model-list endpoint. No inference."""
import hashlib
import json
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener
from labapp import integrations, accounts, store
from labapp.network import explain_error


def fingerprint(config):
    return hashlib.sha256((config['key']+'\0'+config['model']).encode()).hexdigest()


def init():
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS ai_validation(id INTEGER PRIMARY KEY CHECK(id=1), fingerprint TEXT, at REAL, payload TEXT)')


def status():
    init()
    config=integrations.read()
    if not config:
        return {'state':'not_configured','message':'请先保存 AI 配置。'}
    with store.connect() as db:
        row=db.execute('SELECT * FROM ai_validation WHERE id=1').fetchone()
    if not row or row['fingerprint']!=fingerprint(config):
        return {'state':'unverified','message':'配置已保存，尚未验证密钥与模型。'}
    return {**json.loads(row['payload']),'checked_at':row['at'],'verification_stale':time.time()-row['at']>86400}


def validate():
    init()
    config=integrations.read()
    if not config:
        raise ValueError('请先保存 AI 配置。')
    identity=fingerprint(config)
    with store.connect() as db:
        old=db.execute('SELECT * FROM ai_validation WHERE id=1').fetchone()
    if old and old['fingerprint']==identity and time.time()-old['at']<30:
        return {**json.loads(old['payload']),'checked_at':old['at']}
    request=Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+config['key'],'User-Agent':'CryptoLab/connection-check'},method='GET')
    try:
        with build_opener(accounts.NoRedirect()).open(request,timeout=10) as response:
            raw=response.read(262145)
            if len(raw)>262144:
                raise ValueError('Oversized model response')
            data=json.loads(raw)
        models=sorted({x['id'] for x in data.get('data',[]) if isinstance(x,dict) and isinstance(x.get('id'),str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,100}',x['id'])})
        if not models:
            raise ValueError('Invalid model response')
        available=config['model'] in models
        result={'state':'verified' if available else 'model_unavailable','authenticated':True,
                'selected_model':config['model'],'available_models':models,'generation_calls':0,
                'message':'密钥验证通过，所选模型可用；未生成内容，未验证账户余额。' if available else '密钥认证通过，但所选模型不在可用列表中。'}
    except HTTPError as exc:
        message='密钥认证失败，请检查 DeepSeek API Key。' if exc.code in (401,403) else 'DeepSeek 模型接口请求失败，请稍后重试。'
        result={'state':'error','http_status':exc.code,'message':message,'generation_calls':0}
    except ValueError:
        result={'state':'error','message':'DeepSeek 返回的模型列表格式异常，验证未通过。','generation_calls':0}
    except Exception as exc:
        result={'state':'error','message':explain_error(exc)[2],'generation_calls':0}
    checked_at=time.time()
    # Do not apply an old in-flight validation after changing/deleting credentials.
    with accounts.LOCK:
        current=integrations.read()
        if not current or fingerprint(current)!=identity:
            return {'state':'unverified','message':'配置在验证期间发生变化，请重新验证。'}
        with store.connect() as db:
            db.execute('INSERT INTO ai_validation VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET fingerprint=excluded.fingerprint,at=excluded.at,payload=excluded.payload',
                       (identity,checked_at,json.dumps(result)))
    return {**result,'checked_at':checked_at}
