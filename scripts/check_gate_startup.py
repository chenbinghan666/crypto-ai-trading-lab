"""Initialize a real Freqtrade bot in a temporary ledger, no trading loop/entries."""
import json
import tempfile
from pathlib import Path
from labapp import store,paper_runtime


def main():
    original=store.STATE
    with tempfile.TemporaryDirectory(prefix='gate-init-') as temp:
        store.STATE=Path(temp)/'state';store.STATE.mkdir()
        try:
            c=paper_runtime.config(1000,'gate');paper_runtime.validate(c)
            c['initial_state']='stopped'
            path=store.STATE/'config.json';path.write_text(json.dumps(c))
            from freqtrade.configuration import Configuration
            from freqtrade.enums import RunMode
            c=Configuration({'config':[str(path)],'strategy':'FuturesBaseline',
                'user_data_dir':str(store.ROOT/'user_data'),'strategy_path':str(store.ROOT/'strategies')},RunMode.DRY_RUN).get_config()
            paper_runtime.public_only();paper_runtime.restrict_gate_tiers()
            from freqtrade.freqtradebot import FreqtradeBot
            from freqtrade.persistence import Trade,Order
            bot=FreqtradeBot(c)
            try:
                bot.startup()
                from freqtrade.enums import CandleType
                rows=bot.exchange.refresh_latest_ohlcv([(paper_runtime.PAIR,'1h',CandleType.FUTURES)])
                frame=rows[(paper_runtime.PAIR,'1h',CandleType.FUTURES)]
                report={'passed':len(frame)>=100,'exchange':bot.exchange.name,'dry_run':c['dry_run'],
                    'candles':len(frame),'contract_size':bot.exchange.markets[paper_runtime.PAIR]['contractSize'],
                    'open_trades':len(Trade.get_trades_proxy(is_open=True)),
                    'orders':Trade.session.query(Order).count(),'trading_loop_started':False,
                    'production_ledger_created':(original/'futures-paper-gate.sqlite').exists()}
            finally:bot.cleanup()
        finally:store.STATE=original
    target=store.ROOT/'reports/evidence/phase3/gate-startup.json'
    target.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    if not report['passed'] or report['orders']:raise RuntimeError('Gate initialization failed')


if __name__=='__main__':main()
