# 架构设计（阶段 1，未实现运行时）

> 2026-10-16 更新：当前已实现独立基础设施，详见 DEPLOYMENT.md 和 SYSTEM_DELIVERY.md。以下为完整交易系统目标设计，AI/训练/风控/执行尚未实现。当前运行链路为 Windows watchdog → supervisor → market / dashboard / FreqUI webserver，不运行交易。

## 数据流与信任边界

公开行情 → UTC 收盘 K 线校验/缓存 → FreqAI 预测与规则策略 → 严格信号校验 → 独立 risk_gate → Freqtrade Dry-run → 订单/成交账本 → 本地报表。
TradingAgents 从只读行情快照研究，通过缓存提供可选辅助；禁止获得交易所凭证、编辑风险配置或直接提交订单。新闻内容视为不可信数据，不执行其中指令。

## 五个异步循环

1. 持续行情与订单监测：遵守限流，校验新鲜度，断线指数退避；订单/持仓未知时阻止开仓。
2. 每根新收盘 K 线评估及 FreqAI 推理：比较 5m/15m/1h；以交易对、市场类型、周期、收盘时间建立持久去重键。
3. Agent 研究：初始每日两次，重大波动/成交量/漂移触发事件研究；受事件去重、冷却、每日调用上限和总预算约束。结果有效期独立于下一次调度时间。
4. 模拟执行与持仓管理：独立处理退出、止损和订单核对，不等待 LLM；新仓必须通过统一风险闸门。
5. 再训练和复盘：CPU 单任务，比较 6h/12h/24h；训练产物带数据/特征/代码版本，验证及人工批准后才替换模型。日报/周报由本地账本生成。

默认 `agent_required`：无有效研究禁止新仓；阶段 2 单独测试基础策略属于离线/隔离基础验收，不代表已批准融合系统使用 `baseline_fallback`。后者须人工批准且只允许已验证基线。任何模式都持续管理已有模拟持仓。

## 信号契约（阶段 6 实现）

版本化 JSON Schema/Pydantic，拒绝未知字段。必填 schema_version、created_at_utc、valid_until_utc、symbol、market_type、timeframe、action（LONG/SHORT/HOLD）、confidence、rationale、evidence_refs、data_cutoff_utc、model_id、research_run_id；可选 suggested_stop、suggested_take_profit、risk_flags。

必须检查时区、数据截止不晚于决策时点、创建时间不在未来、有效期、目标市场与周期、持久去重。缺失、冲突和无效数据转 HOLD。confidence 不作为胜率。现货 SHORT 拒绝执行。

## 持久化与恢复

Freqtrade 订单库与研究/预算账本分离，初期 SQLite 足够；各数据库单写者，备份用一致性快照。预算请求前事务预留，成功后按 usage 结算；超时且未知是否计费时保留预留，不能无条件退款。日/月以明确的 Asia/Singapore 账期统计，所有事件时间存 UTC。

执行意图、去重键与状态更新事务化；重启先核对未完成意图和模拟订单，未知状态不重复提交。日志包含 run_id、research_run_id、策略/模型/配置版本、订单 ID 和拒单原因，不记录密钥或授权头。

## 资源与部署边界

Windows + WSL2 + Docker 为首选；Freqtrade/FreqAI 一组容器，研究进程隔离，初期不引入 Redis/Kubernetes。建议 WSL 总内存起点 6 GiB、4 个逻辑 CPU，训练单并发、LightGBM 2 线程；这是待压测参数，不修改系统设置。资源不足则错峰训练或暂停新仓。

阶段 2 才创建可启动 Compose；先锁定镜像 digest，显式关闭真实交易及外部管理端口。此阶段没有交易入口，JSON 中的 false 不是未来安全实现的替代品。
