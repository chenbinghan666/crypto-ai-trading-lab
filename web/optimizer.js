const optimizeStates={running:'自动优化中',accepted:'候选通过，自动切换或等待空仓',rejected:'候选未通过，原版保留',failed:'本轮失败，原版保留',waiting_data:'等待全新最终检验数据',waiting_forward:'候选已生成，自动等待未来验证与最终检验数据',interrupted:'本轮中断',cancelled:'已停止'};
let optimizationSignature='';
function openOptimizerPanel(){document.querySelector('[data-pane="module-ops"]').click();requestAnimationFrame(()=>$('optimizer-panel').scrollIntoView({behavior:'smooth'}));}
document.querySelectorAll('[data-open-optimizer]').forEach(link=>link.addEventListener('click',openOptimizerPanel));
window.addEventListener('hashchange',()=>{if(location.hash==='#optimizer-panel')openOptimizerPanel();});
if(location.hash==='#optimizer-panel')openOptimizerPanel();
$('optimizer-enable').onclick=e=>operation(e.currentTarget,async()=>{const r=await accountRequest('/optimizer-action',{enabled:true});$('optimizer-message').textContent=r.message;optimizationSignature='';});
$('optimizer-disable').onclick=e=>operation(e.currentTarget,async()=>{const r=await accountRequest('/optimizer-action',{enabled:false});$('optimizer-message').textContent=r.message;optimizationSignature='';});
async function pollOptimizer(){try{
  if(unlocked){const s=await accountRequest('/optimizer');if(!unlocked)return;
    const signature=JSON.stringify(s);if(signature!==optimizationSignature){optimizationSignature=signature;
      $('optimizer-state').textContent=s.enabled?'自动优化已开启':'自动优化已暂停';
      const a=s.active_version,p=a.params,r=s.run;
      $('optimizer-message').textContent=s.message;
      $('optimizer-details').innerHTML=`<p>当前模拟版本 ${escapeText(a.id)} · 均线 ${p.fast}/${p.slow} · FreqAI 过滤 ${p.model_filter?'启用':'关闭'} · 阈值 ${(p.prediction_threshold*100).toFixed(2)}%</p><p>下一次后台检查：${date(s.next_due)} · 独立服务 ${s.service_ready?'在线':'未就绪'}${s.pending?' · 候选等待空仓切换':''}</p>`+
      (r?`<p><strong>${optimizeStates[r.state]||escapeText(r.state)}</strong> · ${escapeText(r.stage)}${r.error?' · '+escapeText(r.error):''}</p>`:'')+
      (r?.result?.wait_until?`<p>未来数据收集至：${date(r.result.wait_until)}；此期间原策略继续运行，不重复调用 AI。</p>`:'')+
      (r?.result?.candidate?`<p class="${r.result.passed?'positive':'negative'}">${r.result.passed?'含成本检验通过':'含成本检验未通过'}：${escapeText(r.result.reasons.join('；').replaceAll('validation','验证窗口').replaceAll('holdout','最终检验窗口'))}</p><div class="table-scroll"><table><tr><th>窗口</th><th>原版净收益 USDT</th><th>候选净收益 USDT</th><th>候选交易数</th><th>候选回撤</th></tr>${['validation','holdout'].map(w=>`<tr><td>${w==='validation'?'验证':'最终检验'}</td><td>${number(r.result.incumbent[w].profit)}</td><td>${number(r.result.candidate[w].profit)}</td><td>${r.result.candidate[w].trades}</td><td>${number(r.result.candidate[w].drawdown*100)}%</td></tr>`).join('')}</table></div>`:'')+
      '<p class="muted">自动优化不会自动启动尚未启用的模拟账户。新版本通过后自动应用，已有持仓保持原退出逻辑；模拟表现恶化时自动回退。</p>';
    }
  }else{optimizationSignature='';$('optimizer-details').innerHTML='';}
}catch(e){if(unlocked)$('optimizer-message').textContent=e.message;}finally{setTimeout(pollOptimizer,3000);}}
pollOptimizer();
