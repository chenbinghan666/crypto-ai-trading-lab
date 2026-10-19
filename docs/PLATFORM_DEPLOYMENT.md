# Freqtrade / TradingAgents 平台部署验收

检查日期：2026-10-16。用户要求先部署和接通平台，再开展策略与模拟。本轮未启动模拟、回测、真实下单或付费 AI 研究。

后续更新：手动 AI 研究执行、DeepSeek 密钥验证、公开行情适配及费用闸门已接通，详见 [AI 研究使用与验收](AI_RESEARCH.md)。下文保留首次平台部署验收记录；其中研究执行“尚未完成”属于当时状态。当前仍未发起真实付费推理，模型训练、交易信号桥接及模拟执行仍待完成。

## 当前真实状态

| 组件 | 部署情况 | 已验证 | 尚未完成 |
|---|---|---|---|
| Freqtrade | 2026.9，WSL 独立主环境 | 官方 Webserver / FreqUI 服务在线 | 合约策略、风控、模拟执行及订单恢复 |
| FreqUI | 3.1.3，8081 端口 | 本地管理页面运行，交易 API 拦截有效 | 尚未连接交易 Worker |
| TradingAgents | 0.6.0，独立 Python 环境 | 官方代码可导入，真实 Agent 工作流编译，独立健康服务和异常重启 | 付费研究执行、费用闸门、合约数据和信号桥接 |
| FreqAI | 尚未部署训练扩展 | 无训练任务 | 后续 CPU 训练与模型评估 |

TradingAgents 固定官方提交 `1394a3f72aa4393e1a98f51b382434c4b4c2d972`（上游提交日期 2026-10-03），依赖固定于 `requirements-tradingagents.lock.txt`。它使用独立环境，未改变 Freqtrade 的依赖。

官方来源： https://github.com/TauricResearch/TradingAgents 。当前上游原生提供 `BTC-USD` / `ETH-USD` 与 `asset_type="crypto"` 路径；这不等于已经接通 Binance USDT 永续合约、资金费率或交易执行。后续必须明确匹配研究数据与交易市场。

## 独立运行方式

Windows 继续使用根目录「启动系统.cmd」「停止系统.cmd」「查看状态.cmd」。主 supervisor 现在管理行情、管理网页、FreqUI、TradingAgents 部署服务四个子进程；TradingAgents 进程使用 WSL HOME 下 `.local/share/crypto-ai-trading-lab/tradingagents-venv/bin/python`。服务运行不依赖 Codex 会话。

本地健康接口： http://127.0.0.1:8082/health 。只提供部署检查与状态，不提供 Agent 执行、交易或密钥读取接口。网页的「平台部署状态」同时展示安装版本、服务是否在线及待完成项目。

重新安装：在 WSL 项目目录运行 `bash scripts/setup-tradingagents.sh`。完整新机器初始化执行 `bash scripts/setup-wsl.sh`，会安装主环境及研究环境。研究环境默认地址可通过 `LAB_RESEARCH_PYTHON` 指定。

Docker Compose 已补充独立 `research` 服务、版本锁、持久状态卷及健康检查。主容器设置 `LAB_EXTERNAL_RESEARCH=1`，避免再启动重复研究进程。本机无 Docker，容器构建及迁移没有实际验证。

## 本轮验收证据

- TradingAgents 工作流真实编译包含 Market Analyst、Bull/Bear Researcher、Trader、Research Manager、三个风险讨论节点及 Portfolio Manager。
- 离线检查使用占位密钥和模型 ID，阻止 socket 对外连接，不调用 `propagate()` 或 LLM。占位模型产生的“未知模型 ID”警告符合预期；检查不代表 DeepSeek 远程密钥、真实模型或研究结果已验证。
- `pip check` 通过，两套 Python 环境保持隔离。
- 40 项本地自动化测试通过。
- `python -m scripts.check_platforms --test-recovery` 验证了组件版本、服务在线、工作流编译、DeepSeek 配置、0 次付费调用、模拟关闭和实盘关闭；终止本项目研究服务后，supervisor 自动启动新进程并恢复健康。
- 验收结果：`reports/evidence/phase3/platform_acceptance.json`。没有实际关闭 Codex 窗口做测试，报告明确记录 `not_observed`。

## 下一步顺序

1. 完成 DeepSeek 密钥验证、调用记账与预算闸门；仍通过网页本机配置，不在聊天中发送密钥。
2. 适配加密资产数据，保留数据截止时间、来源、现货/永续差异和缺失信息。
3. 建立 TradingAgents 的结构化研究信号到 Freqtrade 的受控桥接，不直接执行自然语言建议。
4. 编写候选策略，做成本完整的样本外回测和独立风控验收。
5. 验收后由用户在网页手动启用模拟；合约实时接口可用性仍单独核验。

当前币安合约网络限制仍存在，与软件安装是否成功是两项不同检查。本轮历史数据探测只读取了一份 K 线 ZIP 和一份资金费率 ZIP 的样例内容，没有生成策略绩效、模拟收益或订单。
