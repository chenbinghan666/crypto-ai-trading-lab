let fastWasUnlocked=false;
const fastStates={running:'两组实时实验运行中',training:'正在训练 15m FreqAI 模型',stopped:'实验已停止',failed:'训练失败 / 等待重试',reconnecting:'引擎恢复中'};
const fastReasons={allowed:'风控通过',daily_new_risk_limit:'当日新增风险达到上限',daily_loss_stop:'当日亏损达到上限',drawdown_stop:'回撤达到上限',loss_streak_cooldown:'连亏冷却中',one_position_limit:'已有持仓',position_risk_limit:'仓位风险超限'};
$('fast-start').onclick=e=>operation(e.currentTarget,async()=>{const r=await accountRequest('/fast-experiment-action',{enabled:true});$('fast-message').textContent=r.message;});
$('fast-stop').onclick=e=>operation(e.currentTarget,async()=>{const r=await accountRequest('/fast-experiment-action',{enabled:false});$('fast-message').textContent=r.message;});
function openFastPanel(){document.querySelector('[data-pane="module-ops"]').click();requestAnimationFrame(()=>$('fast-panel').scrollIntoView({behavior:'smooth'}));}
document.querySelectorAll('[data-open-fast]').forEach(a=>a.addEventListener('click',openFastPanel));
window.addEventListener('hashchange',()=>{if(location.hash==='#fast-panel')openFastPanel();});
if(location.hash==='#fast-panel')openFastPanel();
async function pollFast(){try{
  if(unlocked){fastWasUnlocked=true;const s=await accountRequest('/fast-experiment');if(!unlocked)return;
    $('fast-state').textContent=fastStates[s.state]||s.state;$('fast-message').textContent=s.message;
    $('fast-model').textContent=s.model?`15m CPU LightGBM · 预测未来 ${s.model.horizon_minutes} 分钟 · MAE ${(s.model.mae*100).toFixed(4)}% / 零预测基线 ${(s.model.zero_mae*100).toFixed(4)}% · 训练 ${s.model.train_rows} / 测试 ${s.model.test_rows} · 固定模型 · 未通过盈利验收`:'实验模型尚未准备好。';
    $('fast-comparison').innerHTML=['rule','ai'].map(arm=>{const a=s.arms[arm],g=a.signal;
      return `<article><h3>${arm==='ai'?'FreqAI 模型组':'规则对照组'}</h3><span class="badge ${a.online&&s.enabled?'':'warning'}">${s.enabled?(a.online?'引擎在线':'等待引擎'):'已停止'}</span><p>本金 1000 USDT · 15m · 1 倍 · 独立账本</p><p>已平仓 ${a.closed_count??'—'} 笔 · 持仓 / 开仓中 ${a.open_count??'—'} 个 · 订单 ${a.orders.length} 条（最近 100 条）</p><p>已实现净盈亏 <strong>${number(a.realized_pnl)}</strong> USDT<br>浮动盈亏估算 ${number(a.floating_estimate)} USDT<br>合计估算 <strong>${number(a.total_pnl_estimate)}</strong> USDT</p><p>${g?`最近信号 ${g.direction==='long'?'做多':g.direction==='short'?'做空':'观望'} · ${date(g.at)}<br>${escapeText(fastReasons[g.reason]||g.reason)}${g.prediction==null?'':`<br>模型预测 ${(g.prediction*100).toFixed(3)}% · 门槛 ±0.30%`}`:'等待第一根有效实验 K 线'}${a.error?'<br>'+escapeText(a.error):''}</p></article>`;}).join('');
    $('fast-trades').innerHTML=['rule','ai'].map(arm=>{const a=s.arms[arm];return `<h3>${arm==='ai'?'AI':'规则'}组持仓与交易记录</h3>`+paperTable(['编号 / 方向','状态','开仓时间','平仓时间','开仓价 → 平仓价','净盈亏 / 浮盈估算 USDT'],a.trades.map(t=>`<tr><td>#${t.id} ${t.is_short?'做空':'做多'}</td><td>${t.is_open?(t.entry_filled?'持仓中':'待开仓成交'):'已平仓'}</td><td>${ledgerDate(t.open_date)}</td><td>${ledgerDate(t.close_date)}</td><td>${number(t.open_rate)} → ${number(t.close_rate)}</td><td>${number(t.is_open?t.floating_estimate:t.close_profit_abs)}</td></tr>`),'尚无交易。只在实验开始后的已收盘 K 线上评估，不强制产生订单。')+`<details><summary>${arm==='ai'?'AI':'规则'}组订单（最近 100 条）</summary>`+paperTable(['订单编号','买卖方向','状态','委托量 / 已成交 BTC','时间'],a.orders.map(o=>`<tr><td>#${o.id} / 交易 #${o.ft_trade_id}</td><td>${o.side==='buy'?'买入':'卖出'}</td><td>${escapeText(paperOrderStates[o.status]||o.status)}</td><td>${quantity(o.amount)} / ${quantity(o.filled)}</td><td>${ledgerDate(o.order_date)}</td></tr>`),'尚无订单。')+'</details>';}).join('');
  }else if(fastWasUnlocked){fastWasUnlocked=false;['fast-comparison','fast-trades','fast-model','fast-message'].forEach(id=>$(id).textContent='');$('fast-state').textContent='请先解锁';}
}catch(e){if(unlocked)$('fast-message').textContent=e.message;}finally{setTimeout(pollFast,3000);}}
pollFast();
setInterval(()=>{const seconds=900-Math.floor(Date.now()/1000)%900;$('fast-next-eval').textContent=`下一根 15m 收盘：约 ${Math.floor(seconds/60)} 分 ${seconds%60} 秒后；行情到达后评估，不保证成交`;},1000);
