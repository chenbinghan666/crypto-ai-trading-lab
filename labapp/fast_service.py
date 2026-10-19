"""Independent 15m experiment lifecycle; disabled until explicit user start."""
import fcntl
import signal
import threading
import time
from labapp import store,fast_experiment as exp
from labapp.paper_service import launch,terminate

STOP=threading.Event()


def main():
    store.init();exp.init()
    lock=(store.STATE/'fast-service.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:STOP.set())
    children={};started={};training=None;trained_at=0;due=0
    try:
        while not STOP.is_set():
            store.heartbeat('fast_manager','running','15m 独立 AI / 规则实验管理')
            s=exp.state();root=exp.folder()
            if not s['enabled']:
                terminate(training);training=None
                for arm,p in children.items():terminate(p);store.heartbeat('fast_'+arm,'stopped','实验已暂停，账本保留')
                children.clear();exp.update('stopped','15m 独立实验未运行；原 1h 账户不受影响')
            elif not (root/'ready.json').exists():
                if training and (training.poll() is not None or time.monotonic()-trained_at>180):
                    terminate(training);training=None;due=time.time()+300;exp.update('failed','实验训练失败或超时；5 分钟后重试，不调用付费 API')
                if not training and time.time()>=due:
                    trained_at=time.monotonic();training=launch('labapp.fast_model',(),'fast-training.log')
            else:
                if training:
                    if training.poll() is None:STOP.wait(1);continue
                    training=None
                if time.time()>=due:
                    for arm in exp.ARMS:
                        p=children.get(arm)
                        if p and p.poll() is not None:
                            children.pop(arm);due=time.time()+30;exp.update('reconnecting','实验引擎退出，保留账本并退避恢复');break
                        if not p:
                            children[arm]=launch('labapp.fast_runtime',(arm,),'fast-'+arm+'-service.log');started[arm]=time.time()
                with store.connect() as db:rows=list(db.execute("SELECT * FROM services WHERE name IN ('fast_rule','fast_ai')"))
                heartbeats={r['name']:r['heartbeat'] for r in rows}
                for arm,p in list(children.items()):
                    if time.time()-started[arm]>180 and time.time()-heartbeats.get('fast_'+arm,0)>60:
                        terminate(p);children.pop(arm);due=time.time()+30
                        store.heartbeat('fast_'+arm,'reconnecting','心跳过期，退避恢复');exp.update('reconnecting','实验引擎心跳过期，账本保留并恢复')
                if len(rows)==2 and all(r['state']=='running' and time.time()-r['heartbeat']<30 for r in rows):
                    exp.update('running','两个 15m 独立模拟账户均已运行；模型未经盈利验收，仅用于前向比较')
            STOP.wait(1)
    finally:
        terminate(training)
        for p in children.values():terminate(p)
        store.heartbeat('fast_manager','stopped');lock.close()


if __name__=='__main__':main()
