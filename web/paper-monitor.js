let paperMonitor=null,paperMonitorAt=0;
const paperOrderStates={open:'待成交',closed:'已完成',canceled:'已取消',cancelled:'已取消',expired:'已过期',rejected:'已拒绝'};
const paperExitReasons={roi:'止盈',stop_loss:'止损',stoploss_on_exchange:'止损',exit_signal:'策略平仓',force_exit:'强制退出',trailing_stop_loss:'移动止损'};
const quantity=v=>v==null?'—':Number(v).toLocaleString('en-US',{maximumFractionDigits:8});
function ledgerDate(v){if(!v)return '—';const raw=String(v).replace(' ','T');const ms=Date.parse(raw+(/Z$|[+-]\d\d:\d\d$/.test(raw)?'':'Z'));return Number.isFinite(ms)?date(ms/1000):escapeText(v);}
function paperTable(head,rows,empty){return rows.length?`<div class="table-scroll"><table><thead><tr>${head.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`:`<p class="muted">${empty}</p>`;}
function renderPaperMonitor(s){
  paperMonitor=s;paperMonitorAt=performance.now();paintPaperMonitor();
}
function paintPaperMonitor(){
  const s=paperMonitor;if(!s)return;const m=s.monitor;if(!m)return;
  const healthy=m.enabled&&m.engine_healthy&&m.state==='running';
  $('paper-live-state').textContent=healthy?'● 实时模拟正在运行':m.enabled?'● 模拟已启用，正在连接或恢复':'○ 实时模拟未运行';
  $('paper-live-state').className=healthy?'positive':'negative';
  const positions=m.positions.filter(t=>t.entry_filled),pending=m.positions.length-positions.length;
  $('paper-live-explanation').textContent=m.ledger_error||(!m.enabled?'模拟已停止，以下保留已有账本记录。':!healthy?'引擎尚未就绪或心跳过期，请查看连接检查；不能视为正常交易中。':m.total_orders===0?'引擎已运行，尚无订单。策略使用 1 小时已收盘 K 线，等待入场信号与风控放行；启动不等于立即下单。':positions.length?`当前持有 ${positions.filter(t=>!t.is_short).length} 个多仓、${positions.filter(t=>t.is_short).length} 个空仓。`:'当前空仓，正在等待下一次入场。');
  $('paper-ledger-summary').innerHTML=`<article><span>已成交订单 / 全部订单</span><strong>${m.filled_orders??'—'} / ${m.total_orders??'—'}</strong></article><article><span>当前持仓 / 待开仓成交</span><strong>${m.ledger_error?'— / —':positions.length+' / '+pending}</strong></article><article><span>已实现净盈亏 · USDT</span><strong class="${m.realized_pnl>=0?'positive':'negative'}">${number(m.realized_pnl)}</strong></article><article><span>浮动盈亏估算 · USDT</span><strong class="${m.unrealized_pnl>=0?'positive':'negative'}">${number(m.unrealized_pnl)}</strong></article>`;
  $('paper-sync-time').textContent=`账本同步：${date(m.received_at)} · 引擎心跳：${m.engine?date(m.engine.heartbeat):'尚未取得'} · ${s.venue.toUpperCase()} · 固定 1 倍 · 虚拟本金 ${number(s.capital)} USDT`;
  $('paper-floating-note').textContent=m.mark_price?`浮盈亏按 ${s.venue.toUpperCase()} 标记价格 ${number(m.mark_price)} 估算，含已记录资金费及双侧手续费；不是最终成交盈亏。`:'标记价格未就绪或已过期，有持仓时不显示浮盈亏估算。';
  const filter=$('paper-record-filter').value,selected=t=>filter==='all'||Boolean(t.is_short)===(filter==='short');
  $('paper-positions').innerHTML=paperTable(['编号 / 方向','状态','开仓时间（本地）','开仓价','数量（BTC）','保证金 USDT','浮动盈亏估算','策略版本'],m.positions.filter(selected).map(t=>`<tr><td>#${t.id} <span class="${t.is_short?'negative':'positive'}">${t.is_short?'做空':'做多'}</span></td><td>${t.entry_filled?'持仓中':'等待开仓成交'}</td><td>${ledgerDate(t.open_date)}</td><td>${number(t.open_rate)}</td><td>${quantity(t.amount)}</td><td>${number(t.stake_amount)}</td><td class="${t.unrealized_pnl>=0?'positive':'negative'}">${number(t.unrealized_pnl)}</td><td>${escapeText(t.enter_tag)}</td></tr>`),m.ledger_error?'账本读取失败。':filter==='all'?'当前没有多仓或空仓。':'当前没有该方向持仓。');
  $('paper-closed-trades').innerHTML=paperTable(['编号 / 方向','开仓时间（本地）','平仓时间（本地）','开仓价 → 平仓价','净盈亏 USDT','资金费盈亏','平仓原因'],m.closed_trades.filter(selected).map(t=>`<tr><td>#${t.id} <span class="${t.is_short?'negative':'positive'}">${t.is_short?'做空':'做多'}</span></td><td>${ledgerDate(t.open_date)}</td><td>${ledgerDate(t.close_date)}</td><td>${number(t.open_rate)} → ${number(t.close_rate)}</td><td class="${t.close_profit_abs>=0?'positive':'negative'}">${number(t.close_profit_abs)}</td><td>${number(t.funding_fees)}</td><td>${escapeText(paperExitReasons[t.exit_reason]||t.exit_reason)}</td></tr>`),m.ledger_error?'账本读取失败。':'尚无已平仓交易；有真实模拟平仓后会自动显示。');
  $('paper-order-records').innerHTML=paperTable(['订单 / 交易编号','操作','状态','委托时间（本地）','委托价 / 成交均价','委托量 / 已成交（BTC）'],m.recent_orders.filter(o=>filter==='all'||(filter==='short'?['开空','平空']:['开多','平多']).includes(o.action)).map(o=>`<tr><td>#${o.id} / #${o.ft_trade_id}</td><td class="${o.action.includes('空')?'negative':'positive'}">${o.action}</td><td>${escapeText(paperOrderStates[o.status]||o.status)}${o.filled>0&&o.remaining>0?' · 部分成交':''}</td><td>${ledgerDate(o.order_date)}</td><td>${number(o.price)} / ${number(o.average)}</td><td>${quantity(o.amount)} / ${quantity(o.filled)}</td></tr>`),m.ledger_error?'账本读取失败。':'尚无开多、开空或平仓订单。这里仅显示实时模拟账本，不显示历史回测。');
}
$('paper-record-filter').onchange=paintPaperMonitor;
$('paper-refresh-ledger').onclick=e=>operation(e.currentTarget,async()=>{await pollPaperOnce();});
setInterval(()=>{if(!paperMonitorAt||!unlocked)return;const elapsed=(performance.now()-paperMonitorAt)/1000;$('paper-ledger-countdown').textContent=elapsed>10?'账本同步已延迟，请检查服务':elapsed>=3?'正在同步…':`下次账本刷新 ${Math.ceil(3-elapsed)} 秒`;if(elapsed>10){$('paper-live-state').textContent='● 账本同步中断，运行状态待确认';$('paper-live-state').className='negative';}},250);
