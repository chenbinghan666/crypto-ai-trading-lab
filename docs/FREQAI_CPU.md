# FreqAI CPU 训练部署与使用

部署日期：2026-10-17。训练由独立 `training_service` 进程管理，Codex 和浏览器不是运行依赖。Windows 一键启动、停止和 Docker Compose 自动包含训练服务；Docker 构建仍未在本机实测。

## 已安装的内容

Freqtrade 2026.9 / FreqAI 官方 BaseRegressionModel、FreqaiDataKitchen 和 DataDrawer，LightGBM 4.7.0、scikit-learn 1.9.1、DataSieve 0.1.9。新增依赖固定于 `requirements-freqai-cpu.lock.txt`，按原 `requirements.lock.txt` 约束安装，`pip check` 通过。

使用自定义 CPU LightGBM `fit` 扩展，其余训练、特征标准化、标签处理、预测及模型保存使用 FreqAI 官方接口。禁用 Tensorboard，不安装 Torch、XGBoost、CUDA 或本地语言模型；不调用 DeepSeek、不产生 API 推理费用。这个扩展不是上游未经修改的 LightGBMRegressor 示例类。

## 网页操作

1. 双击「启动系统.cmd」，打开 http://127.0.0.1:8080 并解锁。
2. 进入「操作中心 → 分析与交易」，点击「开始模型训练」：默认使用当前模拟市场对应的数据源（Gate，或已校验 Binance 历史）。
3. 也可在下方「FreqAI CPU 模型训练」选择数据源，点击「启动 CPU 训练」。页面展示排队、训练、评估、完成或失败，以及模型误差和版本。
4. 关闭页面后训练继续；重开页面可查看结果。「停止 CPU 训练」取消排队或终止本次训练，已有结果保留。

同一时刻只运行一个训练任务，启动间隔至少 60 秒，计算限制为 2 线程、单次最多 2500 根 1h K 线，进程最多运行 180 秒。服务异常重启后，正在运行的任务标记 interrupted，需手动重试，不自动重复计算。模型保存在 `data/system/freqai/jobs/<任务ID>/artifacts`。

## 数据和评估

- Gate：读取公开合约接口的最近最多 2000 根 1h K 线，只使用已收盘部分，检查时钟、连续性和数据新鲜度。Binance：使用先前已校验的官方历史合约数据。
- 冻结数据为 Feather，并记录 SHA256、交易所、时间范围及版本；冻结后禁止训练进程对外连接。
- 16 项只依赖当前及过去数据的特征，包括收益、均线偏离、波动、振幅、相对成交量和小时周期。Gate 成交量单位只在 Gate 数据内部使用，不混合 Binance 成交量。
- 预测目标为未来 6 根 1h 蜡烛收益；按时间顺序划分约 80% 训练 / 20% 测试，训练与测试之间隔离 6 根蜡烛。测试数据不参与标准化拟合或参数选择。
- 显示 MAE、零收益预测基线 MAE、方向正确率和保存后重载一致性。没有调参搜索，没有拿测试集选择模型。
- 评估的是收益预测误差，不是交易策略收益；未计手续费、滑点和资金费率。即使误差改善，也不代表可交易或可盈利。

## 启用边界

本轮只部署训练与评估，不自动将模型接入 Gate 模拟、改变策略或启用真实交易。训练策略的开仓信号恒为 0，入场回调始终拒绝。候选模型必须后续经过含成本策略回测、风险审核及人工选择才能接入模拟。

部署验收已在真实 Gate 已收盘数据上训练模型并保存重载，首个模型未优于零收益预测基线，未用于交易。66 项自动化测试通过，包含特征因果性、标签时间隔离、训练保存重载、认证/同源保护、重复任务与取消恢复。

参考官方：[FreqAI 安装与架构](https://www.freqtrade.io/en/stable/freqai/)、[配置与模型扩展](https://docs.freqtrade.io/en/latest/freqai-configuration/)。
