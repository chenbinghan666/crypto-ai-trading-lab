"""Charts only. Does not produce entry/exit signals."""
from freqtrade.strategy import IStrategy


class NoTradeStrategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '5m'
    startup_candle_count = 20
    can_short = False
    stoploss = -0.01
    minimal_roi = {'0': 1}

    def populate_indicators(self,dataframe,metadata):
        dataframe['sma20'] = dataframe.close.rolling(20).mean()
        return dataframe

    def populate_entry_trend(self,dataframe,metadata):
        dataframe['enter_long'] = 0
        return dataframe

    def populate_exit_trend(self,dataframe,metadata):
        dataframe['exit_long'] = 0
        return dataframe

    def confirm_trade_entry(self,**kwargs):
        return False
