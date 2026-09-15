# 四条 Runner lane 的建设与接入

当前交付是可执行的分流契约、探测器、反例测试和手动预检流水线。
它不等于主机已购买、已部署、已注册或已通过客户工作负载认证。
`lane-topology.json` 中空的 host_binding / evidence_authority 是待接入项，不能自行填造。
所有外部证据保持 `NOT_RUN`，认证保持 `NOT_CERTIFIED`。

## 顺序和边界

1. Ethan 控制的独立 Linux x86_64：专用非 root 账户、本地 Rootless Docker、私网入口、默认拒绝网络策略。
   Spring 使用既有 `deploy/production/compose/docker-compose.spring-runner.yml`，按
   `deploy/production/runner/RUNNER_PRODUCTION_BASELINE.md` 部署。项目生成使用既有
   `scripts/operations/rootless_project_runner.py`。不要将 Mac/Windows Docker Desktop 或 WSL 当独立 Linux。
2. Windows x86_64：Windows 11 Pro + Hyper-V；独立 Windows Server 2022/2025 VM。
   系统安装、许可证、VM 存储、网络和重启窗口由主机所有者提供。
   原生、Server VM、Windows 容器和 Linux VM 分别留存结果；镜像 digest、宿主 build、
   guest build、隔离模式都属于精确元组。不得从 Docker CLI 存在推断容器可运行。
3. 独立 Linux 数据库性能机：不得与普通 CI 共用性能测试主机；固定硬件、数据库/驱动版本、
   数据集、并发、计时方法、暖机和测量窗口，再运行现有 Batch 31 门禁。
   75ms 的指标种类、百分位、查询集合和负载由既有精确路线契约确定，不能用一次平均值代替。
4. 现有 Mac M3：保留 Apple、ARM64、MiniApp 和浏览器专项；Rosetta 结果不能当原生 ARM64。

Windows 容器兼容性按 Microsoft 的精确支持矩阵选择，不能简单概括为所有版本号必须完全相同：
[系统要求](https://learn.microsoft.com/en-us/virtualization/windowscontainers/deploy-containers/system-requirements)、
[版本与隔离模式兼容性](https://learn.microsoft.com/en-us/virtualization/windowscontainers/deploy-containers/version-compatibility)。
[.NET Framework 仅支持 Windows](https://dotnet.microsoft.com/en-us/learn/dotnet/what-is-dotnet-framework)，
IIS/WCF/WinForms/WPF 的对应 .NET Framework 路线放入 Windows lane。

## 可立即运行

在仓库根目录，使用 Python 3.10+；CI 各主机还需 PowerShell 7 (`pwsh`) 和 Git。

```powershell
python scripts/operations/runner_lanes.py validate
python -m unittest discover -s scripts/operations -p test_runner_lanes.py -v
python scripts/operations/runner_lanes.py route spring-rootless
python scripts/operations/runner_lanes.py collect --lane windows-native-x64 --output artifacts/runner-lanes/windows
```

Linux 和 Mac 使用同一命令，替换 `--lane`，必要时将 `python` 替换为 `python3`。
`--workspace` 可指定一次性探测所在卷；NTFS/大小写/长路径结果仅适用于该目录和当前 Python 进程。
脚本只运行固定的本机查询及临时文件探测，不执行客户脚本、不安装软件、不切换容器引擎。
退出 3 表示平台不匹配或检查失败；退出 0 只表示结构检查或本地平台匹配，不是部署就绪。

输出两个以 SHA-256 命名的 JSON 对象。使用 collect 返回的 report 路径校验：

```powershell
python scripts/operations/runner_lanes.py verify artifacts/runner-lanes/windows/<report-sha256>.json
```

摘要能发现字节篡改，不能证明来源真实。报告绑定采集器、Windows 探测器和拓扑摘要，
原始输出留在本地，可能含机器路径和 Docker 元数据；只通过组织授权的证据通道传输。

## 主机接入与流水线

为每条 lane 提供独立主机绑定、账户、工作目录、短期凭据引用、网络白名单、
固定 OS/toolchain/image 版本、TTL/维护窗口、配额以及证据接收端。
现有 runner 服务/调度器仍是执行边界；这套预检不提供新的任意 shell 或认证服务。

GitHub 使用现有组织管理的 Runner 注册流程，将 manifest 中的 labels 绑定到精确主机。
先配置四个 manifest environment 的默认分支限制与独立审核人，再启用
`.github/workflows/runner-lane-preflight.yml`。该 workflow 只有手动触发，拒绝非默认分支，
不执行 PR、不缓存跨租户数据、不上传原始主机数据、不授予部署密钥。
注册令牌应短期使用；禁止写入 Git、日志或报告。标签只是调度提示，不是可信主机证明。
生产 Runner 不能用于不可信仓库；使用现有可信沙箱和工作负载准入边界。

## 专项完成条件（当前全部待真实执行）

| 专项 | 要执行和保存的原始结果 |
|---|---|
| Spring Windows | 实际遗留仓库 PowerShell 构建、NTFS 大小写/长路径/CRLF/文件锁；AD/LDAP/Kerberos、CA/代理、SQL Server JDBC |
| SQL/ChinaDB Windows | 隔离 SQL Server Windows 身份验证；ODBC/OLE DB/DSN/厂商客户端；GBK/GB18030 与中文系统 Locale；精确驱动版本 |
| Frontend Windows | Edge/浏览器精确版本、DPI、字体、输入法、证书/代理、企业桌面旅程；官方 MiniApp Windows 工具链 |
| QA/Foundry Windows | PowerShell/CMD、Windows Service、VS/MSBuild、GUI 自动化、原生沙箱和容器真实运行及清理 |
| Linux Rootless | Spring、项目生成、PostgreSQL/Redis/Kafka、备份恢复、多租户调度/网络隔离、Runner Fleet |
| Linux DB | DM8/ChinaDB 实库、契约指定 75ms 指标、CDC、明细对账、独立 holdout、回滚恢复 |
| Mac | Apple/ARM64 真实构建和设备/浏览器/MiniApp 旅程 |
| Ethan | 可信主机注册、HSM/KMS、不可变原始对象、认证身份、独立验证、各领域门禁；B38–B45 多区 DR/长期 SLO/故障演练 |

## Ethan 证据接收契约

发送端提交内容寻址的原始对象和观察报告。接收端必须从认证身份和可信注册记录
绑定 tenant/project/actor/host/revision/invocation，验证摘要、时效、精确环境与工作负载，
执行幂等接收及未知结果对账，再由独立验证器和领域门禁决定资格。
本地 JSON 不得生成这些可信字段；`verify` 仅验证完整性。
接收端 URL、认证协议和 KMS 引用未提供前不发送、不创建模拟接收成功回执。

## 回滚与清理

预检仅创建临时探测文件并自行删除；结果目录按组织留存策略管理。
停止注册的 Worker 时，先停止接收新任务、排空/取消现有任务并取得清理回执，
再通过现有 Runner 管理流程注销并撤销凭据。不要删除共享数据库、Docker 卷或用户工作区。
Hyper-V/容器/数据库部署的 rollback/destroy 必须在其真实隔离环境分别验证。
缺少主机、企业域、设备、数据库、接收端或独立验证时，保留对应缺口，不能提升认证状态。
