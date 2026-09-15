# Runner 建设状态：2026-09-14

总体：仓库预检工具已实现并本地验证；四条生产/客户兼容 lane 的部署和资格验证尚未完成。
认证 `NOT_CERTIFIED`，外部证据 `NOT_RUN`。没有创建远端主机、VM、Runner 注册、数据库或接收端。

## 已交付

- `lane-topology.json`：四条 lane、固定工作负载分配、主机隔离及接入缺口。
- `scripts/operations/runner_lanes.py`：结构检查、路由、本地观察、内容寻址和完整性校验。
- `scripts/operations/probe_windows_runner.ps1`：只读 Windows 查询和可清理的原生文件锁探测。
- `.github/workflows/runner-lane-preflight.yml`：默认分支、手动触发、只读权限、分 lane environment 的预检。
- `MULTIPLATFORM_RUNBOOK.md`：部署顺序、依赖、专项完成条件、Ethan 接收边界、回滚和清理。

## 已执行

- 14 项 Python 单元/反例测试通过，包括平台误分配、Rootless/WSL/Desktop/远程端点、主机共用、
  路径穿越、篡改、伪造认证字段、采集期间输入变更、未知 Windows 查询和临时文件清理。
- 手动流水线 YAML 解析及只读/触发限制断言通过；未在 GitHub 实际运行。
- 既有 Spring `validate_spring_runner_topology.py --json` 静态检查通过，结果仍为
  `STATIC_CONTRACT_ONLY / NOT_RUN / NOT_CERTIFIED`。
- 本机最终原始对象和观察报告位于 `artifacts/runner-lanes/windows-final/`。
  报告对象 SHA-256：`8392894552c9c2b223def8d73f9e2911883bf19f08b268e8b0bea9e9d50c3913`。
  `verify` 完整性检查通过，来源认证仍为 `NOT_VERIFIED`。

## 本机实际观察

Windows 11 Pro Insider Preview，build 26340，x86_64；PowerShell 7.6.5；系统 Locale zh-CN；
Hyper-V vmms 服务 Running；Edge 154.0.4258.12。
这些是观察值，不是推荐或锁定的生产版本；正式客户矩阵应另行绑定接受的稳定版本。

在 F:\PythonPro\elmos 的临时目录内：大小写不敏感；CRLF、GBK、GB18030、364 字符路径读写通过；
临时目录已清理。原生 FileShare.None 排他文件锁在系统临时目录通过并清理。
这些微型探测不代替实际 Spring/SQL/浏览器/官方 MiniApp 工作负载。

Docker 服务版本查询失败。Java/Maven/dotnet/CMD 可从 PATH 找到；MSBuild/sqlcmd 未从 PATH 找到，
这不能证明机器上完全未安装这些组件。Hyper-V 服务状态也不证明 Server VM 或容器已创建。
完整可选功能、GUI/DPI/输入法、企业 AD/CA/代理、数据库身份验证等尚未执行。

## 完成外部落地所缺输入

1. 独立 Rootless Linux、独立数据库性能机、Mac 的实际主机别名/接入配置和精确版本。
2. Windows Server VM 镜像/许可证、资源/私网配置，以及客户兼容所需域、数据库和测试项目。
3. Ethan 可信接收端地址、认证协议、可信主机绑定、HSM/KMS 引用和独立验证者。
4. 精确客户工作负载、独立测试语料及长期 SLO/多区 DR 的真实运行窗口。

未提供这些输入前，主机部署、注册、证据提交和领域认证均不能标记完成。
