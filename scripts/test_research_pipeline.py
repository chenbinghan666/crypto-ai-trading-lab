"""Actual upstream graph + gateway + ledger, with fake responses and no external IO."""
import json
import os
import socket
import tempfile
import time
from pathlib import Path


def schema_value(schema,root=None):
    root=root or schema
    if '$ref' in schema:
        target=root
        for key in schema['$ref'].removeprefix('#/').split('/'):
            target=target[key]
        return schema_value(target,root)
    if 'enum' in schema:
        return next((x for x in schema['enum'] if str(x).lower()=='hold'),schema['enum'][0])
    for key in ('anyOf','oneOf'):
        if key in schema:
            return schema_value(next((x for x in schema[key] if x.get('type')!='null'),schema[key][0]),root)
    kind=schema.get('type','object' if 'properties' in schema else 'string')
    if kind=='object':return {k:schema_value(v,root) for k,v in schema.get('properties',{}).items()}
    if kind=='array':return []
    if kind=='boolean':return False
    if kind in ('number','integer'):return schema.get('minimum',0)
    if kind=='null':return None
    return '离线测试数据；仅 HOLD；不是市场判断。'


def main():
    import sys
    optimization='--optimization' in sys.argv
    external_attempts=[]
    original_connect=socket.socket.connect
    original_getaddrinfo=socket.getaddrinfo
    def local_connect(self,address):
        if not isinstance(address,tuple) or address[0] not in ('127.0.0.1','::1','localhost'):
            external_attempts.append(True)
            raise RuntimeError('External network forbidden in offline pipeline test')
        return original_connect(self,address)
    def local_dns(host,*args,**kwargs):
        if host not in ('127.0.0.1','::1','localhost'):
            external_attempts.append(True)
            raise RuntimeError('External DNS forbidden in offline pipeline test')
        return original_getaddrinfo(host,*args,**kwargs)
    with tempfile.TemporaryDirectory(prefix='crypto-ai-offline-') as temp:
        os.environ['LAB_STATE_DIR']=str(Path(temp)/'state')
        os.environ['LAB_LOG_DIR']=str(Path(temp)/'logs')
        os.environ['LAB_SECRETS_DIR']=str(Path(temp)/'secrets')
        from labapp import store,integrations,ai_connection,research_jobs,ai_costs
        from labapp.research_gateway import Gateway
        from labapp.research_runner import execute
        store.init();research_jobs.init()
        integrations.save({'key':'offline-test-not-real-key-'+'K'*24,'model':'deepseek-v4-pro','budget_cny':50})
        config=integrations.read()
        calls=[]
        def fake_provider(body,key):
            calls.append(body['model'])
            message={'role':'assistant','content':'离线测试报告：HOLD。没有真实市场判断，不产生订单。'}
            reason='stop'
            tools=body.get('tools')
            if tools:
                name=(body.get('tool_choice') or {}).get('function',{}).get('name') if isinstance(body.get('tool_choice'),dict) else None
                tool=next((t['function'] for t in tools if t['function']['name']==name),tools[0]['function'])
                args=schema_value(tool.get('parameters',{}))
                message={'role':'assistant','content':None,'tool_calls':[{'id':'offline-tool-'+str(len(calls)),'type':'function','function':{'name':tool['name'],'arguments':json.dumps(args,ensure_ascii=False)}}]}
                reason='tool_calls'
            elif body.get('response_format',{}).get('type')=='json_schema':
                schema=body['response_format']['json_schema']['schema']
                message['content']=json.dumps(schema_value(schema),ensure_ascii=False)
            elif body.get('response_format',{}).get('type')=='json_object':
                message['content']=json.dumps({'fast':10,'slow':40,'model_filter':True,'prediction_threshold':.002})
            return {'id':'offline-'+str(len(calls)),'object':'chat.completion','created':int(time.time()),
                    'model':body['model'],'choices':[{'index':0,'message':message,'finish_reason':reason}],
                    'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}
        payload={'id':'offline-test','symbol':'BTC/USDT','model':config['model'],'source':'offline_fixture_not_market_data',
                 'market_type':'spot_reference','cutoff_ms':int(time.time()*1000)-60000,
                 'analysis':{'count':120,'return_pct':0,'high':101,'low':99,'sma20':100},
                 'candles':[{'open_ms':1,'open':100,'high':101,'low':99,'close':100,'volume':1}]}
        if optimization:
            payload.update(purpose='optimization',review={'eligible_closed_trades':0,'net_realized_pnl':0},
                           incumbent={'fast':20,'slow':60,'model_filter':False,'prediction_threshold':0})
        with store.connect() as db:
            db.execute('INSERT INTO research_jobs VALUES(?,?,?,?,?,?,?,?,?)',('offline-test',time.time(),time.time(),'running',0,json.dumps(payload),None,None,0))
        socket.socket.connect=local_connect
        socket.getaddrinfo=local_dns
        try:
            with Gateway('offline-test',config['model'],ai_connection.fingerprint(config),transport=fake_provider) as gateway:
                result=execute(payload,gateway)
            assert result['research_only'] and result['trading_eligible'] is False
            if optimization:assert result['proposal']=={'fast':10,'slow':40,'model_filter':True,'prediction_threshold':.002}
            assert not external_attempts and len(calls)>=7
            assert ai_costs.summary()['calls']==len(calls)
            with store.connect() as db:
                assert db.execute('SELECT count(*) FROM order_intents').fetchone()[0]==0
        finally:
            socket.socket.connect=original_connect
            socket.getaddrinfo=original_getaddrinfo
        evidence={'passed':True,'actual_tradingagents_graph':True,'fake_provider_responses':True,
                  'fake_model_calls':len(calls),'external_connections':len(external_attempts),
                  'live_orders':0,'paid_calls':0,'note':'测试数据和费用账本均在临时隔离目录，不是市场研究结果。'}
        evidence['optimization_proposal_validated']=optimization
        target=store.ROOT/'reports/evidence/phase3'/('optimization_graph_offline.json' if optimization else 'research_pipeline_offline.json')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
        print(json.dumps(evidence,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
