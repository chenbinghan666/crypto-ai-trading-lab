"""One bounded FreqAI training task. No orders, credentials, or paid inference."""
import hashlib
import json
import math
import os
import socket
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
from labapp import store,training
from strategies.FreqaiCpuResearch import features,HORIZON,TARGET

PAIR='BTC/USDT:USDT'


def partition(frame):
    # Labels at train boundary cannot include any holdout price.
    labelled=features(frame)
    labelled[TARGET]=labelled.close.shift(-HORIZON)/labelled.close-1
    cols=[c for c in labelled if c.startswith('%')]
    valid=labelled.dropna(subset=cols+[TARGET]).reset_index(drop=True)
    boundary=int(len(valid)*.8)
    train=valid.iloc[:boundary-HORIZON].copy();test=valid.iloc[boundary:].copy()
    if len(train)<600 or len(test)<150:raise ValueError('Insufficient closed training candles')
    if train.date.iloc[-1]+pd.Timedelta(hours=HORIZON)>=test.date.iloc[0]:raise ValueError('Target overlap')
    return train,test,cols


def configuration(directory,identifier):
    from freqtrade.enums import RunMode
    return {'user_data_dir':directory,'timeframe':'1h','runmode':RunMode.BACKTEST,
        'exchange':{'name':'gate','pair_whitelist':[PAIR]},'dry_run':True,
        'freqai':{'enabled':True,'identifier':identifier,'train_period_days':60,'backtest_period_days':14,
          'activate_tensorboard':False,'data_kitchen_thread_count':2,'continual_learning':False,
          'feature_parameters':{'include_timeframes':['1h'],'include_corr_pairlist':[],
              'include_shifted_candles':0,'label_period_candles':HORIZON,'indicator_periods_candles':[6,12,24,48],
              'shuffle_after_split':False,'principal_component_analysis':False,'DI_threshold':0,
              'use_SVM_to_remove_outliers':False,'use_DBSCAN_to_remove_outliers':False},
          'data_split_parameters':{'test_size':0,'shuffle':False},
          'model_training_parameters':{'n_estimators':80,'num_leaves':15,'max_depth':5,
              'learning_rate':.05,'min_child_samples':30,'n_jobs':2,'random_state':42,'verbosity':-1}}}


def load_data(source):
    from scripts.download_history import validate
    if source=='binance_history':
        from scripts.futures_backtest import verify_data
        folder,manifest=verify_data()
        frame=pd.read_feather(folder/'futures/BTC_USDT_USDT-1h-futures.feather')
        description={'venue':'binance','kind':'official_historical_archive','manifest':manifest}
    elif source=='gate':
        import ccxt
        from labapp.paper_runtime import config,public_only
        public_only();client=ccxt.gate(config(1000,'gate')['exchange']['ccxt_config'])
        server=client.fetch_time()
        if abs(server/1000-time.time())>30:raise ValueError('Clock mismatch')
        rows=client.fetch_ohlcv(PAIR,'1h',limit=2000)
        frame=pd.DataFrame([r for r in rows if r[0]+3600000<=server],columns=['date','open','high','low','close','volume'])
        frame['date']=pd.to_datetime(frame.date,unit='ms',utc=True)
        if not 0<=server/1000-frame.date.iloc[-1].timestamp()-3600<3720:raise ValueError('Stale data')
        description={'venue':'gate','kind':'public_closed_candles','received_at':time.time(),
                     'volume_unit':'Gate contract volume, used only within same venue'}
    else:raise ValueError('Unsupported source')
    validate(frame,60)
    if len(frame)>2500:raise ValueError('Training dataset too large')
    return frame,description


