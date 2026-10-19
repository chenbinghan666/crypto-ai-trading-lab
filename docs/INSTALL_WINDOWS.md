# Windows 安装计划

当前未安装任何依赖，也未修改 WSL、系统权限或 Docker 设置。

已检测 Windows 11、WSL2 Ubuntu（Stopped），Docker 不在 PATH，Windows Python 3.8.10 不符合两套上游 >=3.11 要求。

## 批准阶段 2 后的选择

优先 Docker Desktop + WSL2 后端：先确认 Docker Desktop 是否已安装但未加入 PATH，若未安装，使用 [Docker 官方 Windows 安装文档](https://docs.docker.com/desktop/setup/install/windows-install/)。安装、管理员操作及较大镜像下载前说明内容并取得授权。建议将镜像/数据磁盘置于 D 盘；不自动迁移 WSL。

备选：在 WSL Ubuntu 内单独检查系统版本与 Python，以独立 Python >=3.11 venv 部署。不能用现有 Windows 3.8 环境强行安装。不安装 GPU/CUDA、本地语言模型或整套研究依赖。

验证命令（待执行，不代表已通过）：

```powershell
wsl --list --verbose
docker version
docker compose version
```

阶段 2：核验 `2026.9` 对应镜像标签及 digest，拉取后记录 `freqtrade --version`；验证配置 dry_run、空交易所凭证、spot、禁用管理 API。用公开数据完成基线回测后再启动可停止的 Dry-run。阶段 3 再核验 FreqAI 镜像与 CPU LightGBM。

WSL 服务能列出不表示 Linux 内依赖已验证；Docker 命令缺失也不证明程序从未安装。C 盘可用空间约 26 GiB，下载前必须重新检查空间。
