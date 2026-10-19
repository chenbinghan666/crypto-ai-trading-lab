"""Causal feature definitions shared with the independent FreqAI trainer."""
import numpy as np
from freqtrade.strategy import IStrategy

HORIZON=6
TARGET='&-return_6h'


def features(df):
    df=df.copy()
    for period in (6,12,24,48):
        df[f'%-return_{period}']=df.close.pct_change(period)
        df[f'%-ma_ratio_{period}']=df.close/df.close.rolling(period).mean()-1
        df[f'%-volatility_{period}']=df.close.pct_change().rolling(period).std()
    df['%-range']=(df.high-df.low)/df.close
    df['%-volume_ratio']=df.volume/df.volume.rolling(24).mean().replace(0,np.nan)
    df['%-hour_sin']=np.sin(df.date.dt.hour*2*np.pi/24)
    df['%-hour_cos']=np.cos(df.date.dt.hour*2*np.pi/24)
    return df.replace([np.inf,-np.inf],np.nan)


class FreqaiCpuResearch(IStrategy):
    INTERFACE_VERSION=3
    timeframe='1h'
    can_short=True
    startup_candle_count=100
    stoploss=-0.02
    minimal_roi={'0':0.04}

    def feature_engineering_standard(self,dataframe,metadata,**kwargs):return features(dataframe)

    def set_freqai_targets(self,dataframe,metadata,**kwargs):
        dataframe[TARGET]=dataframe.close.shift(-HORIZON)/dataframe.close-1
        return dataframe

    def populate_indicators(self,dataframe,metadata):return self.freqai.start(dataframe,metadata,self)

    def populate_entry_trend(self,dataframe,metadata):
        # Research-only until independent strategy/cost validation and user approval.
        dataframe['enter_long']=0;dataframe['enter_short']=0
        return dataframe

    def populate_exit_trend(self,dataframe,metadata):
        dataframe['exit_long']=0;dataframe['exit_short']=0
        return dataframe

    def confirm_trade_entry(self,**kwargs):return False
