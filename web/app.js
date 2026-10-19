const $=id=>document.getElementById(id);
const number=x=>x===null||x===undefined?'—':Number(x).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const date=x=>new Date(x*1000).toLocaleString('zh-CN',{hour12:false});
const escapeText=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={market:'币安行情采集',dashboard:'中文管理页面',frequi:'官方 FreqUI',supervisor:'独立进程守护',research:'TradingAgents 研究服务',paper:'独立模拟与回测管理',paper_engine:'Freqtrade 模拟引擎',training:'FreqAI CPU 训练服务',optimizer:'自动复盘与策略优化',fast_manager:'15m AI 对照实验管理',fast_ai:'15m AI 模拟引擎',fast_rule:'15m 规则模拟引擎'};
const states={running:'运行正常',starting:'启动中',reconnecting:'重连中',restarting:'重启中',stopped:'已停止',stale:'心跳过期',paused:'采集已暂停'};
let windowSize=15,chartOffset=0,lastStatus=null,lastReceipt=0,lastPrice=null,statusAt=0,unlocked=false,account=null,hiddenMoney=false,accountEpoch=0;

function chart(rows){
  chartOffset=Math.min(chartOffset,Math.max(0,rows.length-windowSize));rows=rows.slice(Math.max(0,rows.length-chartOffset-windowSize),rows.length-chartOffset);if(!rows.length){$('chart').innerHTML='';return;}
  const low=Math.min(...rows.map(r=>r.low)),high=Math.max(...rows.map(r=>r.high));
  const padding=Math.max((high-low)*.12,high*.00001),min=low-padding,max=high+padding;
  const y=v=>215-(v-min)/(max-min)*185,step=730/windowSize,width=Math.max(2,step*.65);
  let svg='';
  for(let i=0;i<5;i++){let value=max-i*(max-min)/4,py=y(value);svg+=`<line x1="10" y1="${py}" x2="750" y2="${py}" stroke="#263446" stroke-dasharray="3 5"/><text x="760" y="${py+4}" fill="#8091a8" font-size="11">${number(value)}</text>`;}
  rows.forEach((r,i)=>{const x=18+step*i+step/2,color=r.close>=r.open?'#52d8b0':'#fb7185';svg+=`<g opacity="${r.unclosed?.65:1}"><line x1="${x}" y1="${y(r.high)}" x2="${x}" y2="${y(r.low)}" stroke="${color}"/><rect x="${x-width/2}" y="${Math.min(y(r.open),y(r.close))}" width="${width}" height="${Math.max(1,Math.abs(y(r.open)-y(r.close)))}" fill="${color}"><title>${new Date(r.open_ms).toLocaleTimeString()} 开 ${r.open} 高 ${r.high} 低 ${r.low} 收 ${r.close}${r.unclosed?'（未收盘）':''}</title></rect></g>`;if(i%Math.max(1,Math.floor(windowSize/5))===0)svg+=`<text x="${x}" y="240" text-anchor="middle" fill="#8091a8" font-size="11">${new Date(r.open_ms).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false})}</text>`;});
  $('chart').innerHTML=svg;
  $('chart-range').textContent=`${chartOffset?'历史窗口':'最新窗口'} · 可见 ${rows.length} 根 · 区间振幅 ${((high-low)/low*100).toFixed(3)}% · 纵轴自动缩放`;
}
function renderChart(){if(!lastStatus)return;document.querySelectorAll("[data-window]").forEach(b=>b.classList.toggle("active",Number(b.dataset.window)===windowSize));let rows=[...lastStatus.candles];const current=lastStatus.market?.current_candle;if(current){rows=rows.filter(r=>r.open_ms!==current.open_ms);rows.push(current);}chart(rows);}
$('windows').addEventListener('click',e=>{if(!e.target.dataset.window)return;chartOffset=0;windowSize=Number(e.target.dataset.window);document.querySelectorAll('[data-window]').forEach(b=>b.classList.toggle('active',Number(b.dataset.window)===windowSize));renderChart();});

