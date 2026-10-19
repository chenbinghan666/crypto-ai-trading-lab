"""Independent process supervisor. No UI automation or Codex connection required."""
import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
import ctypes
from urllib.request import urlopen

import psutil
from labapp.store import ROOT, STATE, LOGS, connect, event, heartbeat, init, process_identity

STOP = threading.Event()
SERVICES = {'market':'labapp.market','dashboard':'labapp.web','frequi':'labapp.frequi','paper':'labapp.paper_service','training':'labapp.training_service','optimizer':'labapp.optimizer_service'}
SERVICES['fast_manager']='labapp.fast_service'
if os.environ.get('LAB_EXTERNAL_RESEARCH') != '1':
    SERVICES['research']='labapp.research_service'


def terminate_with_parent():
    # Linux/WSL: don't leave orphan listeners if the supervisor crashes.
    parent = os.getppid()
    if ctypes.CDLL(None).prctl(1,signal.SIGTERM) != 0:
        os._exit(1)
    if parent == 1 or os.getppid() != parent:
        os._exit(1)


def healthy(name):
    if name in ('market','paper','training','optimizer','fast_manager'):
        with connect() as c:
            row = c.execute('SELECT heartbeat FROM services WHERE name=?',(name,)).fetchone()
        return row is not None and time.time()-row[0] < 100
    port,path = (8080,'/health') if name == 'dashboard' else (8082,'/health') if name=='research' else (8081,'/api/v1/ping')
    try:
        with urlopen(f'http://127.0.0.1:{port}{path}',timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    init()
    lock = open(STATE/'supervisor.lock','w')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('System is already running')
    pidfile = STATE/'supervisor.json'
    pidfile.write_text(json.dumps({'pid':os.getpid(),'identity':process_identity(os.getpid())}))
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_: STOP.set())
    children, failures, due, started, checks = {}, {}, {}, {}, {}
    event('supervisor','info','独立系统启动：仅行情采集和管理页面，交易关闭')
    try:
        while not STOP.is_set():
            now = time.time()
            heartbeat('supervisor','running','独立进程守护；与 Codex 无连接')
            for name,module in SERVICES.items():
                child = children.get(name)
                if child and child.poll() is None:
                    if now-started[name] > 15 and now-checks.get(name,0) > 10:
                        checks[name] = now
                        if healthy(name):
                            if name not in ('market','paper','training','optimizer','fast_manager'):
                                heartbeat(name,'running','HTTP 健康检查通过；交易未启用')
                            if now-started[name] > 60:
                                failures[name] = 0
                        elif now-started[name] > 120:
                            event(name,'warning','服务无响应，终止并退避重启')
                            child.terminate()
                    continue
                if child:
                    event(name,'warning',f'服务退出（code={child.returncode}），等待自动重启')
                    failures[name] = failures.get(name,0)+1
                    due[name] = now + min(60,2**min(failures[name],6))
                    heartbeat(name,'restarting','异常退出，退避后重启')
                    del children[name]
                if now < due.get(name,0):
                    continue
                path = LOGS/f'{name}-service.log'
                if path.exists() and path.stat().st_size > 5_000_000:
                    path.replace(path.with_suffix('.log.1'))
                python=sys.executable
                if name=='research':
                    python=os.environ.get('LAB_RESEARCH_PYTHON',str(__import__('pathlib').Path.home()/'.local/share/crypto-ai-trading-lab/tradingagents-venv/bin/python'))
                with open(path,'a') as logfile:
                    children[name] = subprocess.Popen([python,'-m',module],cwd=ROOT,
                                                     stdout=logfile,stderr=subprocess.STDOUT,
                                                     preexec_fn=terminate_with_parent)
                started[name] = now
                heartbeat(name,'starting',f'PID {children[name].pid}')
            STOP.wait(2)
    finally:
        for p in children.values():
            if p.poll() is None:
                p.terminate()
        for name,p in children.items():
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill(); p.wait(timeout=5)
            heartbeat(name,'stopped','系统已停止')
        heartbeat('supervisor','stopped','正常停止')
        event('supervisor','info','系统停止；状态保留，未运行交易')
        pidfile.unlink(missing_ok=True)
        lock.close()


if __name__ == '__main__':
    main()
