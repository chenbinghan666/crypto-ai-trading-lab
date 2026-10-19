"""Download official monthly archives, verify SHA256, and reject imperfect OHLCV."""
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def validate(frame, minutes):
    if frame.empty or frame.isna().any().any():
        raise ValueError('Empty data or missing values')
    if frame.date.duplicated().any() or not frame.date.is_monotonic_increasing:
        raise ValueError('Duplicate or unordered timestamps')
    if not frame.date.diff().iloc[1:].eq(pd.Timedelta(minutes=minutes)).all():
        raise ValueError('Candle gaps')
    values = frame[['open', 'high', 'low', 'close', 'volume']]
    if not np.isfinite(values).all().all() or (values[['open','high','low','close']] <= 0).any().any():
        raise ValueError('Non-finite or non-positive price')
    if (frame.volume < 0).any() or (frame.high < frame[['open','close','low']].max(axis=1)).any() or (frame.low > frame[['open','close','high']].min(axis=1)).any():
        raise ValueError('Invalid OHLCV bounds')
    if (frame.date + pd.Timedelta(minutes=minutes) > pd.Timestamp.now(tz='UTC')).any():
        raise ValueError('Unclosed or future candle')


def main():
    archive = ROOT / 'data/archives'
    output = ROOT / 'data/binance'
    archive.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    sources, frames = [], []
    for month in ['2026-08', '2026-09']:
        name = f'BTCUSDT-5m-{month}.zip'
        url = 'https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/5m/' + name
        expected = urlopen(url + '.CHECKSUM', timeout=30).read().decode().split()[0]
        target = archive / name
        body = target.read_bytes() if target.exists() else urlopen(url, timeout=30).read()
        digest = hashlib.sha256(body).hexdigest()
        if digest != expected:
            raise ValueError('Archive checksum mismatch: ' + name)
        target.write_bytes(body)
        with ZipFile(io.BytesIO(body)) as z:
            raw = pd.read_csv(z.open(name.replace('.zip','.csv')), header=None)
        # Binance spot archives from 2025 use microseconds; detect explicitly.
        unit = 'us' if int(raw.iloc[0, 0]) > 10**14 else 'ms'
        frame = raw.iloc[:, :6].copy()
        frame.columns = ['date','open','high','low','close','volume']
        frame['date'] = pd.to_datetime(frame.date, unit=unit, utc=True)
        frame.iloc[:, 1:] = frame.iloc[:, 1:].astype(float)
        validate(frame, 5)
        start = pd.Timestamp(month + '-01', tz='UTC')
        end = start + pd.offsets.MonthBegin(1)
        if frame.date.iloc[0] != start or frame.date.iloc[-1] + pd.Timedelta(minutes=5) != end:
            raise ValueError('Incomplete monthly boundary')
        frames.append(frame)
        sources.append({'url':url, 'sha256':digest, 'rows':len(frame), 'timestamp_unit':unit})
    base = pd.concat(frames, ignore_index=True)
    validate(base, 5)
    products = []
    for tf, minutes in [('5m',5),('15m',15),('1h',60)]:
        if minutes == 5:
            frame = base
        else:
            frame = base.set_index('date').resample(f'{minutes}min', label='left', closed='left').agg(
                {'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).reset_index()
        validate(frame, minutes)
        path = output / f'BTC_USDT-{tf}.feather'
        frame.to_feather(path)
        products.append({'file':str(path.relative_to(ROOT)), 'rows':len(frame),
                         'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                         'first_open_utc':str(frame.date.iloc[0]), 'last_open_utc':str(frame.date.iloc[-1])})
    report = {'retrieved_at_utc':datetime.now(timezone.utc).isoformat(), 'exchange':'binance',
              'market':'spot', 'symbol':'BTC/USDT', 'sources':sources, 'products':products,
              'missing_candles':0, 'duplicate_candles':0,
              'attribution':'Binance Vision; personal non-production research; CC BY-NC-SA 4.0',
              'resampling':'Closed 5m candles aggregated into complete UTC 15m/1h candles'}
    (ROOT/'reports/evidence/phase2/data_manifest.json').write_text(json.dumps(report,indent=2), encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
