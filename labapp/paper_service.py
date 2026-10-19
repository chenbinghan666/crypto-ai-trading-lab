"""Independent supervisor-owned lifecycle; no simulation auto-start on install."""
import ctypes
import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
from labapp import store,paper

STOP=threading.Event()


def guard():
    parent=os.getppid()
    if ctypes.CDLL(None).prctl(1,signal.SIGTERM)!=0 or parent==1 or os.getppid()!=parent:os._exit(1)


def terminate(child):
    if child and child.poll() is None:
        os.killpg(child.pid,signal.SIGTERM)
        try:child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)


def launch(module,args=(),log='paper-task.log'):
    path=store.LOGS/log
    if path.exists() and path.stat().st_size>5_000_000:path.replace(path.with_suffix('.log.1'))
    with path.open('a') as f:
        return subprocess.Popen([sys.executable,'-m',module,*args],cwd=store.ROOT,
            stdout=f,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=guard)


def update(state,message):
    with store.connect() as db:
        db.execute('UPDATE paper_control SET state=?,message=?,updated=? WHERE id=1',(state,message,time.time()))


def main():
    store.init();paper.init()
    lock=(store.STATE/'paper-service.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with store.connect() as db:
        db.execute("UPDATE paper_jobs SET state='interrupted',error='服务重启中断历史任务；请手动重试' WHERE state='running'")
    if not paper.status()['enabled']:
        update('stopped','实时模拟未启用；独立回测与模拟管理服务运行中')
    worker=None;task=None;job=None;started=0;due=0;attempts=0;probe=None;probe_due=0
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:STOP.set())
    try:
        while not STOP.is_set():
            store.heartbeat('paper','running','模拟控制与历史回测管理服务；空闲时不启动交易 Worker')
            s=paper.status();now=time.time()
            if (s['enabled'] or s['venue']=='gate') and now>=probe_due and (probe is None or not probe.is_alive()):
                probe=threading.Thread(target=paper.check_connection,daemon=True);probe.start();probe_due=now+30
            if worker:
                if not s['enabled']:
                    terminate(worker);worker=None;attempts=0;update('stopped','模拟已停止，账本与持仓保留')
                elif worker.poll() is not None:
                    worker=None;attempts+=1;due=now+min(60,2**min(attempts,6))
                    update('reconnecting','模拟进程退出，保留账本；退避后检查连接并恢复')
                    store.event('paper','warning','模拟进程退出；去重记录和原账本保留，退避重启')
                else:
                    with store.connect() as db:r=db.execute("SELECT * FROM services WHERE name='paper_engine'").fetchone()
                    ready=r and r['heartbeat']>=started and now-r['heartbeat']<30
                    if ready:update('running','官方 Freqtrade Dry-run 主循环运行；交易仅在虚拟账本中')
                    elif now-started>180:
                        terminate(worker);worker=None;due=now+30
                        update('reconnecting','模拟主循环未就绪，保留账本并退避重启')
            if not worker and s['enabled'] and now>=due:
                if s['checks_stale'] or not s['checks'].get('ok'):
                    update('reconnecting','合约网络或数据校验失败，等待恢复；不会使用现货替代')
                elif not paper.acceptance():
                    update('blocked','策略代码已变化，需重新验收；不创建交易进程')
                else:
                    started=now;worker=launch('labapp.paper_runtime',log='paper-worker-console.log')
                    update('starting','正在初始化真实 Freqtrade Dry-run 进程，等待主循环心跳')
            if not worker and not s['enabled'] and s['state']=='stopping':update('stopped','模拟已停止，账本与持仓保留')
            if task:
                with store.connect() as db:r=db.execute('SELECT cancel FROM paper_jobs WHERE id=?',(job['id'],)).fetchone()
                if r['cancel'] or now-task_started>600:
                    terminate(task)
                    with store.connect() as db:db.execute("UPDATE paper_jobs SET state='cancelled',error='任务已取消或超时' WHERE id=?",(job['id'],))
                    task=None
                elif task.poll() is not None:
                    result=None;error=None
                    if task.returncode:error='历史任务失败；请查看本机 paper-task.log。未启动实时模拟。'
                    elif job['kind']=='backtest':
                        result=json.loads((store.STATE/'futures-history'/f"backtest-{job['window']}.json").read_text())
                    else:result={'message':'官方合约历史数据与校验文件已准备好。'}
                    with store.connect() as db:
                        db.execute('UPDATE paper_jobs SET state=?,result=?,error=? WHERE id=?',('failed' if error else 'completed',json.dumps(result),error,job['id']))
                    store.event('backtest','warning' if error else 'info',error or '历史任务完成；没有启动实时模拟或实盘')
                    task=None
            if task is None:
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    r=db.execute("SELECT * FROM paper_jobs WHERE state='queued' ORDER BY at LIMIT 1").fetchone()
                    if r:
                        if r['cancel']:db.execute("UPDATE paper_jobs SET state='cancelled' WHERE id=?",(r['id'],));r=None
                        else:db.execute("UPDATE paper_jobs SET state='running' WHERE id=?",(r['id'],))
                if r:
                    job=dict(r);task_started=now
                    task=launch('scripts.prepare_futures' if job['kind']=='prepare' else 'scripts.futures_backtest',
                                () if job['kind']=='prepare' else (job['window'],str(job['capital'])))
            STOP.wait(1)
    finally:
        terminate(worker);terminate(task)
        # Keep user enablement for automatic recovery after system restart.
        update('stopped','服务停止，用户启用状态、模拟账本和去重记录保留')
        store.heartbeat('paper','stopped','独立模拟管理服务停止')
        store.heartbeat('paper_engine','stopped','模拟进程停止')
        lock.close()


if __name__=='__main__':main()
