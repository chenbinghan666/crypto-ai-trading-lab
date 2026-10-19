"""One official TradingAgents graph run, grounded only in frozen public data."""
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from labapp import store, research_jobs
from labapp.research_gateway import Gateway


def make_graph(payload,gateway):
    os.environ['DEEPSEEK_API_KEY']=gateway.token
    os.environ['LANGCHAIN_TRACING_V2']='false'
    os.environ['LANGSMITH_TRACING']='false'
    os.environ['NO_PROXY']='127.0.0.1,localhost'
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.graph import setup,analyst_execution
    from langchain_core.messages import SystemMessage,HumanMessage

    # Adapt the market analyst to local, dated crypto data; do not silently ask
    # stock/fundamentals tools to interpret a Binance perpetual instrument.
    def local_market_analyst(llm):
        def node(state):
            prompt=('你是加密资产市场分析师。仅使用下列冻结的公开行情，所有数字必须来自数据。'
                    '说明来源、市场类型、截止时间和样本仅约两小时的限制。禁止捏造新闻、基本面、资金费率、'
                    '胜率或回测收益；没有足够证据就建议 HOLD。现货参考价格不代表永续合约报价。'
                    '这是一份研究报告，不下单。简体中文，200字以内。')
            if payload.get('purpose')=='optimization':
                prompt=('你是模拟合约策略复盘分析师。仅用开发数据和开发截止前的真实模拟成交记录，'
                    '指出成本、趋势与样本限制。验证和最终检验数据未提供，禁止编造这些结果。'
                    '没有成交就明确说明暂无成交复盘，不编造胜率。Gate 永续研究，不下单。简体中文200字以内。')
            facts={k:payload[k] for k in ('symbol','market_type','source','cutoff_ms','analysis','candles')}
            if payload.get('purpose')=='optimization':facts.update(review=payload['review'],incumbent=payload['incumbent'])
            response=llm.invoke([SystemMessage(content=prompt),HumanMessage(content=json.dumps(facts,ensure_ascii=False))])
            report=response.content if isinstance(response.content,str) else json.dumps(response.content,ensure_ascii=False)
            return {'messages':[response],'market_report':report}
        return node
    original_factory=setup.create_market_analyst
    original_spec=analyst_execution.ANALYST_NODE_SPECS['market']
    setup.create_market_analyst=local_market_analyst
    analyst_execution.ANALYST_NODE_SPECS['market']=analyst_execution.AnalystNodeSpec('market','Market Analyst','market_report',())
    config=DEFAULT_CONFIG.copy()
    directory=store.STATE/'tradingagents/jobs'/payload['id']
    config.update(llm_provider='deepseek',quick_think_provider='deepseek',deep_think_provider='deepseek',
                  backend_url=gateway.base_url,quick_think_backend_url=gateway.base_url,deep_think_backend_url=gateway.base_url,
                  quick_think_llm=payload['model'],deep_think_llm=payload['model'],max_tokens=512,llm_max_retries=0,
                  max_debate_rounds=1,max_risk_discuss_rounds=1,max_tool_rounds=1,max_recur_limit=32,
                  checkpoint_enabled=False,output_language='简体中文',data_cache_dir=str(directory/'cache'),
                  results_dir=str(directory/'reports'),memory_log_path=str(directory/'memory.md'))
    try:
        graph=TradingAgentsGraph(selected_analysts=['market'],config=config)
    finally:
        setup.create_market_analyst=original_factory
        analyst_execution.ANALYST_NODE_SPECS['market']=original_spec
    return graph


def execute(payload,gateway):
    graph=make_graph(payload,gateway)
    symbol=payload['symbol'].replace('/','')
    date=datetime.fromtimestamp(payload['cutoff_ms']/1000,ZoneInfo('Asia/Singapore')).strftime('%Y-%m-%d')
    context=(f"Crypto research only. Instrument: {payload['symbol']}. Source: {payload['source']}. "
             f"Market type: {payload['market_type']}. Data cutoff UTC ms: {payload['cutoff_ms']}. "
             'Only the provided closed candles are available. No futures funding, news or fundamentals data. '
             'No account holdings are supplied. Do not invent them. No orders will be placed.')
    initial=graph.propagator.create_initial_state(symbol,date,asset_type='crypto',instrument_context=context)
    final=graph.graph.invoke(initial,config={'recursion_limit':32})
    from tradingagents.agents.rating import run_rating
    result={'rating':str(run_rating(final)),'symbol':payload['symbol'],'source':payload['source'],
            'market_type':payload['market_type'],'cutoff_ms':payload['cutoff_ms'],'model':payload['model'],
            'research_only':True,'trading_eligible':False,
            'reports':{key:str(final.get(key,''))[:20000] for key in ('market_report','investment_plan','trader_investment_plan','final_trade_decision')},
            'limitations':'仅冻结的分钟行情研究；无新闻、资金费率、回测验证或交易执行。'}
    if payload.get('purpose')=='optimization':
        # One bounded JSON proposal after the actual multi-agent graph has reviewed the data.
        prompt=('仅输出 JSON。根据研究给出一个保守候选，字段必须且只能为 fast、slow、model_filter、prediction_threshold。'
            'fast 只能为10/20/30，slow只能为40/60/90，model_filter为布尔值，prediction_threshold只能为0/0.002/0.005。'
            '关闭model_filter时阈值须0。不能改变风险、杠杆或代码。没有验证集或最终检验结果，不得声称已盈利。'
            '示例 {"fast":20,"slow":60,"model_filter":false,"prediction_threshold":0}。')
        response=gateway.complete({'model':payload['model'],'response_format':{'type':'json_object'},
            'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps({'review':payload['review'],
                'incumbent':payload['incumbent'],'analysis':payload['analysis'],'reports':result['reports']},ensure_ascii=False)}]})
        from labapp.optimizer import validate_params
        result['proposal']=validate_params(json.loads(response['choices'][0]['message']['content']))
        result['purpose']='optimization'
        result['limitations']='仅开发数据的候选建议；必须独立通过含成本回测，不能直接触发订单。'
    graph.save_reports(final,symbol,html=False)
    return result


def main(identifier):
    with store.connect() as db:
        row=db.execute("SELECT * FROM research_jobs WHERE id=? AND state='running'",(identifier,)).fetchone()
    if not row:
        return
    payload={**json.loads(row['payload']),'id':identifier}
    gateway=Gateway(identifier,payload['model'],payload['credential_fingerprint'])
    try:
        with gateway:
            result=execute(payload,gateway)
        research_jobs.finish(identifier,'completed',result=result)
        store.event('research','info','AI 研究已完成；报告与费用已记录；未触发交易')
    except Exception:
        message=gateway.last_error or '研究未完成：模型返回未通过解析或服务连接异常；未自动重试，请检查费用记录。'
        research_jobs.finish(identifier,'failed',error=message)
        store.event('research','warning',message)


if __name__=='__main__':
    main(sys.argv[1])
