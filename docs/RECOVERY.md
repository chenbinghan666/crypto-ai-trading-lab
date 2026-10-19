# 故障恢复指南

## 常规检查

运行 `查看状态.cmd`，检查四个服务、报价时间和告警。“交易关闭”为当前正确状态，不要修改 dry_run 来解决页面问题。

行情中断时自动指数退避 2–60 秒，保留最后数据并标记过期，成功后记录恢复事件。检查网络/DNS，不关闭 TLS 校验，不绕过地区限制。

子服务退出由 supervisor 退避重启；HTTP 持续无响应超过宽限时间会终止恢复。market 网络重试仍更新心跳，避免断网导致进程重启风暴。Windows watchdog 在 supervisor 异常退出 5 秒后重启；Linux 父进程死亡信号防止遗留子服务占端口。

重复启动受 Windows 文件锁及 Linux flock 保护。进程身份使用 boot_id + /proc 启动 ticks，避免 WSL 校时导致墙上时间变化误判 PID。

## 停止、备份、恢复

双击 `停止系统.cmd` 后再备份整个 `data/system/`（含 sqlite、可能存在的 -wal/-shm 和本地凭证）。恢复也须先停止，不在运行中只复制一个数据库文件。Docker 先停容器再备份卷，不使用 `down -v`。

双击启动后保留历史数据，重复行情由主键去重。Windows 重启后须手动启动；不要用 `wsl --shutdown` 当日常停止命令，它影响该发行版其他服务。

磁盘满/数据库损坏需人工处理；当前未完成磁盘耗尽故障注入或自动备份调度。数据库失败不会返回健康成功。子服务日志超过 5 MB 时在下次启动轮转；Docker stdout 限额 10 MB × 3。

## 页面与登录

端口 8080/8081 冲突时不要自动杀死未知进程。先停本项目再排查；如修改端口，需同步更新页面链接、脚本及 compose。FreqUI 登录凭证通过 `FreqUI登录信息.cmd` 获取，也是解锁账户面板的本机管理密码，不是币安密钥。账户网络、权限、加密文件与迁移恢复见 [合约账户说明](BINANCE_ACCOUNT.md)。

当前回测/交易操作返回 403 是预期保护；不要解除限制来测试下单。配置问题查看 `logs/frequi-service.log`，Windows 守护问题查看 `logs/watchdog-host-error.log` 和 `logs/windows-watchdog.log`。

## 尚未实现的交易恢复

当前只实现行情去重和基础设施恢复，**未实现订单对账/重复订单防护的完整链路**。后续必须加入持久化订单意图、幂等键、模拟/交易所账本核对、未知订单禁止重试和持仓保护，再进行独立验收。这个版本不能直接切实盘。

## 中文目录乱码 / 无法加载 labapp.control

如果出现 `chdir(...閲忓寲浜ゆ槗...) failed` 或 `ModuleNotFoundError: No module named labapp`，原因可能是 Windows PowerShell 按旧代码页解码了 WSL 的 UTF-8 路径。当前入口统一通过 `scripts/wsl-common.ps1` 初始化 UTF-8，验证实际 WSL 工作目录和 Python 模块，再执行管理操作；所有 PowerShell 脚本保留 UTF-8 BOM 以兼容 Windows PowerShell 5.1。

关闭旧报错窗口，重新双击「FreqUI登录信息.cmd」或「启动系统.cmd」。启动和凭证读取无需改名中文目录。开发维护时可运行 `powershell -File scripts/test-launchers.ps1`，它分别以 936、437、65001 代码页验证状态和真实 CMD 凭证入口，报告只含通过/失败，不含密码。
# 合约模拟与回测恢复补充（2026-10-16）

网页控制流程与风险约束见 [PAPER_TRADING.md](PAPER_TRADING.md)。模拟状态、初始本金和研究模式保存在系统 SQLite；模拟订单与持仓在独立 `data/system/futures-paper.sqlite`。不要删除账本或去重记录来“修复”异常。

模拟被用户启用后，Worker 异常退出会退避重启；网络未校验通过时等待恢复，持仓和订单从原账本读取，新的入场仍须经过风控。点击网页停止会取消启用状态并停止 Worker。停止进程不会伪造平仓；已有模拟持仓在恢复后继续管理。关机或休眠期间不运行风险管理。

历史回测在服务退出时中断的任务会标记 interrupted，需从网页手动重试；已完成结果保留。可通过 `python -m scripts.check_paper` 进行隔离环境工程验收，不会启用实际模拟账户。实时网络联调及真实关闭 Codex 的全流程验收仍未完成，不能把离线通过当作现场验收。
