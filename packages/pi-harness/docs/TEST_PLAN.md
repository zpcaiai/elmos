# PI Harness 5.1 分层测试与证据计划

版本：`5.1.0`

测试基线：八项代码实现已完成；外部门禁环境尚未执行

外部执行证据：`NOT_RUN`

认证状态：`NOT_CERTIFIED`

## 1. 测试原则

- 测试对象按“代码、真实服务、真实部署、客户结果、独立验证”分层；低层通过不能替代高层证据。
- development、negative、holdout、representative workload 必须使用相互独立的 corpus。
- 每个测试都绑定精确版本、环境、租户、身份、权限、授权、原始证据、独立 verifier 和 replay 信息。
- 失败、跳过、超时、flaky、未知、部分恢复、证据缺失或自验证均不算通过。
- 测试结果不能把 `NOT_RUN` 批量改为通过；测试计划本身也不能产生认证结论。

## 2. 当前已完成的本地工程验证

这些结果只证明 repository-owned local engineering behavior：

- 默认包级测试：61 个用例中 57 个单元、集成、负向与失败关闭测试通过；真实 PostgreSQL、Temporal 各 1 个，以及 Identity/Crypto profile 2 个在未配置时明确 skip/`NOT_RUN`。
- 根级集成门禁固定源 ZIP SHA-256、425,097 bytes、798 entries、581,309 uncompressed bytes，并检查 82 个实现资产、16 项能力、8 个 Schema 和保守状态；4 个正向/负向门禁测试覆盖 archive drift、实现删除和虚假认证提升。
- `make -C packages/pi-harness check`：Python compileall 通过。
- Ruff 静态检查通过。
- mypy 2.1.0 `--strict` 使用 Temporal、psycopg 与 boto3 typed dependency extras 检查 44 个源文件通过，无 ignore 或遗留类型错误。
- CLI disposable demo、HTTP API 认证/幂等/租户隔离、typed result replay、executor fencing、workspace takeover、sandbox default deny 均有测试。
- 外部门禁 ledger 覆盖冻结 RC、内容寻址证据、完整 hash chain、CLI、幂等重放、事件/对象篡改、符号链接、错 release/environment/evidence、自证、错误 role、撤销/过期信任重验，以及 `FAILED`/`UNKNOWN` fail-closed；八门禁模拟齐备的结果上限仍为 `READY_FOR_HUMAN_DECISION` / `NOT_CERTIFIED`。
- S3 Object Lock 归档覆盖精确 account/region/KMS、public-access block、versioning、COMPLIANCE/GOVERNANCE retention、基于服务端 LastModified 的最短保留期、create-only 写入、SHA-256、VersionId receipt、幂等重放、provider timeout reconciliation 和无法观测时的 `UNKNOWN`；Terraform AWS 6.62.0 `init/validate` 为 0 errors/0 warnings，但没有执行 plan/apply。
- 一次性 PostgreSQL 17.5：001/002 迁移、`NOSUPERUSER NOBYPASSRLS` 服务角色、任务/事件/环境/执行器/工具结果/artifact 全路径通过；结果为本地自证工程证据。
- 生产 SDK 导入/API：Temporal SDK 1.32.0 workflow/worker versioning 与 sandbox prepare、PyJWT 2.13.0、cryptography 46.0.7、boto3 1.43.83、真实 Ed25519 与 X.509 SPIFFE decode 通过。
- 一次性 Temporal Server 1.31.2 + Python SDK 1.32.0：原生 workflow/activity、success、pause/resume、cancel 和实际 history replay 通过，并修复了 `PAUSE_REQUESTED` 与提前 resume 的竞态；该 in-memory dev server 没有 TLS、外部 namespace、代表性负载或独立验证，只是本地自证工程证据。
- 一次性 Identity profile：真实 RS256 token、HTTPS JWKS、CA 签发 server/client certificate、TLS client-certificate chain、SPIFFE tenant/project binding、CRL 和 revoked-certificate/header-spoof 负测通过；loopback TLS 明确禁用环境代理以防本地资格流量被工作站代理改道；本地 CA/JWKS 不是外部 IdP 或生产 PKI。
- 从干净临时环境构建并安装 wheel，`pip check`、import 和 `qualification-status` 通过；本地 wheel SHA-256 为 `89fa9da2460f0d254dafc5bce0f6c1b289de6229c25d192a3d0c09a90125008e`，其门禁输出仍为八项 `CODE_COMPLETE`、外部 `NOT_RUN`、认证 `NOT_CERTIFIED`。该 wheel 未发布、未签名，也不是生产部署证据。
- 容器构建使用 digest-pinned Python base 和带 SHA-256 的完整 Python production dependency lock；本地镜像 manifest digest 为 `sha256:4a2e8581b58d2faafa94f6bfe1369d841baf3557d18b22a07f5d306a90d17699`，以 UID/GID 65532 非 root 运行，且内置 001/002 PostgreSQL migrations。该 digest 只记录当前本地自证构建，不是已发布或已签名的生产制品。
- AWS Terraform 模块在临时目录完成 format/init/validate；没有执行 plan/apply，云证据仍为 `NOT_RUN`。

