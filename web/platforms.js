window.addEventListener('lab-status',()=>{
  const p=lastStatus.platforms;if(!p)return;
  const f=p.freqtrade,t=p.tradingagents;
  $('freqtrade-deployment').textContent=`${f.installed?'已安装':'未安装'} · ${f.version||'—'} · ${f.online?'服务在线':'服务未就绪'}`;
  $('tradingagents-deployment').textContent=`${t.installed?'已安装':'未安装'} · ${t.version||'—'} · ${t.online?'独立服务在线':'独立服务未就绪'}`;
  $('freqtrade-deployment-note').textContent=f.note;
  $('tradingagents-deployment-note').textContent=t.note;
  $('graph-deployment').textContent=t.graph_compiled?'真实 Agent 工作流离线编译通过 · 请求记录见 AI 费用':'工作流部署检查未通过';
  $('platform-next-steps').textContent='接下来：'+p.next_steps.join(' → ');
});
