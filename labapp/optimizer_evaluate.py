"""Same-venue, costed official Freqtrade evaluations of frozen candidates."""
import json
import socket
import time
import numpy as np
import pandas as pd
from labapp import store,optimizer,training
from labapp.optimizer_data import verify
from labapp.paper_runtime import config,validate,PAIR
from strategies.FreqaiCpuResearch import features,TARGET,HORIZON


def fit_candidate_model(identifier,folder,frame,manifest):
    from labapp.training_runner import configuration
    from labapp.freqai_cpu import CpuLightGBMRegressor
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
    from labapp.optimizer_inference import infer
    training.init()
    with store.connect() as db:
        db.execute('INSERT OR IGNORE INTO training_jobs VALUES(?,?,?,?,?,?,?,?,?)',
                   (identifier,time.time(),time.time(),'running','optimizer_gate',0,'优化器：开发集训练',None,None))
    labelled=features(frame);labelled[TARGET]=labelled.close.shift(-HORIZON)/labelled.close-1
    cols=[c for c in labelled if c.startswith('%')]
    boundary=manifest['development_end']
    train=labelled.iloc[:boundary-HORIZON].dropna(subset=cols+[TARGET]).copy()
    test=labelled.iloc[boundary:-HORIZON].dropna(subset=cols+[TARGET]).copy()
    if len(train)<600 or train.date.iloc[-1]+pd.Timedelta(hours=HORIZON)>=test.date.iloc[0]:raise ValueError('Invalid model split')
    cfg=configuration(folder,identifier);model=CpuLightGBMRegressor(cfg);model.live=False
    dk=FreqaiDataKitchen(cfg,live=True,pair=PAIR);dk.find_features(train);dk.find_labels(train)
    dk.data_path=folder/'model';dk.model_filename='cpu_lightgbm'
    model.model=model.train(train,PAIR,dk);model.dd.pair_dict.setdefault(PAIR,{})
    model.dd.save_data(model.model,PAIR,dk)
    import hashlib
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dk.data_path.iterdir() if p.is_file()}
    bundle={'directory':str(dk.data_path.relative_to(store.STATE)),'hashes':hashes,'features':cols}
    predicted,mask=infer(test,bundle);actual=test[TARGET].to_numpy()
    # Validation only chooses the model; the final holdout remains uninspected here.
    val=test.date<pd.to_datetime(frame.date.iloc[manifest['validation_end']],utc=True)
    mae=float(np.mean(np.abs(predicted[val]-actual[val])));zero=float(np.mean(np.abs(actual[val])))
    result={'model':'CpuLightGBMRegressor','source':{'venue':'gate','kind':'optimizer_frozen_development'},
        'horizon_candles':6,'train_rows':len(train),'test_rows':int(val.sum()),'features':cols,
        'mae':mae,'zero_prediction_mae':zero,'beats_zero_baseline':mae<zero,
        'direction_accuracy':float(np.mean(np.sign(predicted[val])==np.sign(actual[val]))),
        'reload_verified':True,'train_start':str(train.date.iloc[0]),'train_end':str(train.date.iloc[-1]),
        'test_start':str(test.date.iloc[0]),'test_end':str(test[val].date.iloc[-1]),'purge_candles':6,
        'deployment':'candidate_only','trading_enabled':False,'paid_ai_calls':0,
        'limitations':'开发集训练，验证集预测误差评估；最终检验仅用于后续含成本策略验收。'}
    training.finish(identifier,'completed',result)
    return bundle,result


def run_backtest(folder,manifest,params,bundle,window,tag):
    optimizer.validate_params(params)
    from freqtrade.configuration import Configuration
    from freqtrade.enums import RunMode
    from freqtrade.exchange import Gate
    from freqtrade.optimize.backtesting import Backtesting
    frame=pd.read_feather(folder/'futures/BTC_USDT_USDT-1h-futures.feather')
    start=manifest['development_end'] if window=='validation' else manifest['validation_end']
    end=manifest['validation_end'] if window=='validation' else len(frame)
    start_ts=int(frame.date.iloc[start].timestamp());end_ts=int(frame.date.iloc[end-1].timestamp())+3600
    c=config(manifest['capital'],'gate');validate(c)
    cfgfile=folder/(tag+'-'+window+'-config.json');cfgfile.write_text(json.dumps(c))
    c=Configuration({'config':[str(cfgfile)],'strategy':'FuturesBaseline','strategy_path':str(store.ROOT/'strategies'),
        'datadir':str(folder),'user_data_dir':str(store.ROOT/'user_data'),
        'timerange':f'{start_ts}-{end_ts}','cache':'none','export':'none'},RunMode.BACKTEST).get_config()
    c['fee']=manifest['cost_per_side'];c['enable_protections']=False
    c['_lab_optimizer_params']=params;c['_lab_optimizer_bundle']=bundle
    e=Gate(c,validate=False,load_leverage_tiers=False)
    e._markets={PAIR:manifest['market']};e._api.set_markets([manifest['market']]);e._api_async.set_markets([manifest['market']])
    e._leverage_tiers={PAIR:[e.parse_leverage_tier(t) for t in manifest['tiers']]};e._last_markets_refresh=10**16;e.reload_markets=lambda *a,**k:None
    try:
        bt=Backtesting(c,exchange=e);bt.start();r=bt.results['strategy']['FuturesBaseline']
        return {'profit':float(r['profit_total_abs']),'drawdown':float(r['max_drawdown_account']),'trades':int(r['total_trades']),
                'funding_pnl':sum(t.get('funding_fees',0) or 0 for t in r['trades']),
                'cost_per_side':manifest['cost_per_side'],'leverage':1,'venue':'gate',
                'from':start_ts,'to':end_ts,'engine':'Freqtrade Backtesting'}
    finally:e.close()


def evaluate(identifier,params,incumbent):
    folder=store.STATE/'optimizer/runs'/identifier;manifest=verify(folder)
    frame=pd.read_feather(folder/'futures/BTC_USDT_USDT-1h-futures.feather')
    original=socket.socket.connect
    def blocked(*a,**k):raise RuntimeError('Frozen evaluation must not access network')
    socket.socket.connect=blocked
    try:
        bundle,model_metrics=fit_candidate_model(identifier,folder,frame,manifest)
        candidate={};baseline={}
        for window in ('validation','holdout'):
            optimizer.update(identifier,'Freqtrade 含成本比较：'+window)
            candidate[window]=run_backtest(folder,manifest,params,bundle if params['model_filter'] else None,window,'candidate')
            baseline[window]=run_backtest(folder,manifest,incumbent['params'],incumbent['bundle'],window,'incumbent')
        passed,reasons=optimizer.judge(candidate,baseline,model_metrics,params)
        result={'passed':passed,'reasons':reasons,'candidate':candidate,'incumbent':baseline,
            'model_metrics':model_metrics,'params':params,'parent':incumbent['id'],
            'heldout_end':manifest['holdout_end'],'reused_holdout':False,
            'selection_source':'TradingAgents + DeepSeek bounded JSON','network_during_evaluation':False}
        (folder/'evaluation.json').write_text(json.dumps(result,indent=2))
        return result,bundle if params['model_filter'] else None
    finally:socket.socket.connect=original
