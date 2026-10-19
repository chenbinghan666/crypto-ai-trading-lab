"""Offline deployment test of the actual upstream TradingAgents graph."""
import importlib.metadata
import json
import os
import socket
import time
from pathlib import Path

from labapp import store

SOURCE_COMMIT='1394a3f72aa4393e1a98f51b382434c4b4c2d972'


def run():
    # This is a deployment test only: no real key, network, LLM invocation or propagate().
    os.environ['DEEPSEEK_API_KEY']='deployment-probe-placeholder-not-a-real-key'
    os.environ['LANGCHAIN_TRACING_V2']='false'
    os.environ['LANGSMITH_TRACING']='false'
    original_connect=socket.socket.connect
    original_connect_ex=socket.socket.connect_ex
    attempts=[]
    def deny(*args,**kwargs):
        attempts.append(True)
        raise RuntimeError('Network forbidden during offline deployment probe')
    socket.socket.connect=deny
    socket.socket.connect_ex=deny
    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        config=DEFAULT_CONFIG.copy()
        config.update(llm_provider='deepseek',quick_think_provider='deepseek',deep_think_provider='deepseek',
                      backend_url='https://api.deepseek.com',quick_think_backend_url='https://api.deepseek.com',
                      deep_think_backend_url='https://api.deepseek.com',
                      quick_think_llm='deployment-probe',deep_think_llm='deployment-probe',
                      max_debate_rounds=1,max_risk_discuss_rounds=1,max_tool_rounds=2,max_tokens=512,
                      llm_max_retries=0,checkpoint_enabled=False,output_language='简体中文',
                      data_cache_dir=str(store.STATE/'tradingagents/cache'),
                      results_dir=str(store.STATE/'tradingagents/reports'),
                      memory_log_path=str(store.STATE/'tradingagents/memory.md'))
        graph=TradingAgentsGraph(selected_analysts=['market'],config=config)
        nodes=sorted(graph.graph.nodes)
        assert 'Trader' in nodes and 'Portfolio Manager' in nodes
        assert not attempts, 'Offline graph construction attempted a network connection'
        return {'installed':True,'version':importlib.metadata.version('tradingagents'),
                'source_commit':SOURCE_COMMIT,'graph_compiled':True,'nodes':nodes,
                'network_attempts':0,'llm_calls':0,'probe_model':'placeholder_not_remote_validated',
                'provider':'deepseek','execution_enabled':False,'checked_at':time.time()}
    finally:
        socket.socket.connect=original_connect
        socket.socket.connect_ex=original_connect_ex


if __name__=='__main__':
    result=run()
    store.STATE.mkdir(parents=True,exist_ok=True)
    (store.STATE/'deployment-tradingagents.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
