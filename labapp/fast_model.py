"""Fresh 15m FreqAI model; explicit 90-minute label, no paid calls."""
import hashlib
import json
import socket
import time
import numpy as np
import pandas as pd
from labapp import store,fast_experiment as exp
from labapp.paper_runtime import PAIR,public_only,config
from strategies.FreqaiCpuResearch import features

TARGET='&-return_90m'
CACHE={}


def configuration(directory):
    from labapp.training_runner import configuration as base
    c=base(directory,'experiment15m');c['timeframe']='15m'
    c['freqai']['feature_parameters']['include_timeframes']=['15m']
    return c


def infer(frame):
    import cloudpickle
    from labapp.freqai_cpu import CpuLightGBMRegressor
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
    root=exp.folder();descriptor=json.loads((root/'model.json').read_text())
    key=exp.state()['cohort']
    if key not in CACHE:
        cfg=configuration(root/'inference')
        dk=FreqaiDataKitchen(cfg,live=True,pair=PAIR)
        dk.training_features_list=descriptor['features'];dk.label_list=[TARGET]
        model=CpuLightGBMRegressor(cfg);model.live=False
        def read(name):
            raw=(root/'model'/name).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=descriptor['hashes'][name]:raise ValueError('实验模型校验失败')
            return cloudpickle.loads(raw)
        model.model=read('cpu_lightgbm_model.joblib')
        dk.feature_pipeline=read('cpu_lightgbm_feature_pipeline.pkl');dk.label_pipeline=read('cpu_lightgbm_label_pipeline.pkl')
        CACHE.clear();CACHE[key]=(model,dk)
    model,dk=CACHE[key];prediction,mask=model.predict(features(frame),dk)
    return prediction[TARGET].to_numpy(),mask


def main():
    import ccxt
    from scripts.download_history import validate
    exp.update('training','获取 Gate 15m 数据，训练独立实验 FreqAI 模型')
    public_only();client=ccxt.gate(config(1000,'gate')['exchange']['ccxt_config']);server=client.fetch_time()
    if abs(server/1000-time.time())>30:raise ValueError('交易所时间不同步')
    rows=client.fetch_ohlcv(PAIR,'15m',limit=2000)
    frame=pd.DataFrame([r for r in rows if r[0]+900000<=server],columns=['date','open','high','low','close','volume'])
    frame['date']=pd.to_datetime(frame.date,unit='ms',utc=True);validate(frame,15)
    if len(frame)<1600 or not 0<=server/1000-frame.date.iloc[-1].timestamp()-900<960:raise ValueError('15m 行情缺失或过期')
    root=exp.folder();root.mkdir(parents=True,exist_ok=True);frame.to_feather(root/'training.feather')
    original=socket.socket.connect
    def blocked(*a,**kw):raise RuntimeError('训练期间禁止联网')
    socket.socket.connect=blocked
    try:
        from labapp.freqai_cpu import CpuLightGBMRegressor
        from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
        df=features(frame);df[TARGET]=df.close.shift(-6)/df.close-1
        cols=[c for c in df if c.startswith('%')];boundary=int(len(df)*.8)
        train=df.iloc[:boundary-6].dropna(subset=cols+[TARGET]);test=df.iloc[boundary:-6].dropna(subset=cols+[TARGET])
        if len(train)<600 or len(test)<150 or train.date.iloc[-1]+pd.Timedelta(minutes=90)>=test.date.iloc[0]:raise ValueError('训练标签隔离失败')
        c=configuration(root/'trainer');model=CpuLightGBMRegressor(c);model.live=False
        dk=FreqaiDataKitchen(c,live=True,pair=PAIR);dk.find_features(train);dk.find_labels(train)
        dk.data_path=root/'model';dk.model_filename='cpu_lightgbm'
        model.model=model.train(train,PAIR,dk);pred,mask=model.predict(test,dk)
        model.dd.pair_dict.setdefault(PAIR,{'trained_timestamp':int(time.time())});model.dd.save_data(model.model,PAIR,dk)
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dk.data_path.iterdir() if p.is_file()}
        actual=test[TARGET].to_numpy();values=pred[TARGET].to_numpy()
        if not np.isfinite(values).all():raise ValueError('预测数值异常')
        metrics={'mae':float(np.mean(abs(values-actual))),'zero_mae':float(np.mean(abs(actual))),
            'direction_accuracy':float(np.mean(np.sign(values)==np.sign(actual))),
            'train_rows':len(train),'test_rows':len(test),'timeframe':'15m','horizon_minutes':90,
            'trained_at':time.time(),'training_cutoff':frame.date.iloc[-1].timestamp()+900,
            'profitability_accepted':False,'paid_ai_calls':0,'threshold':.003,
            'note':'仅用于独立前向模拟实验；不是已验证盈利模型。模型固定，避免比较期间改变实验条件。'}
        (root/'model.json').write_text(json.dumps({'hashes':hashes,'features':cols,'metrics':metrics}))
        restored,_=infer(frame)
        if not np.allclose(restored[test.index.to_numpy()],values,rtol=0,atol=1e-12):raise ValueError('重载预测不一致')
        (root/'ready.json').write_text(json.dumps({'start_after':metrics['training_cutoff']}))
        print(json.dumps(metrics))
    finally:socket.socket.connect=original


if __name__=='__main__':main()
