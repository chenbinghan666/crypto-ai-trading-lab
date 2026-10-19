"""Freeze same-venue futures candles, mark prices, funding and public rules."""
import hashlib
import json
import time
from pathlib import Path
import pandas as pd
from labapp import store,paper
from labapp.paper_runtime import config,public_only,PAIR
from scripts.download_history import validate


def freeze(identifier):
    import ccxt
    public_only();client=ccxt.gate(config(1000,'gate')['exchange']['ccxt_config'])
    server=client.fetch_time()
    if abs(server/1000-time.time())>30:raise ValueError('Exchange clock mismatch')
    market=client.load_markets()[PAIR]
    tiers=client.fetch_market_leverage_tiers(PAIR)
    def frame(params):
        raw=client.fetch_ohlcv(PAIR,'1h',limit=2000,params=params)
        df=pd.DataFrame([r for r in raw if r[0]+3600000<=server],columns=['date','open','high','low','close','volume'])
        df['date']=pd.to_datetime(df.date,unit='ms',utc=True);validate(df,60)
        return df
    candles=frame({});mark=frame({'price':'mark'})
    if len(candles)<1600 or len(mark)!=len(candles) or not candles.date.equals(mark.date):raise ValueError('Insufficient aligned Gate history')
    if not 0<=server/1000-candles.date.iloc[-1].timestamp()-3600<3720:raise ValueError('Stale history')
    rates=[];since=int(candles.date.iloc[0].timestamp()*1000)
    for _ in range(10):
        batch=client.fetch_funding_rate_history(PAIR,since=since,limit=90)
        if not batch:break
        rates.extend(batch);next_since=max(r['timestamp'] for r in batch)+1000
        if next_since<=since:raise ValueError('Funding pagination stalled')
        since=next_since
        if since>=int(candles.date.iloc[-1].timestamp()*1000):break
    funding=pd.DataFrame({'date':[pd.Timestamp(r['timestamp'],unit='ms',tz='UTC').floor('h') for r in rates],
                          'open':[r['fundingRate'] for r in rates]})
    funding=funding[(funding.date>=candles.date.iloc[0])&(funding.date<=candles.date.iloc[-1])].reset_index(drop=True)
    if funding.empty or funding.date.duplicated().any() or not funding.date.diff().iloc[1:].eq(pd.Timedelta(hours=8)).all():raise ValueError('Funding history gap')
    expected=pd.date_range(candles.date.iloc[0].ceil('8h'),candles.date.iloc[-1],freq='8h')
    if not funding.date.tolist()==expected.tolist():raise ValueError('Incomplete funding coverage')
    for c in ('high','low','close','volume'):funding[c]=0.0
    folder=store.STATE/'optimizer/runs'/identifier;data=folder/'futures';data.mkdir(parents=True,exist_ok=True)
    hashes={}
    for kind,df in [('futures',candles),('mark',mark),('funding_rate',funding)]:
        path=data/f'BTC_USDT_USDT-1h-{kind}.feather';df.to_feather(path)
        hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    development_end=int(len(candles)*.6);validation_end=len(candles)-168
    cutoff=candles.date.iloc[development_end].timestamp()
    s=paper.status()
    eligible=[t for t in s['trades'] if not t['is_open'] and t['close_date'] and pd.to_datetime(t['close_date'],utc=True).timestamp()<=cutoff]
    review={'eligible_closed_trades':len(eligible),'net_realized_pnl':sum(t['close_profit_abs'] or 0 for t in eligible),
            'funding_pnl':sum(t['funding_fees'] or 0 for t in eligible),
            'note':'仅使用开发截止前的模拟成交；没有成交时不得编造复盘结论。最近成交仅用于后台回退监测，不提供给参数选择。'}
    manifest={'venue':'gate','pair':PAIR,'timeframe':'1h','market':market,'tiers':tiers,'files':hashes,
        'development_end':development_end,'validation_end':validation_end,'rows':len(candles),
        'development_cutoff':cutoff,'holdout_start':candles.date.iloc[validation_end].timestamp(),
        'holdout_end':candles.date.iloc[-1].timestamp()+3600,
        'review':review,'capital':s['capital'],'cost_per_side':.00125,
        'volume_unit':'Gate contract volume','received_at':time.time()}
    recent=[t for t in s['trades'] if not t['is_open'] and t['close_date'] and pd.to_datetime(t['close_date'],utc=True).timestamp()>cutoff]
    if recent:
        # Recent simulation feedback has seen the recent historical window.
        # Such candidates must be tested on future prices, never that same past.
        cutoff=candles.date.iloc[-1].timestamp()+3600
        manifest.update(forward_only=True,development_end=len(candles),validation_end=len(candles)+168,
            development_cutoff=cutoff,holdout_start=cutoff+168*3600,holdout_end=cutoff+336*3600)
        closed=[t for t in s['trades'] if not t['is_open']]
        manifest['review']={'eligible_closed_trades':len(closed),
            'net_realized_pnl':sum(t['close_profit_abs'] or 0 for t in closed),
            'funding_pnl':sum(t['funding_fees'] or 0 for t in closed),
            'recent_trades':[{k:t[k] for k in ('id','is_short','open_date','close_date','close_profit_abs','funding_fees')} for t in closed[:30]],
            'note':'包含最近真实模拟反馈；该候选必须等待未来 7 天验证及后续 7 天最终检验，禁止复用过去价格证明有效。'}
    (folder/'manifest.json').write_text(json.dumps(manifest,default=str,indent=2))
    return folder,manifest,candles


def refresh_forward(identifier):
    folder=store.STATE/'optimizer/runs'/identifier;manifest=verify(folder)
    refresh,_,_=freeze(identifier+'-refresh')
    candle=pd.read_feather(refresh/'futures/BTC_USDT_USDT-1h-futures.feather')
    if candle.date.iloc[-1].timestamp()+3600<manifest['holdout_end']:return False
    for name in manifest['files']:
        path=folder/'futures'/name
        combined=pd.concat([pd.read_feather(path),pd.read_feather(refresh/'futures'/name)],ignore_index=True)
        combined=combined.drop_duplicates('date',keep='first').sort_values('date').reset_index(drop=True)
        combined=combined[combined.date<pd.Timestamp(manifest['holdout_end'],unit='s',tz='UTC')].reset_index(drop=True)
        if 'funding_rate' not in name:validate(combined,60)
        elif not combined.date.diff().iloc[1:].eq(pd.Timedelta(hours=8)).all():raise ValueError('Forward funding gap')
        combined.to_feather(path);manifest['files'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
    (folder/'manifest.json').write_text(json.dumps(manifest,default=str,indent=2))
    return True


def verify(folder):
    manifest=json.loads((folder/'manifest.json').read_text())
    for name,digest in manifest['files'].items():
        path=folder/'futures'/name
        if path.resolve().parent!=(folder/'futures').resolve() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Frozen data integrity failed')
    return manifest
