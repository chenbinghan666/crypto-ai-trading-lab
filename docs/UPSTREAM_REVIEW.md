# 上游版本与兼容性核验

检查日期：2026-10-16。证据为官方 GitHub API、固定 release 源文件与官方文档；原始响应及失败项见 `reports/evidence/index.json`。

| 项目 | 官方 release | 固定提交 | 许可 | Python |
|---|---|---|---|---|
| Freqtrade | 2026.9（2026-09-29 发布） | 1f394eaebc2f46a83d26971388628707802f8602 | GPL-3.0 | >=3.11 |
| TradingAgents | v0.6.0（2026-10-03 发布） | ff0d0b1b4d7240c16f07f363856639d526934e44 | Apache-2.0 | >=3.11 |

来源：[Freqtrade release](https://github.com/freqtrade/freqtrade/releases/tag/2026.9)、[TradingAgents release](https://github.com/TauricResearch/TradingAgents/releases/tag/v0.6.0)。上游许可证原文已保存；本项目未复制上游实现代码。后续修改/分发上游时保留对应许可证与通知。

[FreqAI 官方说明](https://www.freqtrade.io/en/stable/freqai/)列出 `freqtradeorg/freqtrade:stable_freqai` 和 CPU LightGBM；滚动标签不可作为复现锁。Docker 未就绪，本次未拉取镜像，未验证固定版本镜像 manifest/digest，阶段 2/3 补验。FreqAI 是 Freqtrade 内置组件，不单独选择不匹配版本。

TradingAgents v0.6.0 `openai_client.py` 已包含 deepseek ProviderSpec、官方端点及 DeepSeekChatOpenAI 思考模式处理。源码支持不等于实际工具调用、结构化输出、LangChain 依赖和完整研究流程已通过测试。默认配置仍含股票财务/SEC/yfinance 数据源，不能直接代替 BTC 数据，需要按市场禁用股票基本面并加入公开行情适配与证据时间戳。

[DeepSeek 官方价格页](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)直接请求成功。当前 `deepseek-flash` 对应 V4.1-Flash，支持 JSON Output 与 Tool Calls。每百万 Token 人民币价格快照：缓存命中输入空闲/高峰 0.02/0.04；未命中输入 1/2；输出 4/8。与任务书价格一致。模型上下文或输出上限不作为本项目请求限额；预算控制应设更保守的 Token 上限。

初期预算预估采用高峰未缓存价格且保留余量，运行前重新验证价格。未提供密钥、未请求模型列表、未执行收费调用；账户实际可用性未知。复杂模型自动升级禁用。

Binance 公共 `exchangeInfo?symbol=BTCUSDT` 本次超时，最低名义金额、精度及规则没有填猜测值。地区/账户/合约权限、数据使用条款、当前手续费和人民币兑 USDT 汇率均未完成核验；禁止据此宣称 RMB 200 已满足可执行条件。
