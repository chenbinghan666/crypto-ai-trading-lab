"""Independent, bounded CPU training worker owned by the system supervisor."""
import fcntl
import os
import signal
import threading
import time
from labapp import store,training
from labapp.paper_service import launch,terminate

STOP=threading.Event()


def main():
    store.init();training.init()
    lock=(store.STATE/'training-service.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    training.recover()
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[key]='2'
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:STOP.set())
    child=None;identifier=None;started=0
    try:
        while not STOP.is_set():
            store.heartbeat('training','running','独立 FreqAI CPU 训练服务；2 线程；不自动应用模型')
            if child:
                with store.connect() as db:r=db.execute('SELECT cancel FROM training_jobs WHERE id=?',(identifier,)).fetchone()
                if r['cancel'] or time.monotonic()-started>180:
                    terminate(child);training.finish(identifier,'cancelled',error='任务已停止或超过 180 秒；原模型保留。');child=None
                elif child.poll() is not None:
                    training.finish(identifier,'failed',error='训练进程退出但未完成结果提交；请手动重试。');child=None
            if child is None:
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    r=db.execute("SELECT * FROM training_jobs WHERE state='queued' ORDER BY at LIMIT 1").fetchone()
                    if r:
                        if r['cancel'] or time.time()-r['at']>300:
                            db.execute("UPDATE training_jobs SET state='cancelled',stage='已取消或排队超时' WHERE id=?",(r['id'],));r=None
                        else:db.execute("UPDATE training_jobs SET state='running',stage='训练进程启动中',updated=? WHERE id=?",(time.time(),r['id']))
                if r:
                    identifier=r['id'];started=time.monotonic()
                    child=launch('labapp.training_runner',(identifier,),'training-task.log')
            STOP.wait(.5)
    finally:
        terminate(child)
        if identifier:training.finish(identifier,'interrupted',error='服务停止中断训练，原模型保留。')
        store.heartbeat('training','stopped','CPU 训练服务停止');lock.close()


if __name__=='__main__':main()
