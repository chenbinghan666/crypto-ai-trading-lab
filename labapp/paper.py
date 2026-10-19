"""Persistent control plane for the official Freqtrade dry-run and backtests."""
import hashlib
import json
import math
import sqlite3
import time
import uuid
from urllib.request import urlopen
from labapp import store,risk_gate

STRATEGY=store.ROOT/'strategies/FuturesBaseline.py'


def fingerprint():
    paths=('strategies/FuturesBaseline.py','labapp/risk_gate.py','labapp/paper.py',
           'labapp/paper_runtime.py','labapp/paper_service.py','scripts/futures_backtest.py',
           'labapp/optimizer.py','labapp/optimizer_inference.py','labapp/optimizer_evaluate.py')
    return hashlib.sha256(b''.join((store.ROOT/p).read_bytes() for p in paths)).hexdigest()


def init():
    with store.connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS paper_control(id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER,
            capital REAL,agent_mode TEXT,updated REAL,state TEXT,message TEXT,generation TEXT);
        INSERT OR IGNORE INTO paper_control(id,enabled,capital,agent_mode,updated,state,message,generation) VALUES(1,0,1000,'agent_required',0,'stopped','尚未启动', '');
        CREATE TABLE IF NOT EXISTS paper_checks(id INTEGER PRIMARY KEY CHECK(id=1),at REAL,ok INTEGER,payload TEXT);
        CREATE TABLE IF NOT EXISTS paper_intents(key TEXT PRIMARY KEY,at REAL,state TEXT);
        CREATE TABLE IF NOT EXISTS paper_jobs(id TEXT PRIMARY KEY,at REAL,state TEXT,kind TEXT,window TEXT,
            result TEXT,error TEXT,cancel INTEGER DEFAULT 0,capital REAL DEFAULT 1000);
        CREATE TABLE IF NOT EXISTS paper_signal(id INTEGER PRIMARY KEY CHECK(id=1),job_id TEXT,
            direction TEXT,expires REAL,approved REAL);
        ''')
        if 'capital' not in {r['name'] for r in db.execute('PRAGMA table_info(paper_jobs)')}:
            db.execute('ALTER TABLE paper_jobs ADD COLUMN capital REAL DEFAULT 1000')
        if 'venue' not in {r['name'] for r in db.execute('PRAGMA table_info(paper_control)')}:
            db.execute("ALTER TABLE paper_control ADD COLUMN venue TEXT DEFAULT 'binance'")


def ledger_path():
    with store.connect() as db:venue=db.execute('SELECT venue FROM paper_control WHERE id=1').fetchone()[0]
    return store.STATE/('futures-paper-gate.sqlite' if venue=='gate' else 'futures-paper.sqlite')


def signal():
    init()
    with store.connect() as db:r=db.execute('SELECT * FROM paper_signal WHERE id=1').fetchone()
    return dict(r) if r and time.time()<r['expires'] else None


def approve_research(job_id):
    from labapp import research_jobs
    research_jobs.init();init()
    with store.connect() as db:r=db.execute("SELECT * FROM research_jobs WHERE id=? AND state='completed'",(job_id,)).fetchone()
    if not r:raise ValueError('研究任务不存在或未完成。')
    result=json.loads(r['result']);rating=result.get('rating','').strip().upper()
    directions={'BUY':'long','SELL':'short','HOLD':'hold'}
    if result.get('symbol')!='BTC/USDT' or result.get('market_type')!='usd_m_futures':
        raise ValueError('只能批准 BTC U 本位合约研究；现货参考报告不能用于合约模拟。')
    expiry=result.get('cutoff_ms',0)/1000+7200
    if not time.time()<expiry<=time.time()+7200 or rating not in directions:
        raise ValueError('研究已过期或未提供可解析的 BUY / SELL / HOLD；不解析自然语言建议。')
    with store.connect() as db:
        db.execute('INSERT OR REPLACE INTO paper_signal VALUES(1,?,?,?,?)',(job_id,directions[rating],expiry,time.time()))
    store.event('paper','info','用户批准合约研究方向过滤器；仍须通过策略与独立风控，不直接下单')
    return {'message':'已批准方向过滤器，有效期截止数据时间后 2 小时；不会直接下单。'}


def snapshot_trades():
    path=ledger_path()
    if not path.exists():return {'trades':[],'orders':0,'realized_pnl':0.0,'open_trades':0}
    try:
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1);db.row_factory=sqlite3.Row
        with db:
            trades=[dict(r) for r in db.execute('SELECT id,pair,is_open,is_short,amount,stake_amount,open_rate,close_rate,close_profit_abs,open_date,close_date,leverage,funding_fees FROM trades ORDER BY id DESC LIMIT 100')]
            orders=db.execute('SELECT count(*) FROM orders').fetchone()[0]
            pnl=db.execute('SELECT coalesce(sum(close_profit_abs),0) FROM trades WHERE is_open=0').fetchone()[0]
            opened=db.execute('SELECT count(*) FROM trades WHERE is_open=1').fetchone()[0]
        db.close()
        return {'trades':trades,'orders':orders,'realized_pnl':pnl,'open_trades':opened}
    except sqlite3.Error:
        return {'trades':[],'orders':None,'realized_pnl':None,'open_trades':None,'error':'模拟数据库暂时不可读，禁止新仓。'}


def status():
    init()
    with store.connect() as db:
        control=dict(db.execute('SELECT * FROM paper_control WHERE id=1').fetchone())
        checked=db.execute('SELECT * FROM paper_checks WHERE id=1').fetchone()
        job=db.execute('SELECT * FROM paper_jobs ORDER BY at DESC LIMIT 1').fetchone()
        worker=db.execute("SELECT * FROM services WHERE name='paper'").fetchone()
    control['enabled']=bool(control['enabled'])
    control['checks']=json.loads(checked['payload']) if checked else {'ok':False,'message':'请先检查合约连接与交易规则。'}
    control['checks_stale']=not checked or time.time()-checked['at']>120 or control['checks'].get('venue','binance')!=control['venue']
    control['job']={**dict(job),'result':json.loads(job['result']) if job['result'] else None} if job else None
    control['worker_ready']=bool(worker and worker['state']=='running' and time.time()-worker['heartbeat']<30)
    control['signal']=signal();control['risk_limits']=risk_gate.LIMITS
    control['engineering_accepted']=acceptance()
    control['history_ready']=(store.STATE/'futures-history/manifest.json').exists()
    evaluations=[]
    for window in ('development','validation','holdout'):
        try:
            result=json.loads((store.STATE/'futures-history'/f'backtest-{window}.json').read_text())
            evaluations.append({k:v for k,v in result.items() if k!='trades'})
        except (OSError,ValueError):pass
    control['evaluations']=evaluations
    control['live_enabled']=False
    return {**control,**snapshot_trades()}


def acceptance():
    try:
        report=json.loads((store.STATE/'futures-acceptance.json').read_text())
        return report.get('passed') is True and report.get('strategy_hash')==fingerprint()
    except (OSError,ValueError):return False


def entry_blockers(side=None):
    s=status();reasons=[]
    if not acceptance():reasons.append('当前策略及风控尚未通过本机工程验收。')
    if s['checks_stale'] or not s['checks'].get('ok'):reasons.append('币安合约连接、最新行情或交易规则检查未通过 / 已过期。')
    if s.get('error'):reasons.append(s['error'])
    if s['agent_mode']=='agent_required':
        sig=s['signal']
        if not sig or s['venue']!='binance':reasons.append('当前市场没有有效且人工批准的合约 AI 研究；可在网页明确选择规则基线模拟。')
        elif sig['direction']=='hold' or side and sig['direction']!=side:reasons.append('研究方向过滤器不允许本次开仓。')
    return reasons


def readiness():
    s=status();reasons=entry_blockers()
    if not s['worker_ready']:reasons.append('模拟管理服务未就绪。')
    return {'title':'实时合约模拟','ready':not reasons,'blockers':reasons,
            'description':'官方 Freqtrade Dry-run · '+s['venue'].upper()+' BTC 永续 · 1h · 1 倍 · 虚拟本金 '+str(s['capital'])+' USDT'}


def settings(data):
    init();capital=data.get('capital',1000);mode=data.get('agent_mode','agent_required')
    if set(data)-{'action','capital','agent_mode','venue'}:raise ValueError('不支持此模拟设置；杠杆和风险上限不能由 API 请求修改。')
    if type(capital) not in (int,float) or not math.isfinite(capital) or not 10<=capital<=1_000_000:
        raise ValueError('虚拟本金须在 10 至 1000000 USDT 之间。')
    if mode not in ('agent_required','baseline_fallback'):raise ValueError('模拟策略模式无效。')
    s=status()
    venue=data.get('venue',s['venue'])
    if venue not in ('binance','gate'):raise ValueError('模拟市场无效。')
    if s['enabled'] or s['state'] in ('running','starting','stopping'):raise ValueError('请先停止模拟再修改设置。')
    if any((store.STATE/name).exists() for name in ('futures-paper.sqlite','futures-paper-gate.sqlite')) and capital!=s['capital']:
        raise ValueError('已有模拟账本，不能更改其初始本金。新账户功能尚未开放，原账本保留。')
    with store.connect() as db:
        db.execute('UPDATE paper_control SET capital=?,agent_mode=?,venue=?,updated=? WHERE id=1',(capital,mode,venue,time.time()))
        if venue!=s['venue']:db.execute('DELETE FROM paper_signal')
    store.event('paper','info',f'模拟设置已保存：{capital:g} USDT / {mode} / 固定 1 倍；未启动')
    return {'message':'模拟设置已保存；规则基线模式不调用 AI，也不使用币安账户资金。'}


def start():
    s=status()
    if s['enabled']:return {'message':'模拟已请求启动，不重复创建进程。'}
    reasons=entry_blockers()
    if not s['worker_ready']:reasons.append('模拟管理服务未就绪。')
    if reasons:raise ValueError('\n'.join(reasons))
    with store.connect() as db:
        db.execute("UPDATE paper_control SET enabled=1,state='starting',message='正在启动官方 Freqtrade Dry-run',updated=?,generation=? WHERE id=1",(time.time(),uuid.uuid4().hex))
    store.event('paper','info','用户请求启动官方 Freqtrade 合约模拟；不使用账户密钥；实盘禁止')
    return {'message':'已请求启动实时模拟，请以下方实际进程状态为准。'}


def stop():
    init()
    with store.connect() as db:
        db.execute("UPDATE paper_control SET enabled=0,state=CASE WHEN enabled=1 THEN 'stopping' ELSE state END,message='已请求停止；模拟持仓保留，下次启动继续管理',updated=? WHERE id=1",(time.time(),))
    return {'message':'已请求停止模拟进程；不会清空订单或伪造平仓。持仓恢复后继续管理。'}


def claim_entry(pair,candle,side):
    if not status()['enabled'] or entry_blockers(side):return False
    key=f"{status()['venue']}:{pair}:{candle}:{side}"
    with store.connect() as db:
        try:db.execute('INSERT INTO paper_intents VALUES(?,?,?)',(key,time.time(),'reserved'))
        except sqlite3.IntegrityError:return False
    return True # Persist before engine creates a simulated order; uncertainty fails closed.


def check_connection():
    init();base='https://fapi.binance.com/fapi/v1/'
    s=status()
    if s['venue']=='gate':return check_gate_connection()
    def get(path):
        with urlopen(base+path,timeout=8) as r:
            raw=r.read(4_000_001)
            if len(raw)>4_000_000:raise ValueError('Oversized public response')
            return json.loads(raw)
    try:
        server=get('time')['serverTime'];now=time.time()
        if abs(server/1000-now)>30:raise ValueError('Clock difference')
        info=get('exchangeInfo');market=next(x for x in info['symbols'] if x['symbol']=='BTCUSDT')
        if market['status']!='TRADING' or market['contractType']!='PERPETUAL' or market['marginAsset']!='USDT':
            raise ValueError('Unsupported market')
        filters={x['filterType']:x for x in market['filters']}
        for name,field in [('LOT_SIZE','stepSize'),('PRICE_FILTER','tickSize'),('MIN_NOTIONAL','notional')]:
            value=float(filters[name][field])
            if not math.isfinite(value) or value<=0:raise ValueError('Invalid market limits')
        candles=get('klines?symbol=BTCUSDT&interval=1h&limit=102')
        from scripts.download_history import validate
        import pandas as pd
        frame=pd.DataFrame([x[:6] for x in candles if int(x[6])<server],columns=['date','open','high','low','close','volume'])
        frame['date']=pd.to_datetime(frame.date,unit='ms',utc=True)
        for col in ['open','high','low','close','volume']:frame[col]=frame[col].astype(float)
        validate(frame,60)
        if len(frame)<100 or not 0<=server/1000-(frame.date.iloc[-1].timestamp()+3600)<3720:raise ValueError('Stale candle')
        mark=get('premiumIndex?symbol=BTCUSDT')
        if abs(mark['time']/1000-time.time())>30 or not math.isfinite(float(mark['markPrice'])) or float(mark['markPrice'])<=0:
            raise ValueError('Stale mark price')
        result={'ok':True,'at':time.time(),'message':'币安 U 本位合约行情与交易规则检查通过。',
                'symbol':'BTCUSDT','filters':filters,'last_close':frame.date.iloc[-1].timestamp()+3600,
                'min_notional':float(filters['MIN_NOTIONAL']['notional'])}
        s=status()
        if risk_gate.stake(s['capital'],s['capital'])<result['min_notional']:
            raise ValueError('Virtual position smaller than exchange minimum')
    except Exception as exc:
        from labapp.network import explain_error
        result={'ok':False,'at':time.time(),'message':explain_error(exc)[2] if not isinstance(exc,ValueError) else '合约数据、时间或交易规则校验未通过；禁止新仓。'}
    result['venue']='binance'
    with store.connect() as db:
        db.execute('INSERT OR REPLACE INTO paper_checks VALUES(1,?,?,?)',(time.time(),int(result['ok']),json.dumps(result)))
    return result


def check_gate_connection():
    from labapp.paper_runtime import config,public_only,PAIR
    from scripts.download_history import validate
    import ccxt
    import pandas as pd
    public_only()
    client=ccxt.gate(config(1000,'gate')['exchange']['ccxt_config'])
    try:
        server=client.fetch_time()
        if abs(server/1000-time.time())>30:raise ValueError('Clock mismatch')
        market=client.load_markets()[PAIR]
        if not market['active'] or not market['swap'] or not market['linear'] or market['settle']!='USDT':raise ValueError('Invalid contract')
        rows=client.fetch_ohlcv(PAIR,'1h',limit=102)
        frame=pd.DataFrame([x for x in rows if x[0]+3600000<=server],columns=['date','open','high','low','close','volume'])
        frame['date']=pd.to_datetime(frame.date,unit='ms',utc=True);validate(frame,60)
        if len(frame)<100 or not 0<=server/1000-frame.date.iloc[-1].timestamp()-3600<3720:raise ValueError('Stale history')
        funding=client.fetch_funding_rate(PAIR)
        if not all(math.isfinite(float(funding[k])) for k in ('markPrice','fundingRate')) or funding['markPrice']<=0:raise ValueError('Invalid funding')
        rules=client.publicFuturesGetSettleContractsContract({'settle':'usdt','contract':'BTC_USDT'})
        fee=float(rules['taker_fee_rate'])
        if fee>risk_gate.LIMITS['fee_per_side'] or fee<0:raise ValueError('Fee exceeds approved risk assumption')
        tiers=client.fetch_market_leverage_tiers(PAIR)
        if not tiers:raise ValueError('No leverage tiers')
        minimum=float(market['limits']['amount']['min'])*float(market['contractSize'])*float(funding['markPrice'])
        if risk_gate.stake(status()['capital'],status()['capital'])<minimum:raise ValueError('Position too small')
        result={'ok':True,'at':time.time(),'venue':'gate','symbol':PAIR,'message':'Gate U 本位永续行情、合约乘数、资金费率及风险档位检查通过。',
            'mark_price':funding['markPrice'],'funding_rate':funding['fundingRate'],'min_notional':minimum,
            'contract_size':market['contractSize'],'amount_step':market['precision']['amount'],'taker_fee':fee,
            'last_close':frame.date.iloc[-1].timestamp()+3600,'received_at':time.time()}
    except Exception as exc:
        from labapp.network import explain_error
        result={'ok':False,'at':time.time(),'venue':'gate','message':explain_error(exc)[2] if not isinstance(exc,ValueError) else 'Gate 合约数据、费用或规则校验未通过，禁止新仓。'}
    # A late response cannot overwrite the selected market's readiness.
    with store.connect() as db:
        if db.execute('SELECT venue FROM paper_control WHERE id=1').fetchone()[0]=='gate':
            db.execute('INSERT OR REPLACE INTO paper_checks VALUES(1,?,?,?)',(time.time(),int(result['ok']),json.dumps(result)))
    return result


def enqueue(kind,window='holdout'):
    init()
    if kind not in ('prepare','backtest') or window not in ('development','validation','holdout'):raise ValueError('任务无效。')
    s=status()
    if not s['worker_ready']:raise ValueError('模拟管理服务未就绪。')
    if kind=='backtest':
        from scripts.futures_backtest import verify_data
        try:verify_data()
        except (OSError,ValueError):raise ValueError('请先准备并校验历史合约数据。') from None
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM paper_jobs WHERE state IN ('queued','running')").fetchone():raise ValueError('已有历史任务执行中。')
        identifier=uuid.uuid4().hex
        db.execute('INSERT INTO paper_jobs(id,at,state,kind,window,capital) VALUES(?,?,?,?,?,?)',(identifier,time.time(),'queued',kind,window,s['capital']))
    return {'message':'历史任务已排队；这是回测，不会启动实时模拟。','id':identifier}


def cancel_job():
    init()
    with store.connect() as db:db.execute("UPDATE paper_jobs SET cancel=1 WHERE state IN ('queued','running')")
    return {'message':'已请求取消历史任务，已有结果保留。'}
