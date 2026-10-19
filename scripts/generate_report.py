"""Generate an honest infrastructure report without starting research or trading."""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from labapp.store import init,snapshot

init()
s=snapshot()
now=datetime.now(ZoneInfo('Asia/Singapore'))
lines=[f'# 系统状态报告 {now:%Y-%m-%d %H:%M:%S %Z}',
       '', '运行模式：基础设施；AI/训练/模拟/实盘均未启用。收益无数据，AI 调用数和费用为零。',
       '', '| 服务 | 状态 | 心跳间隔（秒） |', '|---|---|---|']
for v in s['services']:
    lines.append(f"| {v['name']} | {v['state']} | {v['age_seconds']} |")
if s['market']:
    m=s['market'];lines+=['',f"币安 BTC/USDT 买一 {m['bid']}，卖一 {m['ask']} USDT；数据年龄 {m['age_seconds']} 秒；过期={m['stale']}。"]
lines+=['','本报告不是策略业绩日报。完整研究/成本/订单账本复盘尚未实现。']
path=ROOT/'reports/daily'/f'{now:%Y-%m-%d}-system.md';path.parent.mkdir(parents=True,exist_ok=True)
path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(path)
