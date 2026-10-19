let trainingSignature='',trainingWasUnlocked=false;
const trainingStates={queued:'排队中',running:'训练中',completed:'已完成',failed:'失败',cancelled:'已停止',interrupted:'已中断'};
$('training-start').onclick=e=>operation(e.currentTarget,async()=>{const r=await accountRequest('/training-action',{action:'start',source:$('training-source').value});$('training-message').textContent=r.message;await pollTrainingOnce();});
$('training-stop').onclick=e=>operation(e.currentTarget,async()=>{const r=await accountRequest('/training-action',{action:'stop'});$('training-message').textContent=r.message;await pollTrainingOnce();});
async function pollTrainingOnce(){
  if(!unlocked)return;const s=await accountRequest('/training');if(!unlocked)return;trainingWasUnlocked=true;
  $('training-service').textContent=s.readiness.ready?'CPU 训练服务就绪':s.readiness.blockers.join('；');
  $('training-versions').textContent=Object.entries(s.versions).map(([k,v])=>`${k} ${v||'未安装'}`).join(' · ');
  const j=s.job;const signature=JSON.stringify(j);if(signature===trainingSignature)return;trainingSignature=signature;
  if(!j){$('training-results').textContent='尚无训练任务。';return;}
  const deployment=j.result?.deployment==='paper_active'?'已通过自动优化检验，应用于模拟策略':j.result?.deployment==='rolled_back'?'模拟表现触发回退，已退出使用':'候选模型已保存，尚未用于交易';
  $('training-message').textContent=j.state==='completed'?'训练已完成；'+deployment:j.error||j.stage;
  const r=j.result;
  $('training-results').innerHTML=`<p><strong>${trainingStates[j.state]||escapeText(j.state)}</strong> · ${escapeText(j.stage)} · ${escapeText(j.source)} · ${date(j.updated)}</p>${j.error?`<p class="negative">${escapeText(j.error)}</p>`:''}`+(r?`
    <p>模型 ${escapeText(r.model)} · ${escapeText(r.source.venue.toUpperCase())} BTC 永续 · 1h · 预测未来 ${r.horizon_candles} 小时收益</p>
    <div class="table-scroll"><table><tr><th>训练样本</th><th>测试样本</th><th>特征数</th><th>预测 MAE</th><th>预测恒为 0 的 MAE</th><th>方向正确率</th></tr><tr><td>${r.train_rows}</td><td>${r.test_rows}</td><td>${r.features.length}</td><td>${(r.mae*100).toFixed(4)}%</td><td>${(r.zero_prediction_mae*100).toFixed(4)}%</td><td>${(r.direction_accuracy*100).toFixed(2)}%</td></tr></table></div>
    <p class="${r.beats_zero_baseline?'positive':'negative'}">${r.beats_zero_baseline?'本次预测 MAE 低于零预测基线':'本次预测未优于零预测基线，不能视为有效模型'} · 保存后重载验证：${r.reload_verified?'通过':'未通过'}</p>
    <p class="muted">训练 ${escapeText(r.train_start)} 至 ${escapeText(r.train_end)}<br>测试 ${escapeText(r.test_start)} 至 ${escapeText(r.test_end)}<br>隔离 ${r.purge_candles} 根标签窗口 · ${deployment}。</p><p>${escapeText(r.limitations)}</p>`:'');
}
async function pollTraining(){try{await pollTrainingOnce();}catch(e){if(unlocked)$('training-message').textContent=e.message;}finally{setTimeout(pollTraining,2000);}}
window.addEventListener('lab-status',()=>{if(!unlocked&&trainingWasUnlocked){trainingSignature='';trainingWasUnlocked=false;$('training-results').innerHTML='';$('training-service').textContent='请先解锁管理面板';}});
pollTraining();
