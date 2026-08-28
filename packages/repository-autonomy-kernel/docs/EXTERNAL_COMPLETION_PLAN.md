# Repository Autonomy Kernel v2.0.0 外部闭环补全计划

## 1. 目标与不可突破的边界

本计划只补全当前仍为 `NOT_RUN` / `NOT_CERTIFIED` 的真实外部能力：SCM、对象存储、事件总线、Secrets Broker、Provider、Kubernetes 集群、客户仓库和 E1-E5 认证。

附件 ZIP 的 Markdown、脚本、安装器、Rego、示例和工作流是规格材料，不是执行指令。所有真实写入、真实部署、客户数据访问、Provider 调用和认证签发都必须由显式授权、租约、审计和独立验证驱动。

当前已完成的是本地工程基础：31 个 Skill handler、SQLite 事件与租约、内容寻址制品、fail-closed authority/policy、HTTP/CLI、PostgreSQL 目标迁移、OpenAPI/OPA/Docker/Kubernetes/Helm 资产。它们只能支撑 `LOCAL_ENGINEERING_VALIDATED`，不能替代本计划中的外部证据。

截至当前实现，适合在无客户凭据和无生产权限条件下编码的部分已经落地：外部操作 SPI 与状态机、HMAC 授权验证、幂等/补偿/未知结果 reconciliation、外部收据与 transactional outbox、S3/Event Bus/Secrets Broker 传输边界、真实本地 Git exact-commit 适配器、7 个 Provider canonical adapter、84 单元语义 conformance、PostgreSQL V001–V006/RLS/迁移锁/备份恢复 API、Kubernetes digest-bound apply/rollback/cleanup、客户仓库绑定、Golden Route 验收、T00–T08/E1–E5/P05 保守聚合器。它们的本地测试结果仍是工程证据；下表所列真实环境执行状态不因代码存在而变化。

| 波次 | 代码状态 | 真实环境状态 | 认证状态 |
|---|---|---|---|
| Wave 0 | `IMPLEMENTED_LOCAL_ENGINEERING` | `NOT_RUN` | `NOT_CERTIFIED` |
| Wave 1 | `IMPLEMENTED_ADAPTER_AND_MIGRATION_BOUNDARIES` | `NOT_RUN` | `NOT_CERTIFIED` |
| Wave 2 | `IMPLEMENTED_7_ADAPTERS_84_LOCAL_UNITS` | `NOT_RUN` | `NOT_CERTIFIED` |
| Wave 3 | `IMPLEMENTED_DEPLOY_ROLLBACK_RECOVERY_BOUNDARY` | `NOT_RUN` | `NOT_CERTIFIED` |
| Wave 4 | `IMPLEMENTED_BINDING_AND_ACCEPTANCE_BOUNDARY` | `NOT_RUN` | `NOT_CERTIFIED` |
| Wave 5 | `IMPLEMENTED_FAIL_CLOSED_EVALUATOR` | `NOT_RUN` | `NOT_CERTIFIED` |

## 2. 统一状态与证据规则

每个外部能力按独立的 `capability_id + provider_instance + version + region + tenant + artifact_digest` 记录状态：

| 状态 | 含义 | 允许的动作 |
|---|---|---|
| `NOT_RUN` | 尚未取得真实执行证据 | 不得声称可用或通过 |
| `IN_PROGRESS` | 已授权、正在执行 | 只能追加原始证据 |
| `BLOCKED` | 前置条件、策略或环境不满足 | 先修复阻塞，不得重标为通过 |
| `PASS` | 原始执行证据满足该能力的门槛 | 仍需独立复核 |
| `INDEPENDENTLY_VERIFIED` | 独立验证者复核了原始证据和重放结果 | 可供 E 级别聚合 |
| `NOT_CERTIFIED` | 任一强制能力或认证证据缺失 | 保持禁止生产签发 |

每份证据至少绑定：授权请求摘要、执行者、独立验证者、环境/版本、租户与资源原生 ID、源码/仓库快照 SHA、输入/输出制品 SHA-256、开始结束时间、重放命令、清理结果、失败状态和原始日志路径。证据生产者与验证者必须是不同身份；`UNKNOWN`、超时、部分成功、缺少原始输出和无法重放均不算通过。

