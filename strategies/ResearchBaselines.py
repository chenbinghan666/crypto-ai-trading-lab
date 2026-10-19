"""Fixed, unoptimized stage-2 baselines. Paper mode is observation-only."""
import logging
from datetime import datetime

from pandas import DataFrame
from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)


class TrendBaseline(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = False
    startup_candle_count = 100
    process_only_new_candles = True
    stoploss = -0.01
    minimal_roi = {'0': 0.03}
    use_exit_signal = True
    position_adjustment_enable = False

    def bot_start(self, **kwargs):
        if self.config.get('dry_run') is not True:
            raise RuntimeError('This project forbids live trading')
        if self.config.get('trading_mode') != 'spot':
            raise RuntimeError('Stage 2 only supports spot')

    @property
    def protections(self):
        return [
            {'method':'CooldownPeriod','stop_duration_candles':1},
            {'method':'MaxDrawdown','lookback_period_candles':10000,'trade_limit':1,
             'stop_duration_candles':10000,'max_allowed_drawdown':0.10},
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['fast'] = dataframe.close.rolling(20).mean()
        dataframe['slow'] = dataframe.close.rolling(60).mean()
        dataframe['std'] = dataframe.close.rolling(20).std()
        dataframe['prior_high'] = dataframe.high.rolling(20).max().shift(1)
        dataframe['prior_low'] = dataframe.low.rolling(10).min().shift(1)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        cross = (dataframe.fast > dataframe.slow) & (dataframe.fast.shift(1) <= dataframe.slow.shift(1))
        dataframe['enter_long'] = (cross & (dataframe.volume > 0)).astype(int)
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['exit_long'] = (dataframe.fast < dataframe.slow).astype(int)
        return dataframe

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str, **kwargs) -> float:
        # Include the conservative round-trip cost allowance in planned risk.
        equity = self.wallets.get_total_stake_amount()
        stake = min(equity * 0.005 / (abs(self.stoploss) + 2 * self.config.get('fee', 0.0015)), max_stake)
        return 0.0 if min_stake is not None and stake < min_stake else stake

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str | None,
                            side: str, **kwargs) -> bool:
        mode = self.config.get('runmode')
        mode = getattr(mode, 'value', mode)
        if mode == 'dry_run':
            logger.warning('PHASE2_HOLD: paper observation only; validated independent entry gate pending')
            return False
        return mode in ('backtest', 'hyperopt') and side == 'long'


class MeanReversionBaseline(TrendBaseline):
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['enter_long'] = ((dataframe.close < dataframe.fast - 2 * dataframe['std']) &
                                   (dataframe.volume > 0)).astype(int)
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['exit_long'] = (dataframe.close >= dataframe.fast).astype(int)
        return dataframe


class BreakoutBaseline(TrendBaseline):
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['enter_long'] = ((dataframe.close > dataframe.prior_high) &
                                   (dataframe.volume > 0)).astype(int)
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['exit_long'] = (dataframe.close < dataframe.prior_low).astype(int)
        return dataframe
