"""Local manual CLI uses the same durable control plane as the web UI."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['check','download-data','run-backtest','start-paper','stop-paper','status','generate-report','test'])
    action=parser.parse_args().command
    if action=='test':
        subprocess.run([sys.executable,'-m','pytest','-q'],cwd=ROOT,check=True);return
    from labapp import store,paper,paper_runtime
    store.init()
    if action=='check':
        paper_runtime.validate(paper_runtime.config())
        subprocess.run([sys.executable,'-m','pip','check'],check=True)
        result={'message':'配置安全检查通过；实盘禁止。','simulation':paper.readiness()}
    elif action=='download-data':result=paper.enqueue('prepare')
    elif action=='run-backtest':result=paper.enqueue('backtest','holdout')
    elif action=='start-paper':result=paper.start()
    elif action=='stop-paper':result=paper.stop()
    elif action=='generate-report':
        result=paper.status()
        (ROOT/'reports/paper-status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    else:result=paper.status()
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