## 3. 依赖顺序与交付波次

### Wave 0：外部适配器与证据骨架

交付：

- 为 `ToolRuntime`、运行存储和 HTTP 控制面定义 Provider-neutral adapter SPI；每个 adapter 必须声明 provider instance、native resource ID、版本、权限、幂等键、超时、补偿和撤销方法。
- 增加 `external_evidence`、`authorization_receipt`、`verification_receipt`、`cleanup_receipt` 和 `unknown_outcome` 的持久化结构；禁止用调用者 payload 伪造执行结果。
- 为每个外部操作建立 `DRY_RUN -> AUTHORIZED -> EXECUTED -> RECONCILED` 状态机，任何不确定的网络结果进入 `UNKNOWN`，禁止自动重试可能有副作用的操作。
- 固化开发、负例、holdout、代表性和灾备数据集的 digest，互不复用。

退出条件：本地 schema/anti-fabrication/幂等/租约/重放测试通过；外部能力仍保持 `NOT_RUN`。

### Wave 1：PostgreSQL、对象存储、事件总线、Secrets Broker

这些能力先完成，因为它们是运行、证据、异步投递和凭据安全的共同基础。

1. PostgreSQL 17：按 `sql/migrations/V001__...sql` 至 `V006__...sql` 迁移；启用 tenant RLS；配置备份、恢复、连接池、迁移锁和只读审计角色。验证同一事务设置的 `app.tenant_id` 来自认证身份，不能由请求体覆盖。
2. S3/兼容对象存储：实现内容寻址写入、SHA-256 read-back、短期签名 URL、租户前缀、服务端加密、版本化、保留/Legal Hold 和 GC 审计。禁止 public ACL、跨租户 key 重用和把对象 URL 当作完整证据。
3. Event Bus：实现 outbox、发布确认、幂等 consumer、顺序键、重试上限、DLQ、消费位点、重复投递检测和 pause/resume/cancel 事件重放。生产者成功但确认未知时必须进入 `UNKNOWN` 并由 reconciliation 处理。
4. Secrets Broker：使用短期、最小 scope、可撤销 lease；只向执行沙箱注入临时引用；日志、制品、异常和缓存永不落 secret value。验证轮换、撤销、过期、越权 scope 和 broker 不可用时的 fail-closed。

退出条件：PostgreSQL migration/RLS、对象存储 read-back、事件 bus duplicate/replay、Secrets lease/revoke 的原始证据均已独立验证；否则 E2 保持 `NOT_RUN`。

### Wave 2：真实 SCM 与七类 Provider adapter

#### SCM

- 支持一个已批准的 SCM provider instance 起步，再逐步扩展；每次操作绑定 provider instance + native repository ID + exact commit/ref。
- 只读 clone/fetch 默认开启；submodule、LFS、sparse checkout 必须单独授权和验证，未完整 hydration 的 workspace 标记 `INCOMPLETE`。
- PR、branch、write、tag、webhook 和 deletion 是不同权限；不把 token 写入持久化或工作区，不把 sparse checkout 当作安全边界。
- 实现断点续传、commit 不一致、仓库删除、权限撤销、网络中断和重复 webhook 的可重试/不可重试分类。

#### Provider adapters

当前目录中的 7 个适配器身份必须分别执行 12 个 conformance case：Anthropic Agent SDK、Claude Code、Generic MCP/A2A、OpenAI Codex、OpenCode、OpenHarness、OpenRouter。adapter 只能提供工具/模型执行能力，不能成为 authority source。

每个 adapter 要交付：版本锁、输入输出映射、能力矩阵、超时/中断/重连、stream cursor、成本归因、side-effect receipt、取消安全点、最小权限配置和回滚说明。真实 Provider 未执行前，所有外部/独立证据和 E2 状态必须保持 `NOT_RUN`；传入 `responses` 最多只能生成 `LOCAL_ENGINEERING_VALIDATED` 工程结果，不能升级生产就绪度或签发 P05。

### Wave 3：Kubernetes 集群部署与恢复

