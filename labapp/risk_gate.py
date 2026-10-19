"""Deterministic entry gate. No model can change these limits."""
import math
from datetime import timezone

VERSION = 'futures-risk-v2-gate-fee'
LIMITS = {'leverage':1.0,'risk_fraction':0.005,'exposure_fraction':0.20,
          'daily_loss_fraction':0.02,'drawdown_fraction':0.10,
          'daily_risk_fraction':0.02,'loss_streak':3,'cooldown_hours':24,
          'stop_fraction':0.02,'fee_per_side':0.00075,'slippage_per_side':0.0005}


def stake(equity, maximum, minimum=None):
    if not all(math.isfinite(v) and v>0 for v in (equity, maximum)):
        return 0.0
    # Include both fees and adverse slippage in the planned loss.
    risk_cost=LIMITS['stop_fraction']+2*(LIMITS['fee_per_side']+LIMITS['slippage_per_side'])
    value=min(equity*LIMITS['risk_fraction']/risk_cost,equity*LIMITS['exposure_fraction'],maximum)
    return 0.0 if minimum is not None and value<minimum else value


def check(initial, equity, closed, opened, now, planned_stake):
    """closed/opened are plain records, usable by backtests and the real dry-run."""
    if not all(math.isfinite(v) and v>0 for v in (initial,equity,planned_stake)):
        return False,'invalid_equity_or_stake'
    if opened:
        return False,'one_position_limit'
    if planned_stake>stake(equity,equity)+1e-8:
        return False,'position_risk_limit'
    now=now.astimezone(timezone.utc)
    start=now.replace(hour=0,minute=0,second=0,microsecond=0)
    records=sorted(closed,key=lambda x:x['close_date'])
    balance=initial;peak=initial;daily_pnl=0.0;day_start=initial;day_risk=0.0
    for r in records:
        pnl=float(r['profit'])
        if not math.isfinite(pnl):return False,'invalid_trade_history'
        if r['close_date']<start:day_start+=pnl
        else:daily_pnl+=pnl
        if r['open_date']>=start:
            day_risk+=r['stake']*(LIMITS['stop_fraction']+2*(LIMITS['fee_per_side']+LIMITS['slippage_per_side']))
        balance+=pnl;peak=max(peak,balance)
    if equity<=peak*(1-LIMITS['drawdown_fraction']):return False,'drawdown_stop'
    if daily_pnl<=-max(day_start,0)*LIMITS['daily_loss_fraction']:return False,'daily_loss_stop'
    planned_risk=planned_stake*(LIMITS['stop_fraction']+2*(LIMITS['fee_per_side']+LIMITS['slippage_per_side']))
    if day_risk+planned_risk>max(day_start,0)*LIMITS['daily_risk_fraction']+1e-8:
        return False,'daily_new_risk_limit'
    recent=records[-LIMITS['loss_streak']:]
    if len(recent)==LIMITS['loss_streak'] and all(r['profit']<0 for r in recent):
        if (now-recent[-1]['close_date']).total_seconds()<LIMITS['cooldown_hours']*3600:
            return False,'loss_streak_cooldown'
    return True,'allowed'
