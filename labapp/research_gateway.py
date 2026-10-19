"""Per-job loopback gateway: the only code allowed to issue paid DeepSeek calls."""
import hmac
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener
from urllib.error import HTTPError
from labapp import accounts, integrations, ai_connection, ai_costs, store


def forward(body,key):
    request=Request('https://api.deepseek.com/chat/completions',data=json.dumps(body).encode(),
                    headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    with build_opener(accounts.NoRedirect()).open(request,timeout=35) as response:
        raw=response.read(2_000_001)
        if len(raw)>2_000_000:
            raise ValueError('Oversized response')
        return json.loads(raw)


class Gateway:
    def __init__(self,run_id,model,identity,transport=None):
        self.run_id=run_id
        self.model=model
        self.identity=identity
        self.transport=transport or forward
        self.token=secrets.token_urlsafe(32)
        self.count=0
        self.last_error=None
        self.lock=threading.Lock()
        outer=self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path not in ('/chat/completions','/v1/chat/completions'):
                    self.send_error(404);return
                if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+outer.token):
                    self.send_error(401);return
                try:
                    length=int(self.headers.get('Content-Length',0))
                    if not 0<length<=100_000:
                        raise ValueError('请求过大或为空。')
                    body=json.loads(self.rfile.read(length))
                    result=outer.complete(body)
                    encoded=json.dumps(result).encode()
                    self.send_response(200)
                except ValueError as exc:
                    outer.last_error=str(exc)
                    encoded=json.dumps({'error':{'message':str(exc),'type':'budget_or_request_error'}}).encode()
                    self.send_response(429)
                except Exception:
                    encoded=b'{"error":{"message":"Provider request failed; no automatic retry","type":"provider_error"}}'
                    self.send_response(502)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.base_url=f'http://127.0.0.1:{self.server.server_port}/v1'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self,*args):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

    def complete(self,body):
        with self.lock:
            config=integrations.read()
            if not config or ai_connection.fingerprint(config)!=self.identity:
                raise ValueError('AI 配置发生变化，研究停止。')
            with store.connect() as db:
                job=db.execute('SELECT state,cancel FROM research_jobs WHERE id=?',(self.run_id,)).fetchone()
            if not job or job['state']!='running' or job['cancel']:
                raise ValueError('研究任务已停止。')
            if not isinstance(body,dict) or body.get('model')!=self.model or body.get('stream'):
                raise ValueError('模型或请求模式无效。')
            if self.count>=16:
                raise ValueError('单次研究最多 16 次推理请求。')
            body={**body,'max_tokens':512,'stream':False,'thinking':{'type':'disabled'},'reasoning_effort':'none'}
            body.pop('stream_options',None)
            body.pop('max_completion_tokens',None)
            # UTF-8 byte count plus envelope margin is deliberately conservative.
            max_input=len(json.dumps({k:v for k,v in body.items() if k not in ('max_tokens','stream')},ensure_ascii=False).encode())+4096
            self.count+=1
            request_id=f'{self.run_id}:{self.count}'
            ai_costs.reserve(request_id,self.model,max_input,512,run_id=self.run_id)
            try:
                result=self.transport(body,config['key'])
                usage=result['usage']
                ai_costs.settle(request_id,int(usage['prompt_tokens']),int(usage['completion_tokens']),int(usage.get('prompt_cache_hit_tokens',0)))
            except HTTPError as exc:
                if exc.code in (400,401,402,403,404,422,429):
                    ai_costs.settle(request_id,0,0)
                    self.last_error='DeepSeek 余额不足，请在服务商平台检查余额。' if exc.code==402 else f'DeepSeek 返回 HTTP {exc.code}，本次研究停止且不会自动重试。'
                else:
                    ai_costs.mark_unknown(request_id)
                raise RuntimeError('Provider rejected request') from None
            except Exception:
                ai_costs.mark_unknown(request_id)
                raise RuntimeError('Provider request outcome unknown') from None
            with store.connect() as db:
                db.execute('UPDATE research_jobs SET progress=?,updated=? WHERE id=?',(self.count,time.time(),self.run_id))
            return result
