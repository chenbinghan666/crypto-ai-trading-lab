# 模型路由与预算设计

TradingAgents quick/deep 两档均指定 provider=deepseek、base_url=https://api.deepseek.com、model=deepseek-flash；API 默认禁用，不回退到其他提供商或本地 LLM。上游配置键为 `max_debate_rounds=1`、`max_risk_discuss_rounds=1`；工具轮数、输出 Token、并发和事件配额在阶段 4 实测后设置。

月预算 RMB 30、日软限额 RMB 1、每研究 RMB 0.5。未获批准超出日软限额时也停止研究；不能把软限制解释为自行授权额外费用。单研究包含全部子调用和重试，每次网络请求前预留预算，有限重试也扣预算，未知计费保守保留。总预算跨定时与事件共享并持久化，重启不清零。

记录 provider/model、输入/输出/缓存 Token、价格版本、估计费用、延迟和失败；供应商账单为最终依据。预算闸门不能保证外部账单绝对不超支，平台若有独立额度限制应一并设置。无密钥或授权时仅 mock 验证，真实 API 冒烟测试在阶段 4 单独批准。
