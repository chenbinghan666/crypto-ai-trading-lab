import os
import time
import json
import secrets
import hmac
from contextlib import asynccontextmanager
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool
import uvicorn

from labapp.store import ROOT, init, snapshot
from labapp import accounts, store, controls, integrations, platforms, ai_connection, ai_costs, research_jobs
from labapp import paper
from labapp import training
from labapp import optimizer


@asynccontextmanager
async def lifespan(app):
    thread = accounts.start()
    yield
    accounts.STOP.set()
    accounts.WAKE.set()
    thread.join(timeout=35)

app = FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','[::1]'])
SESSIONS = {}
ATTEMPTS = deque()


@app.middleware('http')
async def private_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    if request.url.path.startswith('/api/account'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def authenticated(request):
    token = request.cookies.get('lab_session','')
    if SESSIONS.get(token,0) < time.time():
        SESSIONS.pop(token,None)
        raise HTTPException(401,'请先使用本机管理密码解锁账户面板。')


def same_origin(request):
    if request.headers.get('origin') != str(request.base_url).rstrip('/'):
        raise HTTPException(403,'仅允许本机管理页面提交。')


async def body(request):
    if request.headers.get('content-type','').split(';')[0] != 'application/json':
        raise HTTPException(415,'请使用 JSON 请求。')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(413,'请求过大。')
    try:
        data = json.loads(raw)
        if not isinstance(data,dict):
            raise ValueError()
        return data
    except Exception:
        raise HTTPException(400,'请求格式错误。') from None


@app.post('/api/account/login')
async def login(request: Request):
    same_origin(request)
    now = time.time()
    while ATTEMPTS and now-ATTEMPTS[0] > 60:
        ATTEMPTS.popleft()
    if len(ATTEMPTS) >= 5:
        raise HTTPException(429,'尝试过于频繁，请一分钟后再试。')
    ATTEMPTS.append(now)
    data = await body(request)
    try:
        expected = json.loads((store.STATE/'frequi-auth.json').read_text())['password']
    except Exception:
        raise HTTPException(503,'本机管理密码尚未生成，请等待 FreqUI 服务启动。') from None
    password = data.get('password')
    if not isinstance(password,str) or not hmac.compare_digest(password.encode(),expected.encode()):
        raise HTTPException(401,'管理密码不正确。')
    for token, expires in list(SESSIONS.items()):
        if expires < now:
            SESSIONS.pop(token,None)
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = now+3600
    response = JSONResponse({'ok':True})
    response.set_cookie('lab_session',token,httponly=True,samesite='strict',max_age=3600,secure=request.url.scheme=='https',path='/api/account')
    return response


@app.post('/api/account/logout')
def logout(request: Request):
    same_origin(request)
    SESSIONS.pop(request.cookies.get('lab_session',''),None)
    response = JSONResponse({'ok':True})
    response.delete_cookie('lab_session',path='/api/account')
    return response


@app.get('/api/account')
def account_status(request: Request):
    authenticated(request)
    return accounts.snapshot()


@app.post('/api/account/connect')
async def account_connect(request: Request):
    same_origin(request)
    authenticated(request)
    data = await body(request)
    try:
        accounts.configure(data.get('key'),data.get('secret'))
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from None
    return {'ok':True,'message':'密钥已在本机加密保存，正在进行只读连接验证。'}


@app.post('/api/account/disconnect')
def account_disconnect(request: Request):
    same_origin(request)
    authenticated(request)
    accounts.disconnect()
    return {'ok':True}


@app.get('/api/status')
def status():
    s=paper.status()
    return {**snapshot(),'platforms':platforms.status(),'budget':ai_costs.summary(),
            'paper_enabled':s['enabled'],'paper_state':s['state'],'mode':'paper_dry_run' if s['enabled'] else 'infrastructure_only',
            'performance':{'pnl':s['realized_pnl'] if s['orders'] or s['enabled'] else None,'trades':len(s['trades']),
                           'note':'仅模拟账本已实现盈亏；历史回测另列，不包含在此处'}}


@app.get('/api/account/paper')
def paper_status(request: Request):
    authenticated(request)
    from labapp.paper_monitor import snapshot as monitor
    s=paper.status()
    return {**s,'monitor':monitor(s)}


@app.get('/api/account/fast-experiment')
def fast_experiment_status(request:Request):
    authenticated(request)
    from labapp.fast_experiment import snapshot
    return snapshot()


@app.post('/api/account/fast-experiment-action')
async def fast_experiment_action(request:Request):
    same_origin(request);authenticated(request)
    data=await body(request)
    if set(data)!={'enabled'} or type(data['enabled']) is not bool:raise HTTPException(400,'仅允许启停独立实验')
    from labapp.fast_experiment import configure
    return configure(data['enabled'])


@app.post('/api/account/paper-action')
async def paper_action(request: Request):
    same_origin(request);authenticated(request)
    data=await body(request)
    try:
        action=data.get('action')
        if action=='settings':return paper.settings(data)
        if action=='check':return await run_in_threadpool(paper.check_connection)
        if action=='prepare':return paper.enqueue('prepare')
        if action=='backtest':return paper.enqueue('backtest',data.get('window','holdout'))
        if action=='cancel':return paper.cancel_job()
        if action=='approve-research':return paper.approve_research(data.get('job_id',''))
        if action=='start':return paper.start()
        if action=='stop':return paper.stop()
        raise ValueError('模拟操作无效。')
    except ValueError as exc:
        raise HTTPException(409,{'message':'操作未执行。','blockers':str(exc).splitlines()}) from None


@app.get('/api/account/workspace')
def workspace(request: Request):
    authenticated(request)
    return {'ai':integrations.status(),'modules':integrations.readiness(),'analysis':integrations.last_analysis(),'research':research_jobs.latest()}


@app.get('/api/account/research')
def research_status(request: Request):
    authenticated(request)
    return {'job':research_jobs.latest(),'costs':ai_costs.summary()}


@app.get('/api/account/training')
def training_status(request: Request):
    authenticated(request)
    return {'job':training.latest(),'readiness':training.readiness(),'versions':training.dependencies()}


@app.get('/api/account/optimizer')
def optimizer_status(request: Request):
    authenticated(request)
    return optimizer.status()


@app.post('/api/account/optimizer-action')
async def optimizer_action(request: Request):
    same_origin(request);authenticated(request)
    data=await body(request)
    if set(data)!={'enabled'}:raise HTTPException(400,'仅支持自动优化开关，风险和预算不可在此修改。')
    try:return optimizer.configure(data['enabled'])
    except ValueError as exc:raise HTTPException(400,str(exc)) from None


@app.post('/api/account/training-action')
async def training_action(request: Request):
    same_origin(request);authenticated(request)
    data=await body(request)
    try:
        if data.get('action')=='start':return training.enqueue(data.get('source'))
        if data.get('action')=='stop':return training.cancel()
        raise ValueError('训练操作无效。')
    except ValueError as exc:raise HTTPException(409,{'message':'训练未启动。','blockers':str(exc).splitlines()}) from None


@app.post('/api/account/ai-config')
async def ai_config(request: Request):
    same_origin(request)
    authenticated(request)
    data=await body(request)
    try:
        return integrations.save(data)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from None


@app.post('/api/account/ai-delete')
def ai_delete(request: Request):
    same_origin(request)
    authenticated(request)
    integrations.delete()
    return {'ok':True}


@app.post('/api/account/ai-validate')
async def ai_validate(request: Request):
    same_origin(request)
    authenticated(request)
    try:
        return await run_in_threadpool(ai_connection.validate)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from None


@app.post('/api/account/module-action')
async def module_action(request: Request):
    same_origin(request)
    authenticated(request)
    data=await body(request)
    modules=integrations.readiness()
    if data.get('module') not in modules or data.get('action') not in ('start','stop'):
        raise HTTPException(400,'模块或操作无效。')
    if data['action']=='stop':
        if data['module']=='training':return training.cancel()
        if data['module']=='simulation':
            return paper.stop()
        if data['module']=='research':
            return research_jobs.cancel()
        return {'ok':True,'message':'该模块当前未运行，没有活动任务需要停止。'}
    if data['module']=='research':
        try:
            return research_jobs.create()
        except ValueError as exc:
            raise HTTPException(409,{'message':'研究启动条件未满足。','blockers':str(exc).splitlines()}) from None
    if data['module']=='training':
        try:return training.enqueue()
        except ValueError as exc:
            raise HTTPException(409,{'message':'训练未启动。','blockers':str(exc).splitlines()}) from None
    if data['module']=='simulation':
        try:return paper.start()
        except ValueError as exc:
            raise HTTPException(409,{'message':'实时模拟未启动。','blockers':str(exc).splitlines()}) from None
    if data['module']=='analysis':
        try:
            return {'ok':True,'analysis':integrations.analyze(),'message':'行情描述统计已完成，未调用 AI 或运行交易。'}
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from None
    raise HTTPException(409,{'message':'尚不能启动：此入口不会模拟成功。','blockers':modules[data['module']]['blockers']})


@app.post('/api/account/market-control')
async def market_control(request: Request):
    same_origin(request)
    authenticated(request)
    data=await body(request)
    try:
        return {'ok':True,'settings':controls.change(data)}
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from None


@app.post('/api/account/diagnostics')
def network_diagnostics(request: Request):
    same_origin(request)
    authenticated(request)
    return controls.diagnostics()


@app.get('/health')
def health():
    try:
        snapshot()
        return {'status':'ok','trading_enabled':False}
    except Exception:
        return JSONResponse({'status':'database_unavailable'},status_code=503)


@app.get('/')
def index():
    return FileResponse(ROOT/'web/index.html',headers={'Cache-Control':'no-store'})


@app.get('/style.css')
def stylesheet():
    return FileResponse(ROOT/'web/style.css',media_type='text/css',headers={'Cache-Control':'no-cache'})


@app.get('/app.js')
def javascript():
    return FileResponse(ROOT/'web/app.js',media_type='text/javascript',headers={'Cache-Control':'no-cache'})


app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')


if __name__ == '__main__':
    init()
    uvicorn.run(app,host=os.environ.get('LAB_BIND','127.0.0.1'),port=8080,access_log=False)
