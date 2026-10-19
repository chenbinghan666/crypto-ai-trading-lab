import argparse
import json
import signal
import time
import psutil
from labapp.store import ROOT, STATE, init, snapshot, process_identity


def running_process():
    path = STATE/'supervisor.json'
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    try:
        p = psutil.Process(data['pid'])
        if process_identity(p.pid)==data.get('identity') and 'labapp.supervisor' in p.cmdline() and p.cwd()==str(ROOT) and p.status() != psutil.STATUS_ZOMBIE:
            return p
    except (psutil.NoSuchProcess,FileNotFoundError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command',choices=['status','stop','credentials','is-running'])
    args = parser.parse_args()
    init()
    if args.command == 'credentials':
        path = STATE/'frequi-auth.json'
        if not path.exists():
            raise SystemExit('请先启动系统')
        data = json.loads(path.read_text())
        print('FreqUI http://127.0.0.1:8081\n用户名: '+data['username']+'\n密码: '+data['password'])
        return
    p = running_process()
    if args.command == 'is-running':
        raise SystemExit(0 if p else 1)
    if args.command == 'stop':
        if p:
            p.send_signal(signal.SIGTERM)
            for _ in range(30):
                if running_process() is None:
                    break
                time.sleep(1)
            else:
                raise SystemExit('停止超时，请查看日志；没有误杀其他进程')
        print('系统已停止，数据保留。')
    else:
        s = snapshot()
        print(json.dumps({'running':p is not None,'services':s['services'],'market':s['market'],
                          'live_enabled':False,'paper_enabled':__import__('labapp.paper',fromlist=['status']).status()['enabled']},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