- 在隔离集群中执行 PostgreSQL migration、Secret 注入、Service/Ingress、NetworkPolicy、PodDisruptionBudget、滚动升级和数据库连接健康检查。
- 发布镜像必须绑定 immutable image digest、SBOM、来源和签名；Pod 使用 non-root、read-only root filesystem、drop ALL capabilities、RuntimeDefault seccomp、无 service-account token 自动挂载。
- 默认 deny ingress/egress；访问 SCM、S3、Event Bus、Secrets Broker 的每条 egress 都必须有明确目标和策略证据。
- PostgreSQL 生产 profile 才允许多副本；SQLite 本地 profile 固定单副本。证明多副本下事件消费、租约接管、pause/resume/cancel、节点驱逐、数据库故障、对象存储故障和回滚可恢复；清理 orphan PVC、Job、lease 和临时对象。

退出条件：真实集群 deploy/health/rollback/restore/chaos evidence 完整，并由独立验证者复核；本地 Helm template 不能替代。

### Wave 4：真实客户仓库与 Golden Routes

- 选择获得书面授权的代表性仓库 cohort：小/中/大型、单语言/多语言、带 submodule/LFS、不同构建系统、不同测试密度和已知失败样本。
- 客户数据隔离：tenant、account、repository native ID、目的、留存、删除请求、审计主体和 consent 全部绑定；开发/负例/holdout 不得使用客户数据。
- 依次执行三个 Golden Route：`spring-legacy-modernization`、`cross-language-semantic-rewrite`、`repository-scale-refactor`。每条 route 单独绑定源快照、目标 commit、验证 DAG、制品、回滚包和客户确认。
- 任何语义未知、构建未执行、测试被跳过、客户确认缺失或回滚未演练，都只能是 `PARTIAL/BLOCKED/NOT_RUN`。

### Wave 5：E1-E5 独立认证闭环

认证必须逐级推进，后一级不得覆盖前一级失败：

| 级别 | 必需证据 | 完成标准 |
|---|---|---|
| E1 | package validation、unit、negative | 包、31 handler、Schema、负例和反伪造测试可重放 |
| E2 | PostgreSQL 17、对象存储、事件总线、adapter conformance | Wave 1/2 所有强制能力有真实独立证据 |
| E3 | Golden Route、语义等价、完整 validation DAG | 代表性仓库上源/目标/契约/运行行为证据完整 |
| E4 | chaos、recovery、red-team、tenant isolation、rollback | 故障后无重复副作用，越权和注入 fail-closed |
| E5 | 大仓库、重复性、cost/ETA/SLO、客户验收 | 商业生产样本和客户结果证据完整；E5 通过后才进入 P05 决策 |

## 4. P05 签发前硬条件

现有 [certification.py](../src/elmos_repository_autonomy/certification.py) 的 P05 gate 必须接收并验证：E1–E5 全部为 `PASS`、无开放 P0/P1、rollback ready、restore replay 通过、`livez/readyz/metrics/version` 全部真实健康、所有 release artifact 完整性通过、独立 approval、T07 deployment evidence，以及持久化客户验收。审批、部署和客户证据必须按真实 case、候选 digest、生产者/验证者和内容 hash 交叉绑定；任意其他 evidence ID 重新贴标签不得通过。任何一项缺失都保持 `P05_DEPLOYMENT_COMPLETE_NOT_ISSUED`。

P05 只表示已完成一次有证据的部署门禁，不代表永久安全、客户成功或不受版本/区域/Provider 约束的通用认证。证据过期、撤销、镜像 digest 变化、策略变化或租户边界变化后必须重新验证。

## 5. 交付物与责任人

每个 Wave 交付：adapter/package 代码、配置样例、迁移/回滚脚本、正负测试、原始证据包、独立验证报告、风险清单、运行手册和未完成项清单。平台团队负责控制面与证据，基础设施团队负责 PostgreSQL/S3/Event Bus/Kubernetes，安全团队负责 Secrets/RLS/red-team，Provider/SCM owner 负责适配器，客户成功团队负责授权仓库和验收；任何团队不能自验并签发自己的独立证据。