async function update(){
  try{
    const response=await fetch('/api/status',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!response.ok)throw Error();
    const s=await response.json();lastStatus=s;statusAt=performance.now();
    $('connection').textContent='管理服务在线';$('connection').className='badge';$('clock').textContent=date(s.now);
    $('trade-state').textContent=({stopped:'未启动',running:'实时模拟中',starting:'启动中',stopping:'停止中',reconnecting:'连接恢复中',blocked:'被拦截'})[s.paper_state]||s.paper_state;
    $('trade-mode').textContent=(s.paper_enabled?'模拟已启用':'模拟关闭')+' · 实盘禁止';
    const engine=s.services.find(v=>v.name==='paper_engine');
    const engineReady=s.paper_enabled&&s.paper_state==='running'&&engine?.state==='running'&&engine.age_seconds<30;
    $('header-trade-state').textContent=s.paper_enabled?(engineReady?'实时模拟运行中':'模拟已启用 / 等待引擎'):'实时模拟未运行';
    $('module-execution-state').textContent=s.paper_enabled?(engineReady?'模拟运行 · 实盘禁止':'模拟恢复中 · 实盘禁止'):'模拟未运行 · 实盘禁止';
    if(s.paper_enabled&&s.paper_state==='running'&&!engineReady)$('trade-state').textContent='等待引擎心跳';
    $('sim-pnl').textContent=number(s.performance.pnl);$('sim-pnl-note').textContent=s.performance.note;
    $('price-symbol').textContent=s.settings.symbol;$('chart-title').textContent=s.settings.symbol+' 行情';
    const m=s.market;if(m){
      if(m.received_at!==lastReceipt){$('price').className='value '+(lastPrice===null||m.mid===lastPrice?'':m.mid>lastPrice?'tick-up':'tick-down');lastPrice=m.mid;lastReceipt=m.received_at;}
      $('price').textContent=number(m.mid);$('bid').textContent=number(m.bid);$('ask').textContent=number(m.ask);$('spread').textContent=m.spread_bps.toFixed(3)+' bps';
      $('market-health').textContent=s.settings.paused?'用户已暂停采集':m.stale?'网络未更新 · 行情过期':m.market_type==='usd_m_futures'?'合约行情在线':'现货参考行情';$('market-health').className='badge'+(s.settings.paused||m.stale||m.fallback_reason?' warning':'');
      $('market-kind').textContent=m.market_type==='usd_m_futures'?'BINANCE · U 本位永续':'BINANCE · 现货参考';
      $('source-note').textContent=m.fallback_reason||(m.market_type==='usd_m_futures'?'Binance U 本位合约公共行情 · 目标每 3 秒采集':'Binance 现货参考行情 · 等待合约连接验证');
    }else{['price','bid','ask','spread'].forEach(id=>$(id).textContent='—');$('market-health').textContent='等待所选交易对数据';$('source-note').textContent='尚未取得所选交易对行情';$('chart').innerHTML='';}
    renderChart();
    $('services').innerHTML=s.services.map(v=>`<div class="service"><div><strong>${names[v.name]||escapeText(v.name)}</strong><small>心跳 ${v.age_seconds.toFixed(0)} 秒前</small></div><span class="badge ${v.state==='running'?'':'warning'}">${states[v.state]||escapeText(v.state)}</span></div>`).join('');
    $('event-count').textContent=s.events.length+' 条记录';$('events').innerHTML=s.events.map(e=>`<div class="event"><time>${date(e.at)}</time><span class="${e.level==='warning'?'badge warning':'muted'}">${e.level==='warning'?'告警':'信息'}</span><span class="message">${escapeText(e.message)}</span></div>`).join('')||'<p class="muted">暂无事件</p>';
    window.dispatchEvent(new Event('lab-status'));
  }catch(e){$('connection').textContent='管理服务离线';$('connection').className='badge warning';$('market-health').textContent='无法确认行情新鲜度';$('market-health').className='badge warning';}
  finally{setTimeout(update,1000);}
}
setInterval(()=>{
  const m=lastStatus?.market;if(m){const now=lastStatus.now+(performance.now()-statusAt)/1000,age=Math.max(0,now-m.received_at),remaining=(m.next_poll_at??m.received_at+3)-now;$('quote-note').textContent=`买卖中间价 · ${age.toFixed(1)} 秒前更新`;$('countdown').textContent=lastStatus.settings.paused?'后台采集已暂停':age>(m.stale_after_seconds||30)?'网络未更新 · 行情过期':remaining>0?`下次采集 ${remaining.toFixed(1)} 秒`:'正在采集 / 等待网络';}
  if(account?.updated_at){const age=Math.max(0,Date.now()/1000-account.updated_at),remain=(account.next_poll_at||0)-Date.now()/1000;$('account-timer').textContent=`上次同步 ${date(account.updated_at)} · ${age.toFixed(0)} 秒前 · ${remain>0?'下次同步 '+Math.ceil(remain)+' 秒':'等待同步'}`;}
},100);

