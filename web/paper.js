let paperDraft=false,paperLoaded=false,paperSignature='';
function openPaperPanel(){document.querySelector('[data-pane="module-ops"]').click();requestAnimationFrame(()=>$('paper-panel').scrollIntoView({behavior:'smooth'}));}
document.querySelectorAll('[data-open-paper]').forEach(link=>link.addEventListener('click',openPaperPanel));
window.addEventListener('hashchange',()=>{if(location.hash==='#paper-panel')openPaperPanel();});
if(location.hash==='#paper-panel')openPaperPanel();
const paperStates={stopped:'未运行',starting:'启动中',running:'实时模拟运行中',stopping:'停止中',reconnecting:'合约连接中断 / 恢复中',blocked:'启动被拦截'};
const splitNames={development:'开发 · 2025 年 1 月',validation:'验证 · 2025 年 2 月',holdout:'最终检验 · 2025 年 3 月'};
$('paper-settings').oninput=()=>{paperDraft=true;};
$('paper-settings').onsubmit=e=>{e.preventDefault();operation(e.submitter,async()=>{const r=await accountRequest('/paper-action',{action:'settings',capital:Number($('paper-capital').value),agent_mode:$('paper-agent-mode').value,venue:$('paper-venue').value});paperDraft=false;$('paper-message').textContent=r.message;feedback(r.message);await pollPaperOnce();await loadWorkspace();});};
$('paper-panel').addEventListener('click',e=>{const b=e.target;if(!b.dataset.paper)return;operation(b,async()=>{
  const action=b.dataset.paper;let payload={action};
  if(action==='start'&&paperDraft)throw Error('请先保存模拟设置，再启动。');
  if(action==='backtest')payload.window=$('paper-window').value;
  if(action==='approve-research'){const r=await accountRequest('/research');if(!r.job)throw Error('尚无可批准的研究报告。');payload.job_id=r.job.id;}
  const r=await accountRequest('/paper-action',payload);$('paper-message').textContent=r.message;feedback(r.message);await pollPaperOnce();await loadWorkspace();
});});
async function pollPaperOnce(){
  if(!unlocked)return;const s=await accountRequest('/paper');if(!unlocked)return;
  renderPaperMonitor(s);
  $('paper-message').textContent=s.message;
  paperLoaded=true;$('paper-state').textContent=paperStates[s.state]||s.state;
  if(!paperDraft){$('paper-capital').value=s.capital;$('paper-agent-mode').value=s.agent_mode;$('paper-venue').value=s.venue;}
  $('paper-market-description').textContent=`官方 Freqtrade · ${s.venue.toUpperCase()} BTC/USDT 永续 · 1 小时 · 固定 1 倍 · 独立虚拟账本`;
  $('paper-risk').textContent=`单笔风险 ≤0.5% · 仓位金额 ≤20% · 每日亏损 2% 停止新仓 · 回撤 10% 停止新仓 · 连亏 3 次冷却 24 小时 · ${s.engineering_accepted?'工程离线验收通过':'工程验收待完成'}。停止后持仓与账本保留。`;
  const signature=JSON.stringify([s.venue,s.state,s.message,s.updated,s.checks,s.checks_stale,s.job,s.orders,s.trades,s.evaluations]);
  if(signature===paperSignature)return;paperSignature=signature;
  const checks=`<p class="${s.checks.ok&&!s.checks_stale?'positive':'negative'}">${s.venue.toUpperCase()} 实时合约：${escapeText(s.checks.message)}${s.checks_stale?'（检查未做或已过期）':''}</p>`+(s.checks.mark_price?`<p>标记价格 ${number(s.checks.mark_price)} USDT · 资金费率 ${(s.checks.funding_rate*100).toFixed(4)}% · 接收于 ${date(s.checks.received_at)} · 后台每 30 秒检查</p>`:'')+'<p class="muted">下方历史回测属于 Binance 数据，不代表当前 Gate 市场表现。模拟下单无需交易所账户或密钥；自动优化开启时，研究按已保存预算单独计费。</p>';
  const job=s.job?`<p>历史任务：${escapeText(s.job.kind==='backtest'?'回测':'数据校验')} · ${escapeText(s.job.state)}${s.job.error?' · '+escapeText(s.job.error):''}</p>`:'';
  const summary=s.evaluations.length?'<div class="table-wrap"><table><thead><tr><th>历史检验窗口</th><th>初始本金</th><th>期末资金</th><th>净收益 USDT</th><th>回撤</th><th>交易数</th></tr></thead><tbody>'+s.evaluations.map(r=>`<tr><td>${splitNames[r.window]}</td><td>${number(r.starting_balance)}</td><td>${number(r.final_balance)}</td><td class="${r.profit_total_abs>=0?'positive':'negative'}">${number(r.profit_total_abs)}</td><td>${number(r.max_drawdown_account*100)}%</td><td>${r.total_trades}</td></tr>`).join('')+'</tbody></table></div><p class="muted">历史结果不是实时模拟收益；每侧成本合计 0.1%，包含实际历史资金费率。当前交易规则未在线验证；这是待研究的规则基线，不代表已验证盈利，也没有使用当前 AI 报告预测历史。</p>':'<p>尚无历史回测结果。</p>';
  $('paper-results').innerHTML=checks+job+summary;
  const trades=s.job?.result?.trades;
  const detail=trades?.length?'<details><summary>本次历史回测成交明细（最近 50 笔）</summary><div class="table-wrap"><table><tr><th>方向</th><th>开仓时间 UTC</th><th>平仓时间 UTC</th><th>杠杆</th><th>净盈亏</th><th>资金费率盈亏</th><th>退出原因</th></tr>'+trades.slice(-50).map(t=>`<tr><td>${t.is_short?'空':'多'}</td><td>${escapeText(t.open_date)}</td><td>${escapeText(t.close_date)}</td><td>${t.leverage}</td><td>${number(t.profit_abs)}</td><td>${number(t.funding_fees)}</td><td>${escapeText(t.exit_reason)}</td></tr>`).join('')+'</table></div></details>':'';
  $('paper-trades').innerHTML=detail;
}
async function pollPaper(){try{await pollPaperOnce();}catch(e){if(unlocked)$('paper-message').textContent=e.message;}finally{setTimeout(pollPaper,3000);}}
window.addEventListener('lab-status',()=>{
  if(!unlocked&&paperLoaded){paperLoaded=false;paperDraft=false;paperSignature='';paperMonitor=null;paperMonitorAt=0;['paper-positions','paper-closed-trades','paper-order-records','paper-ledger-summary'].forEach(id=>$(id).innerHTML='');$('paper-live-state').textContent='请解锁查看实时模拟';$('paper-live-explanation').textContent='';$('paper-sync-time').textContent='';$('paper-floating-note').textContent='';$('paper-ledger-countdown').textContent='等待解锁';$('paper-results').innerHTML='';$('paper-trades').innerHTML='';$('paper-state').textContent='等待解锁';}
});
pollPaper();
