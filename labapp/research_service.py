"""Independent TradingAgents deployment service. No paid jobs or trading routes."""
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import threading
import time
import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from labapp import store, research_jobs, ai_costs

STOP=threading.Event()


def child_guard():
    parent=os.getppid()
    if ctypes.CDLL(None).prctl(1,signal.SIGTERM)!=0 or parent==1 or os.getppid()!=parent:
        os._exit(1)


def stop_child(child):
    if child and child.poll() is None:
        os.killpg(child.pid,signal.SIGTERM)
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=3)


def main():
    store.init()
    store.heartbeat('research','starting','验证 TradingAgents 独立环境')
    checked=subprocess.run([sys.executable,'-m','labapp.research_probe'],cwd=store.ROOT,
                           capture_output=True,text=True,timeout=45)
    if checked.returncode:
        store.heartbeat('research','error','TradingAgents 离线工作流检查失败，请查看研究服务日志')
        # The probe uses only a dummy key. Avoid printing imported-library exception payloads.
        raise RuntimeError('TradingAgents offline graph probe failed')
    manifest=json.loads((store.STATE/'deployment-tradingagents.json').read_text())
    version=importlib.metadata.version('tradingagents')
    assert version==manifest['version'] and manifest['graph_compiled']
    research_jobs.recover()
    active=None
    active_id=None
    started=0

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ('/health','/status'):
                self.send_error(404)
                return
            payload={'status':'ok','component':'TradingAgents','version':version,
                     'graph_compiled':True,'provider':'deepseek','research_enabled':active is not None,
                     'job_execution_available':True,
                     'trading_enabled':False,'llm_calls':ai_costs.summary()['calls'],
                     'note':'手动研究任务和费用闸门已接通；不执行交易'}
            body=json.dumps(payload,ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self,*args):
            pass

    server=ThreadingHTTPServer((os.environ.get('LAB_BIND','127.0.0.1'),8082),Handler)
    server.timeout=1
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:STOP.set())
    try:
        while not STOP.is_set():
            if active:
                with store.connect() as db:
                    job=db.execute('SELECT cancel FROM research_jobs WHERE id=?',(active_id,)).fetchone()
                if active.poll() is not None:
                    research_jobs.finish(active_id,'failed',error='研究进程退出但未提交完整结果；请查看费用记录，不自动重试。')
                    active=None
                elif (job and job['cancel']) or time.monotonic()-started>180:
                    cancelled=bool(job and job['cancel'])
                    stop_child(active)
                    research_jobs.finish(active_id,'cancelled' if cancelled else 'timed_out',error='研究已停止；已发送的请求可能计费，不自动重试。')
                    active=None
            if active is None:
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    queued=db.execute("SELECT * FROM research_jobs WHERE state='queued' ORDER BY at LIMIT 1").fetchone()
                    if queued:
                        if queued['cancel'] or time.time()-queued['at']>120:
                            db.execute("UPDATE research_jobs SET state='cancelled',updated=?,error='排队任务已取消或超过有效期，未发出推理。' WHERE id=?",(time.time(),queued['id']))
                            queued=None
                        else:
                            db.execute("UPDATE research_jobs SET state='running',updated=? WHERE id=?",(time.time(),queued['id']))
                if queued:
                    active_id=queued['id']
                    try:
                        active=subprocess.Popen([sys.executable,'-m','labapp.research_runner',active_id],cwd=store.ROOT,
                                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                                start_new_session=True,preexec_fn=child_guard)
                        started=time.monotonic()
                    except OSError:
                        research_jobs.finish(active_id,'failed',error='无法启动研究进程；未发送推理请求。')
                        active=None
            store.heartbeat('research','running',f'TradingAgents {version}；手动研究与费用闸门可用；交易关闭')
            server.handle_request()
    finally:
        stop_child(active)
        if active_id:
            research_jobs.finish(active_id,'interrupted',error='研究服务停止；未自动重试；请检查已发送请求的费用。')
        server.server_close()
        store.heartbeat('research','stopped','研究部署服务已停止')


if __name__=='__main__':
    main()
