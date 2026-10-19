"""Official FreqAI BaseRegressionModel with a CPU-only LightGBM fit extension.

Tensorboard is disabled: no torch/XGBoost runtime is needed for this model.
"""
from lightgbm import LGBMRegressor
from freqtrade.freqai.base_models.BaseRegressionModel import BaseRegressionModel


class CpuLightGBMRegressor(BaseRegressionModel):
    def fit(self,data_dictionary,dk,**kwargs):
        model=LGBMRegressor(**self.model_training_parameters)
        model.fit(data_dictionary['train_features'],data_dictionary['train_labels'].iloc[:,0],
                  sample_weight=data_dictionary['train_weights'])
        return model
