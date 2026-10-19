# 独立部署说明

最新补充：已增加独立 `paper_service`，负责网页提交的历史回测和官方 Freqtrade 实时模拟进程。后台现有五个子服务（行情、管理网页、研究 FreqUI、AI 研究、模拟管理），加 supervisor 共六个常驻服务；模拟 Worker 仅在用户手动启用后创建。使用方法和当前验收边界见 [PAPER_TRADING.md](PAPER_TRADING.md)。模拟 FreqUI 使用本机 8083 端口。以下首次部署记录中“模拟尚未接通”属于历史状态。

2026-10-16 用户最新要求先完成 Freqtrade / TradingAgents 部署与集成，再做策略及模拟。本版本启动 supervisor、market、dashboard、FreqUI webserver、TradingAgents 研究服务。默认不自动发起 AI 请求；网页手动研究见 [AI_RESEARCH.md](AI_RESEARCH.md)。训练及交易执行尚未启用，也没有 Codex SDK/会话依赖。

## 已配置的 Windows 电脑

双击根目录 `启动系统.cmd`。脚本启动独立隐藏 PowerShell watchdog，通过 WSL 执行 Python supervisor；后者维护四个子服务。关闭 Codex、页面和启动窗口都不会停止服务。当前未添加开机自启/计划任务，Windows 重启后需再次双击启动。

管理首页：http://127.0.0.1:8080 。官方 FreqUI：http://127.0.0.1:8081 。均仅监听 loopback，局域网不能直接连接。

FreqUI 登录：双击 `FreqUI登录信息.cmd`；点击页面 Login，URL 填 `http://127.0.0.1:8081`，使用脚本显示的本地用户名与密码。不要填写币安密码或 API Key。凭证在 `data/system/frequi-auth.json`，被 Git/Docker 构建上下文忽略；不要上传或发到聊天，也不要共享给其他 Windows 用户。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/system.ps1 start
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/system.ps1 status
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/system.ps1 stop
```

ExecutionPolicy 参数只作用于该进程，不改变系统全局策略。无需管理员权限。已安装：WSL Ubuntu 24.04 / Python 3.12 / Freqtrade 2026.9 / FreqUI 3.1.3 / TradingAgents 0.6.0（独立环境）。

## 另一台 WSL 机器

先安装 WSL Ubuntu 和 Python >=3.11，再进入项目目录运行：

```bash
bash scripts/setup-wsl.sh
```

脚本在 WSL HOME 的 `.local/share/crypto-ai-trading-lab/venv` 创建主环境，安装 `requirements.lock.txt` 和 FreqUI 3.1.3；随后在 `tradingagents-venv` 独立环境安装 `requirements-tradingagents.lock.txt`。首次下载约数百 MB，不包含 CUDA、本地 LLM 权重或 FreqAI。sdnotify 无 wheel，构建其小型纯 Python 包。TradingAgents 固定官方提交，版本锁尚未包含全部依赖哈希。

Windows 脚本自动读取 WSL HOME，不要求相同用户名或项目路径。默认发行版名称 Ubuntu；如不同，修改脚本中的 `-d Ubuntu`。

## Docker / Linux VPS

当前 Compose 包含主服务 `lab`（2 CPU / 2 GiB）和独立 `research` 服务（1 CPU / 1 GiB），隔离两套依赖并共享状态/日志卷。研究服务运行健康检查，并执行用户从网页手动提交的 AI 研究任务。限额不能作为未来训练资源承诺。Docker 构建仍待实际验收。

```bash
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs --tail=100
docker compose exec lab python -m labapp.control credentials
docker compose down
```

基础镜像固定 digest，依赖和 FreqUI 固定版本；非 root、去除 capabilities、命名持久卷。`.dockerignore` 排除 data/logs/.env。`down` 保留数据，勿用 `down -v`。

VPS 仍仅绑定 loopback，远程查看使用：

```bash
ssh -L 8080:127.0.0.1:8080 -L 8081:127.0.0.1:8081 your-user@your-vps
```

不要直接暴露到公网。本机无 Docker daemon，未实际构建容器或购买 VPS。Docker healthcheck 本身不重启 unhealthy 容器；内部 supervisor 恢复子服务，restart policy 处理容器进程退出。

## 数据、网络和费用

公共行情优先连接 U 本位合约 `fapi.binance.com`；不可达时，使用无需 Key 的 `data-api.binance.vision` 并明确标注「现货参考」。当前环境合约域名 DNS 失败。只读账户绑定已提供，真实账户连通性待验；见 [合约账户说明](BINANCE_ACCOUNT.md)。

SQLite：`data/system/system.sqlite`，日志：`logs/`。已收盘 1m K 线保留 7 天（切换行情来源时清除旧来源数据），事件保留约 2000 条；公开行情目标采集间隔 3 秒，另加请求耗时，故障退避最多 60 秒，超过 30 秒未更新显示过期。1m 仅用于展示。合约账户独立每 30 秒只读查询，未绑定时不发送私有请求。

历史归档仅用于个人非生产研究，条款快照在 reports/evidence/phase2。DeepSeek 未启用，费用 0；页面费用数据不代表完整计费账本已经实现。