上述结果不改变下列外部状态：真实 PostgreSQL/Temporal/云 Provider、IdP/mTLS、独立验证器、灾备、客户验收、生产部署均为 `NOT_RUN`；认证为 `NOT_CERTIFIED`。

## 3. 测试阶段与放行关系

| 层级 | 测试内容 | 执行环境 | 结果上限 | 不能证明 |
|---|---|---|---|---|
| T0 | lint、schema、compile、unit、property、本地 API | repo/临时目录 | `LOCAL_ENGINEERING_PASS` | 真实服务、部署、客户结果 |
| T1 | PostgreSQL/IdP/mTLS/Temporal 集成和负测 | staging、隔离租户 | `READY_FOR_EXTERNAL_GATE` | 独立认证、生产稳定性 |
| T2 | 云 Provider、代表性负载、故障注入、DR | 隔离账户/区域 | `READY_FOR_EXTERNAL_GATE` | 客户业务价值、长期 SLO |
| T3 | 独立验证器复核与 holdout | 不同信任域 | `READY_FOR_HUMAN_DECISION` | 自动认证 |
| T4 | 客户 UAT、canary、rollback、生产观察 | 受控生产候选环境 | `READY_FOR_HUMAN_DECISION` | 委员会未签署的认证 |

## 4. P0/P1 测试矩阵

### T1-PG：PostgreSQL 与数据正确性

正向：迁移、启动、连接池、事务提交、事件顺序、幂等重放、artifact digest、并发 lease、checkpoint 恢复。

负向：错租户读写、缺失 tenant context、越权 SQL、重复 migration、死锁/serialization failure、连接断开、时钟偏移、超限 payload、过期 lease takeover 无 checkpoint、损坏 artifact。

独立 holdout：不复用本地 SQLite fixture，使用独立 schema、独立数据集和独立并发工作负载。

通过条件：RLS 与应用层双重隔离；事务和事件无丢失/乱序；可重放；数据校验和备份恢复一致。否则 `NOT_RUN` 或 `FAILED`。

### T1-IDP：身份、租户和 mTLS

正向：operator、workload、auditor 登录；正确 tenant/project binding；短期凭证；证书轮换；撤销后立即拒绝；审计事件完整。

负向：无 token、过期 token、错 issuer/audience、错租户 claim、证书过期/撤销、重放、break-glass 超时、actor/workload 混用、扩大权限的 resume 或 executor replacement。

通过条件：权限来自认证身份与可信资源绑定；缺失/歧义 context fail closed；所有拒绝可审计。IdP/mTLS 未在真实环境执行前保持 `NOT_RUN`。

### T1-TEMPORAL：工作流耐久性与 fencing

正向：创建、排队、规划、执行、验证、暂停、恢复、取消、重试、分支、checkpoint、artifact 发布。

故障注入：worker crash、worker replacement、late callback、重复 activity、Temporal reconnect、signal 重复、网络短断、数据库短断、历史 replay、版本升级和降级。

断言：旧 generation 不能发布；同一 workspace 不能并发写；重试不产生重复 effect；未知 provider 结果进入 reconciliation；恢复后的 sandbox override 不扩大权限。

### T1-API：契约与兼容性

覆盖 OpenAPI 中的 health/readiness、task create/get、events、artifacts、state action、branch；验证 schema dialect、分页边界、错误 problem shape、幂等 key、Content-Length 上限和 bearer/mTLS ingress。

兼容测试至少覆盖当前 API 版本、上一支持版本和拒绝的未来 major 版本。任何 typed ToolResult 不得被 adapter 转为字符串或丢弃 media/encrypted/unknown 类型。

### T2-CLOUD：Provider 与副作用

对每个 provider × account × region × version 单独执行：plan、人工批准、apply、runtime observation、成本/配额、撤销、rollback、destroy/orphan cleanup。

负向必须覆盖：宽 IAM、公共 bucket、任意 egress、secret 越权、错误 region、错误租户、KMS 不可用、超配额、provider timeout、返回未知状态。未知状态必须停止自动 close/retry/publication。

通过条件：provider DTO 只存在 adapter；原生证据和规范化证据分别保留；真实 plan/apply/runtime/rollback 原始输出可回放。

