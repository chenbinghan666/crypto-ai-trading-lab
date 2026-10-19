"""Small, checksum-verified official USDT-M archives. No exchange credentials."""
import hashlib
import io
import json
from datetime import datetime,timezone
from urllib.request import urlopen
from zipfile import ZipFile
import pandas as pd
from scripts.download_history import validate
from labapp import store

MONTHS=('2025-01','2025-02','2025-03')
BASE='https://data.binance.vision/data/futures/um/monthly'


def download(kind,month):
    folder=store.STATE/'futures-history'/'archives';folder.mkdir(parents=True,exist_ok=True)
    name=f'BTCUSDT-fundingRate-{month}.zip' if kind=='fundingRate' else f'BTCUSDT-1h-{month}.zip'
    url=f'{BASE}/{kind}/BTCUSDT/'+('' if kind=='fundingRate' else '1h/')+name
    with urlopen(url+'.CHECKSUM',timeout=25) as r:expected=r.read(4096).decode().split()[0]
    path=folder/(kind+'-'+name)
    if path.exists():body=path.read_bytes()
    else:
        with urlopen(url,timeout=25) as r:body=r.read(4_000_001)
    if len(body)>4_000_000 or hashlib.sha256(body).hexdigest()!=expected:
        raise ValueError('Archive checksum or size rejected')
    path.write_bytes(body)
    with ZipFile(io.BytesIO(body)) as z:
        info=z.infolist()
        if len(info)!=1 or info[0].file_size>15_000_000:raise ValueError('Archive rejected')
        data=pd.read_csv(z.open(info[0]))
    return data,{'url':url,'sha256':expected,'rows':len(data)}


def main():
    store.init();folder=store.STATE/'futures-history';folder.mkdir(parents=True,exist_ok=True)
    sources=[];futures=[];marks=[];funding=[]
    for month in MONTHS:
        for kind,target in [('klines',futures),('markPriceKlines',marks)]:
            raw,source=download(kind,month);sources.append(source)
            frame=raw.iloc[:,:6].copy();frame.columns=['date','open','high','low','close','volume']
            frame['date']=pd.to_datetime(frame.date.astype('int64'),unit='ms',utc=True)
            for col in ['open','high','low','close','volume']:frame[col]=frame[col].astype(float)
            validate(frame,60)
            start=pd.Timestamp(month+'-01',tz='UTC');end=start+pd.offsets.MonthBegin(1)
            if frame.date.iloc[0]!=start or frame.date.iloc[-1]+pd.Timedelta(hours=1)!=end:
                raise ValueError('Incomplete monthly archive')
            target.append(frame)
        raw,source=download('fundingRate',month);sources.append(source)
        timestamps=raw.calc_time.astype('int64')
        if (timestamps%28_800_000>1000).any() or not raw.funding_interval_hours.eq(8).all():
            raise ValueError('Unexpected funding settlement time')
        frame=pd.DataFrame({'date':pd.to_datetime((timestamps//28_800_000)*28_800_000,unit='ms',utc=True),
                            'open':raw.last_funding_rate.astype(float)})
        if frame.open.isna().any() or not frame.date.diff().iloc[1:].eq(pd.Timedelta(hours=8)).all():
            raise ValueError('Invalid funding history')
        for col in ['high','low','close','volume']:frame[col]=0.0
        funding.append(frame)
    products=[]
    # Freqtrade 2026.9 names Binance funding files by its 1h fetch timeframe;
    # settlement records remain at their actual 8h timestamps (no synthetic fill).
    for suffix,items in [('1h-futures',futures),('1h-mark',marks),('1h-funding_rate',funding)]:
        frame=pd.concat(items,ignore_index=True)
        if suffix!='1h-funding_rate':validate(frame,60)
        elif frame.date.duplicated().any() or not frame.date.diff().iloc[1:].eq(pd.Timedelta(hours=8)).all():
            raise ValueError('Funding gaps')
        (folder/'futures').mkdir(exist_ok=True)
        path=folder/'futures'/f'BTC_USDT_USDT-{suffix}.feather';frame.to_feather(path)
        products.append({'name':str(path.relative_to(folder)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':len(frame)})
    manifest={'at':datetime.now(timezone.utc).isoformat(),'market':'usd_m_futures','pair':'BTC/USDT:USDT',
              'timeframe':'1h','months':MONTHS,'sources':sources,'products':products,
              'exchange_rules':'offline_assumptions_only_not_live_verified',
              'split':{'development':'20250106-20250201','validation':'20250201-20250301','holdout':'20250301-20250401'}}
    path=folder/'manifest.json';temp=path.with_suffix('.tmp');temp.write_text(json.dumps(manifest,indent=2));temp.replace(path)
    print(json.dumps({'ok':True,'files':len(products),'archives':len(sources)}))


if __name__=='__main__':main()
