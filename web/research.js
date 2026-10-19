$('validate-ai').onclick=e=>operation(e.currentTarget,async()=>{feedback('正在验证 DeepSeek 密钥和模型列表…');const r=await accountRequest('/ai-validate',{});await loadWorkspace();feedback(r.message,r.state!=='verified');});
let lastResearchSignature='';
const jobStates={queued:'排队中',running:'正在研究',completed:'已完成',failed:'研究失败',cancelled:'已停止',timed_out:'执行超时',interrupted:'曾中断 · 未自动重试'};
function renderResearch(job,costs){
  if(costs){$('ai-spent').textContent='¥ '+Number(costs.spent_cny).toFixed(4);$('ai-limit').textContent='/ '+costs.month_limit_cny;$('ai-usage').textContent=`${costs.calls} 条推理请求记录 · 预留 ¥${Number(costs.reserved_cny).toFixed(4)}`;}
  if(job===undefined)return;
  const panel=$('research-output');if(!job){panel.hidden=true;return;}
  const signature=JSON.stringify([job.id,job.state,job.progress,job.updated,job.cost_cny]);if(signature===lastResearchSignature)return;lastResearchSignature=signature;
  panel.hidden=false;
  const result=job.result;
  panel.innerHTML=`<h3>最近一次 AI 研究 · ${escapeText(job.symbol)}</h3><p><span class="badge ${job.state==='completed'?'':'neutral'}">${jobStates[job.state]||escapeText(job.state)}</span>模型 ${escapeText(job.model)} · ${job.progress} 次已完成推理</p><p>已记账 / 预留费用 ¥${Number(job.cost_cny).toFixed(4)} · 本次上限 ¥${job.run_limit_cny}</p><p class="muted">发起 ${date(job.at)} · 行情截止 ${date(job.cutoff_ms/1000)}<br>来源 ${escapeText(job.source)}<br>仅研究参考，不产生交易订单。</p>${job.error?`<p class="negative">${escapeText(job.error)}</p>`:''}${result?`<p>研究评级：<strong>${escapeText(result.rating)}</strong></p><p class="muted">${escapeText(result.limitations)}</p>`+Object.entries(result.reports).map(([key,text])=>`<details ${key==='final_trade_decision'?'open':''}><summary>${({market_report:'市场分析',investment_plan:'多空研究与汇总',trader_investment_plan:'交易员研究意见',final_trade_decision:'风险讨论与最终研究结论'})[key]||escapeText(key)}</summary><pre>${escapeText(text||'本节点未产生完整文本')}</pre></details>`).join(''):''}`;
}
async function pollResearch(){
  if(unlocked){try{const r=await accountRequest('/research');renderResearch(r.job,r.costs);}catch(e){/* Main connection indicator reports service availability. */}}
  else{$('research-output').hidden=true;$('research-output').innerHTML='';lastResearchSignature='';}
  setTimeout(pollResearch,2000);
}
window.addEventListener('lab-status',()=>{if(lastStatus.budget)renderResearch(undefined,lastStatus.budget);});
pollResearch();