### T2-DR：灾备与恢复

测试场景：主区域丢失、PostgreSQL 丢失、object store 丢失、Temporal worker 全损、KMS/证书恢复、损坏备份、半恢复、重复恢复、恢复时旧 lease 和未完成 effect。

记录：RPO、RTO、恢复时间线、恢复前后 digest、事件序列、租户隔离、task 状态、artifact、审计、告警、人工动作和 orphan cleanup。

通过条件：达到书面 RPO/RTO；失败恢复不被标记成功；恢复后的数据与证据链可独立核验。

### T3-VERIFY：独立验证器与证据完整性

验证器使用不同 actor、不同凭证、不同服务边界和独立 holdout corpus。测试 pass、fail、unknown、stale、revoked、tampered、self-verified、wrong-environment、wrong-release。

只有验证器确认 digest、签名、时间窗、授权、环境和 replay 后，结果才能进入 `INDEPENDENTLY_VERIFIED`。本地测试只能测试 fail-closed behavior，不能替代该确认。

### T4-UAT/RELEASE：客户验收与生产候选

客户旅程：create task → monitor events → pause/resume → recover after worker loss → inspect artifacts → export evidence；角色覆盖 owner、operator、auditor，租户隔离和支持升级均需真实操作。

生产候选：signed artifact、SBOM、部署 smoke、canary、peak/degraded traffic、mixed-version、rollback、alert acknowledgement、SLO observation、cost ceiling 和 runbook rehearsal。

通过条件：客户签署 UAT、critical/high 缺陷处置、canary 与 rollback 都有原始证据；没有这些证据不得宣称生产就绪。

## 5. 风险覆盖规划结果

仓库 Autonomous QA `04-risk-coverage-planning` 已针对 PostgreSQL、Temporal、Cloud、IdP/mTLS、独立验证、DR、客户验收、生产部署八类需求生成风险覆盖计划：

- 计划用例：829；
- 当前规划预算：最多 500 cases、wall-clock 86,400 秒；
- 结果：`PARTIAL`；
- 阻塞原因：`REQUIRED_SCOPE_EXCEEDS_CASE_BUDGET`、`REQUIRED_SCOPE_EXCEEDS_WALL_CLOCK_BUDGET`；
- `required_scope_silently_dropped`：`false`；
- 该规划结果是本地规划证据，不是测试执行证据，也不是认证。

执行前必须选择其一：把预算提升到能覆盖完整 required scope，或按 T1/T2/T3/T4 分批执行并保留完整父子 traceability；禁止简单截断前 500 个用例。

## 6. 结果记录格式

每个 `test_id` 必须有一条不可变结果记录，至少包括：

```json
{
  "test_id": "T1-TEMPORAL-GEN-FENCE-001",
  "requirement_id": "PI-TEMPORAL-001",
  "release_sha": "<exact-git-sha>",
  "artifact_digests": ["sha256:<...>"],
  "environment": {
    "temporal_version": "<exact-version>",
    "database": "<exact-version>",
    "region": "<exact-region>",
    "tenant_id": "<bound-tenant>"
  },
  "authorization_id": "<approved-run>",
  "executor": "<runner-identity>",
  "independent_verifier": "<different-trust-domain> or NOT_RUN",
  "raw_evidence": ["<immutable-evidence-ref>"],
  "replay": "<controlled-replay-ref>",
  "result": "NOT_RUN",
  "limitations": ["real Temporal environment not configured"],
  "cleanup": "<cleanup-evidence-ref>"
}
```

结果枚举至少支持 `PASS`、`FAIL`、`BLOCKED`、`UNKNOWN`、`FLAKY`、`NOT_RUN`；没有原始证据或独立验证时，不得使用 `PASS` 推导认证。

## 7. 测试执行节奏

- 每次代码变更：T0 全量，变更影响的 T1 contract/negative subset。
- 每日 staging：T1 PostgreSQL、IdP/mTLS、Temporal、API 和安全负测。
- 每周或每次 provider 变更：T2 Cloud、DR、成本/配额和 orphan cleanup。
- 每个 release candidate：T3 独立 verifier holdout、T4 UAT/canary/rollback。
- 每次事故或恢复：重跑受影响的 T1/T2/T3，保留原始证据与差异，不覆盖历史结果。

## 8. 当前结论

本计划明确区分“代码已完成”和“商业生产证据已完成”：前者已经完成；真实 PostgreSQL/Temporal/云 Provider、IdP/mTLS、独立验证器、灾备、客户验收和生产部署测试仍为 `NOT_RUN`。认证状态固定为 `NOT_CERTIFIED`，直到授权、真实执行、独立验证和人工放行全部存在。
