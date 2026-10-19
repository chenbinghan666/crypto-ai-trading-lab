"""Persistent autonomous scheduler, no Codex connection or manual approval loop."""
import fcntl
import signal
import threading
import time
import uuid
from labapp import store,optimizer,paper
from labapp.paper_service import launch,terminate

STOP=threading.Event()


def main():
    store.init();optimizer.init()
    lock=(store.STATE/'optimizer-service.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with store.connect() as db:
        # A paid request interrupted by a service crash is never blindly reissued.
        ids=[r[0] for r in db.execute("SELECT research_id FROM optimizer_runs WHERE state='running' AND research_id IS NOT NULL")]
        for identifier in ids:
            db.execute("UPDATE research_jobs SET cancel=1 WHERE id=? AND state IN ('queued','running')",(identifier,))
        db.execute("UPDATE optimizer_runs SET state='interrupted',error='服务中断，本轮不自动重发' WHERE state='running'")
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:STOP.set())
    child=None;identifier=None;started=0
    try:
        while not STOP.is_set():
            store.heartbeat('optimizer','running','自动复盘、模型训练、策略验证与模拟版本管理')
            optimizer.reconcile();s=optimizer.status()
            if child:
                if not s['enabled'] or time.monotonic()-started>600:
                    terminate(child);optimizer.finish(identifier,'cancelled',error='自动优化暂停或超时，原版本保留。');child=None
                elif child.poll() is not None:
                    optimizer.finish(identifier,'failed',error='优化进程退出，原版本保留。');child=None
            if child is None and s['enabled'] and time.time()>=s['next_due']:
                now=time.time();identifier=uuid.uuid4().hex
                with store.connect() as db:
                    db.execute('UPDATE optimizer_control SET next_due=? WHERE id=1',(now+optimizer.INTERVAL,))
                if paper.status()['venue']!='gate':
                    with store.connect() as db:db.execute("UPDATE optimizer_control SET message='自动优化当前只支持 Gate 合约；等待市场匹配' WHERE id=1")
                else:
                    with store.connect() as db:
                        pending=db.execute("SELECT id FROM optimizer_runs WHERE state='waiting_forward' ORDER BY at LIMIT 1").fetchone()
                        if pending:
                            identifier=pending['id'];db.execute("UPDATE optimizer_runs SET state='running',stage='检查未来验证数据' WHERE id=?",(identifier,))
                        else:db.execute('INSERT INTO optimizer_runs VALUES(?,?,?,?,?,?,?,?)',(identifier,now,'running','启动中',0,None,None,None))
                    started=time.monotonic();child=launch('labapp.optimizer_runner',(identifier,),'optimizer-task.log')
            STOP.wait(1)
    finally:
        terminate(child)
        if identifier:optimizer.finish(identifier,'interrupted',error='优化服务停止，本轮不自动重发。')
        if identifier:
            from labapp import training
            training.finish(identifier,'interrupted',error='优化服务停止中断候选模型训练。')
        store.heartbeat('optimizer','stopped','自动优化服务已停止');lock.close()


if __name__=='__main__':main()
