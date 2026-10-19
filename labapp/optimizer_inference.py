"""Load only local, hash-verified FreqAI candidate artifacts. No network."""
import hashlib
from pathlib import Path
from labapp import store
from strategies.FreqaiCpuResearch import features,TARGET

CACHE={}


def infer(frame,bundle):
    import cloudpickle
    from labapp.freqai_cpu import CpuLightGBMRegressor
    from labapp.training_runner import configuration,PAIR
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
    folder=(store.STATE/bundle['directory']).resolve()
    if not folder.is_relative_to((store.STATE/'optimizer/runs').resolve()):raise ValueError('Untrusted model path')
    identity=(str(folder),tuple(sorted(bundle['hashes'].items())))
    if identity not in CACHE:
        def read(name):
            path=folder/name
            if path.resolve().parent!=folder or hashlib.sha256(path.read_bytes()).hexdigest()!=bundle['hashes'][name]:raise ValueError('Model integrity failed')
            return cloudpickle.loads(path.read_bytes())
        cfg=configuration(folder.parent,'inference')
        model=CpuLightGBMRegressor(cfg);model.live=False
        dk=FreqaiDataKitchen(cfg,live=True,pair=PAIR)
        dk.training_features_list=bundle['features'];dk.label_list=[TARGET]
        model.model=read('cpu_lightgbm_model.joblib')
        dk.feature_pipeline=read('cpu_lightgbm_feature_pipeline.pkl');dk.label_pipeline=read('cpu_lightgbm_label_pipeline.pkl')
        CACHE.clear();CACHE[identity]=(model,dk)
    model,dk=CACHE[identity]
    prediction,mask=model.predict(features(frame),dk)
    return prediction[TARGET].to_numpy(),mask