async function accountRequest(path, data){
  const response=await fetch('/api/account'+path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),cache:'no-store',signal:AbortSignal.timeout(path==='/paper-action'&&data?.action==='check'?45000:10000)});
  const result=await response.json();if(!response.ok){if(response.status===401)setLocked();const detail=result.detail;throw Error(typeof detail==='object'?[detail.message,...(detail.blockers||[])].join('\n'):detail||'账户请求失败');}return result;
}
function setLocked(){accountEpoch++;unlocked=false;account=null;$('account-locked').hidden=false;$('account-unlocked').hidden=true;$('account-state').textContent='面板已锁定';$('account-state').className='badge neutral';$('api-key').value='';$('api-secret').value='';['wallet','margin','available','unrealized'].forEach(id=>$(id).textContent='—');$('positions').innerHTML='';$('assets').innerHTML='';$('account-timer').textContent='等待解锁';}
const money=v=>hiddenMoney?'••••':number(v);
const precise=v=>hiddenMoney?'••••':v===null||v===undefined?'—':Number(v).toLocaleString('en-US',{maximumFractionDigits:8});
function renderAccount(a){
  account=a;unlocked=true;$('account-locked').hidden=true;$('account-unlocked').hidden=false;
  $('account-state').textContent=({not_configured:'未绑定',connecting:'正在验证',connected:'只读连接正常',error:'连接异常'})[a.state]||'等待同步';
  $('account-state').className='badge'+(a.state==='connected'&&!a.stale?'':' warning');
  if(a.state==='connected'&&a.stale)$('account-state').textContent='账户数据已过期';
  $('account-warning').hidden=!a.error&&!a.stale;$('account-warning').textContent=a.error||(a.updated_at?'当前为上次成功同步的数据，已过期。':'尚未取得账户数据。');
  $('disconnect-account').disabled=!a.configured;
  const t=a.totals||{};for(const [id,key] of Object.entries({wallet:'totalWalletBalance',margin:'totalMarginBalance',available:'availableBalance',unrealized:'totalUnrealizedProfit'}))$(id).textContent=money(t[key]);
  $('position-count').textContent=a.positions?`${a.positions.length} 个`:'';
  $('positions').innerHTML=a.positions?.length?a.positions.map(p=>`<tr><td><strong>${escapeText(p.symbol)}</strong><small>${p.positionSide==='LONG'?'多仓':p.positionSide==='SHORT'?'空仓':Number(p.positionAmt)>0?'单向 · 多仓':'单向 · 空仓'}</small></td><td>${precise(p.positionAmt)}</td><td>${precise(p.entryPrice)}</td><td>${precise(p.markPrice)}</td><td>${Number(p.liquidationPrice)>0?precise(p.liquidationPrice):'—'}</td><td class="${hiddenMoney?'':Number(p.unRealizedProfit)>=0?'positive':'negative'}">${precise(p.unRealizedProfit)}</td><td>${escapeText(p.marginAsset)}</td></tr>`).join(''):`<tr><td colspan="7">${a.updated_at?'上次成功同步时无持仓':'尚未取得持仓数据，不代表空仓'}</td></tr>`;
  $('assets').innerHTML=a.assets?.length?a.assets.map(v=>`<tr><td>${escapeText(v.asset)}</td>${['walletBalance','marginBalance','availableBalance','unrealizedProfit'].map(k=>`<td>${precise(v[k])}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="5">${a.updated_at?'上次成功同步时无非零余额':'尚未取得资产数据'}</td></tr>`;
  if(!a.updated_at)$('account-timer').textContent=a.configured?'正在等待账户同步（每 30 秒查询）':'等待绑定';
}
async function pollAccount(){const epoch=accountEpoch;try{const a=await accountRequest('');if(epoch===accountEpoch)renderAccount(a);}catch(e){if(unlocked&&epoch===accountEpoch){$('account-state').textContent='同步中断';$('account-warning').hidden=false;$('account-warning').textContent='管理服务不可达，所示金额可能已过期。';}}finally{setTimeout(pollAccount,3000);}}
$('unlock-form').addEventListener('submit',async e=>{e.preventDefault();try{await accountRequest('/login',{password:$('admin-password').value});$('admin-password').value='';renderAccount(await accountRequest(''));$('account-message').textContent='面板已解锁；本机查询服务独立运行。';}catch(err){$('account-message').textContent=err.message;}});
$('bind-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{const result=await accountRequest('/connect',{key:$('api-key').value.trim(),secret:$('api-secret').value.trim()});$('api-key').value='';$('api-secret').value='';$('account-message').textContent=result.message;$('bind-details').open=false;renderAccount(await accountRequest(''));}catch(err){$('account-message').textContent=err.message;}finally{button.disabled=false;}});
$('lock-account').onclick=async()=>{try{await accountRequest('/logout',{});setLocked();$('account-message').textContent='已锁定面板，后台只读同步继续。';}catch(e){$('account-message').textContent=e.message;}};
$('disconnect-account').onclick=async()=>{try{await accountRequest('/disconnect',{});renderAccount(await accountRequest(''));$('bind-details').open=true;$('account-message').textContent='已删除本机保存的 API 密钥，清除账户快照并停止同步。';}catch(e){$('account-message').textContent=e.message;}};
$('hide-money').onclick=()=>{hiddenMoney=!hiddenMoney;$('hide-money').textContent=hiddenMoney?'显示金额':'隐藏金额';if(account)renderAccount(account);};
update();pollAccount();
