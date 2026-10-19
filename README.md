# Crypto AI Trading Lab · 量化研究与模拟工作台

独立运行的加密货币研究和合约模拟系统，提供中文 Web 管理页面，集成 Freqtrade / FreqUI、FreqAI CPU LightGBM 和 TradingAgents / DeepSeek。运行时不依赖 Codex 或聊天会话。

**当前仅支持研究与虚拟交易，真实交易禁止。策略和模型均不代表已验证盈利。**

## 功能

- Binance 公共行情、连接诊断、K 线及刷新倒计时；Gate 永续公开行情用于独立合约模拟。
- 币安 U 本位合约账户只读绑定，查询资产与持仓；API 配置在本机加密保存。
- TradingAgents / DeepSeek 研究任务、API 用量记账、预算预留与费用限制。
- FreqAI CPU 训练、时间隔离评估、模型保存和重载验证。
- 官方 Freqtrade 合约回测与实时 Dry-run：多空持仓、开平仓订单、成交状态及盈亏。
- 自动优化：生成候选、训练、含成本样本外比较，通过后空仓切换模拟版本，表现恶化时回退。
- 15m AI 对照实验：规则组与 FreqAI 模型组使用独立虚拟账本，比较信号、交易记录和盈亏。
- 独立进程守护、断线重连、状态恢复、订单去重、Windows 一键启停和 Docker Compose 配置。

## Windows 启动

环境准备与依赖安装见 [Windows 安装](docs/INSTALL_WINDOWS.md) 和 [部署说明](docs/DEPLOYMENT.md)。需要 WSL / Ubuntu 和兼容的 Python 环境；Windows 脚本会发现项目路径。

1. 克隆仓库，按安装文档准备 WSL 及依赖。
2. 双击 `启动系统.cmd`，访问 <http://127.0.0.1:8080>。
3. 双击 `FreqUI登录信息.cmd` 查看本机管理密码，在网页解锁面板。
4. 在网页配置所需 API、检查行情和服务，再手动启用研究、训练或模拟。
5. 双击 `停止系统.cmd` 停止服务，`查看状态.cmd` 查看运行状态。

关闭浏览器或开发工具不影响后台服务；电脑关机或休眠会中断本地运行。新部署默认不启动模拟和自动优化。仓库不包含开发者的配置、密钥、模型和运行数据，克隆后需自行初始化。

官方研究 FreqUI：<http://127.0.0.1:8081>。原 1h 模拟启动后的只读 FreqUI：<http://127.0.0.1:8083>。

## Docker Compose

```sh
docker compose up -d --build
docker compose down
```

默认端口只绑定本机。首次部署需自行配置凭证与模块开关。已提供主程序及研究服务镜像配置；Docker 实际构建和 Linux VPS 部署仍需在目标环境验收。

## 模拟与 AI 的边界

模拟使用虚拟资金，无需交易所交易权限。当前固定 1 倍杠杆，保留独立仓位、日亏损、回撤和连亏冷却限制。策略按已收盘 K 线评估，没有信号或风控未放行时可以零交易。

15m 对照实验中的 AI 指本地 FreqAI LightGBM 预测过滤；TradingAgents / DeepSeek 是单独的研究与优化流程。实验模型未经盈利验收，实验结果不会直接替换原账户策略。自动优化只调整受限参数和模型，不执行 AI 生成的任意代码。

手续费、滑点费用折算、资金费、训练数据隔离与最终检验规则见相关文档。费用折算不能完全代表真实成交冲击，短期模拟收益不能证明策略有效。

## 凭证与运行数据

API 密钥只在本机网页填写，不要提交到 GitHub、Issue 或聊天。使用只读币安账户权限；系统不会用该账户执行交易。DeepSeek 调用受预算及价格核验有效期限制。

本机环境文件、密钥、数据库、模型、日志、运行报告和截图均由 `.gitignore` 排除。公开仓库只包含源代码、配置模板、测试和文档。运行程序后生成的报告留在本机。

## 文档

- [部署与故障恢复](docs/DEPLOYMENT.md) · [恢复指南](docs/RECOVERY.md)
- [网页操作](docs/WEB_CONTROLS.md) · [账户只读绑定](docs/BINANCE_ACCOUNT.md)
- [合约模拟](docs/PAPER_TRADING.md) · [15m AI 对照实验](docs/FAST_AI_EXPERIMENT.md)
- [FreqAI CPU](docs/FREQAI_CPU.md) · [AI 研究](docs/AI_RESEARCH.md)
- [自动优化](docs/AUTOMATIC_OPTIMIZATION.md) · [风险政策](docs/RISK_POLICY.md)
- [独立运行验收](docs/INDEPENDENCE_ACCEPTANCE.md)

## 开发验证

```powershell
.\scripts\lab.ps1 test
```

需先安装文档指定的运行依赖。网络验收、独立后台恢复和实验服务验收脚本位于 `scripts/`；部分脚本要求本地服务已经启动。验收输出不随仓库发布。

项目使用的上游包括 [Freqtrade](https://github.com/freqtrade/freqtrade) 和 [TradingAgents](https://github.com/TauricResearch/TradingAgents)。依赖版本固定在 requirements 锁定文件中，上游软件遵循各自许可证。