def execute(identifier,source):
    directory=store.STATE/'freqai/jobs'/identifier;directory.mkdir(parents=True,exist_ok=True)
    training.stage(identifier,'获取并冻结已收盘合约数据')
    frame,description=load_data(source)
    data_path=directory/'candles.feather';frame.to_feather(data_path)
    data_hash=hashlib.sha256(data_path.read_bytes()).hexdigest()
    # No network after the input snapshot is frozen.
    original=socket.socket.connect
    def blocked(*a,**k):raise RuntimeError('Network forbidden during training')
    socket.socket.connect=blocked
    try:
        from labapp.freqai_cpu import CpuLightGBMRegressor
        from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
        train,test,cols=partition(frame)
        cfg=configuration(directory,identifier)
        cfg['exchange']['name']=description['venue']
        freqai=CpuLightGBMRegressor(cfg);freqai.live=False
        dk=FreqaiDataKitchen(cfg,live=True,pair=PAIR)
        dk.find_features(train);dk.find_labels(train)
        dk.data_path=directory/'artifacts';dk.model_filename='cpu_lightgbm'
        training.stage(identifier,f'CPU 训练：{len(train)} 样本 / {len(cols)} 特征 / 2 线程')
        freqai.model=freqai.train(train,PAIR,dk)
        training.stage(identifier,'独立时间段评估与模型保存验证')
        prediction,mask=freqai.predict(test,dk)
        predicted=prediction[TARGET].to_numpy();actual=test[TARGET].to_numpy()
        if not np.isfinite(predicted).all() or not np.isfinite(actual).all():raise ValueError('Invalid predictions')
        mae=float(np.mean(np.abs(predicted-actual)));zero=float(np.mean(np.abs(actual)))
        freqai.dd.pair_dict.setdefault(PAIR,{})
        freqai.dd.save_data(freqai.model,PAIR,dk)
        import cloudpickle
        artifacts=directory/'artifacts'
        artifact_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts.iterdir() if p.is_file()}
        # Reload only this task's own hash-verified artifacts; no uploaded pickle is accepted.
        def restore(name):
            p=artifacts/name
            if hashlib.sha256(p.read_bytes()).hexdigest()!=artifact_hashes[name]:raise ValueError('Model integrity failure')
            return cloudpickle.loads(p.read_bytes())
        freqai.model=restore('cpu_lightgbm_model.joblib')
        dk.feature_pipeline=restore('cpu_lightgbm_feature_pipeline.pkl')
        dk.label_pipeline=restore('cpu_lightgbm_label_pipeline.pkl')
        reloaded,_=freqai.predict(test,dk)
        if not np.allclose(predicted,reloaded[TARGET].to_numpy(),rtol=0,atol=1e-12):raise ValueError('Reload predictions differ')
        result={'model':'CpuLightGBMRegressor','engine':'FreqAI BaseRegressionModel + FreqaiDataKitchen',
            'source':description,'data_sha256':data_hash,'timeframe':'1h','horizon_candles':HORIZON,
            'train_rows':len(train),'test_rows':len(test),'features':cols,'purge_candles':HORIZON,
            'train_start':str(train.date.iloc[0]),'train_end':str(train.date.iloc[-1]),
            'test_start':str(test.date.iloc[0]),'test_end':str(test.date.iloc[-1]),
            'mae':mae,'zero_prediction_mae':zero,'beats_zero_baseline':mae<zero,
            'direction_accuracy':float(np.mean(np.sign(predicted)==np.sign(actual))),
            'accepted_predictions':int(np.sum(mask==1)),'reload_verified':True,
            'artifacts':artifact_hashes,'versions':training.dependencies(),'threads':2,
            'deployment':'candidate_only','trading_enabled':False,'paid_ai_calls':0,
            'limitations':'仅预测误差评估，不是策略收益回测；未计交易成本，不代表可盈利，不自动用于交易。'}
        (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        return result
    finally:socket.socket.connect=original


def main(identifier):
    with store.connect() as db:r=db.execute("SELECT * FROM training_jobs WHERE id=? AND state='running'",(identifier,)).fetchone()
    if not r:return
    try:
        result=execute(identifier,r['source']);training.finish(identifier,'completed',result)
        store.event('training','info','FreqAI CPU 训练、独立评估与保存重载验证完成；候选模型未用于交易')
    except Exception as exc:
        # Only exception type is exposed; never raw external data or credentials.
        training.finish(identifier,'failed',error='训练未完成：'+type(exc).__name__+'；请查看本机 training-task.log。')
        raise


if __name__=='__main__':main(sys.argv[1])
