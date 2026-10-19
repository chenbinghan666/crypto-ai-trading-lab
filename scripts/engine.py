"""Compatibility wrapper. Direct invocation never bypasses web start checks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    operation=sys.argv[1] if len(sys.argv)>1 else ''
    if operation=='paper':
        from labapp.paper_runtime import main as run
        return run()
    if operation=='backtest':
        from scripts.futures_backtest import run
        return run('holdout')
    raise ValueError('Only guarded paper or fixed futures backtest supported')


if __name__=='__main__':main()
