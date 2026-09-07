# OpenHands Absorption P0/P1 实现追踪矩阵

## 判定口径

`IMPLEMENTED` 只表示代码级能力、接口、持久化/迁移边界和本地测试已经落入仓库；
它不等于真实环境已部署或生产认证。ZIP 的通用 acceptance 要求包括 contract、
tenant isolation、Chaos recovery、observability、cost attribution、security review、
Golden Repo 和 rollback runbook。只有本地可执行项可由本地门禁给出工程证据；其余
外部项继续为 `NOT_RUN`。

## Skill 到实现和证据

| Skill | 代码状态 | 主要实现 | 本地验证重点 | 尚未执行的命名证据 |
|---|---|---|---|---|
| P0-01 Stateless Agent Runtime | IMPLEMENTED | runtime、supervisor、service、API | 单写租约、预算、取消、终态、防自报完成 | Temporal worker replacement、Golden、load/Chaos、安全审查 |
| P0-02 Immutable Event Ledger | IMPLEMENTED | SQLite/PostgreSQL ledger、RLS、outbox、projection | 单调序列、hash chain、幂等、correction、重建 | 真实 PostgreSQL/RLS/failover、event bus、容量 |
| P0-03 Action-Observation Protocol | IMPLEMENTED | typed protocol、Tool Gateway、workspace API | Schema、能力、超时、截断、脱敏、reconciliation | 真实工具插件矩阵、生产 sandbox、独立攻击测试 |
| P0-04 Persistence/Checkpoint/Replay | IMPLEMENTED | layered checkpoint、CAS、resume、audit/isolated replay | 损坏 checkpoint 回退、manifest binding、未知副作用阻断 | 真实 Temporal/PostgreSQL/S3、RPO/RTO、灾难恢复 |
| P0-05 Workspace/Sandbox | IMPLEMENTED | Local/Docker/K8s/Firecracker/SSH、Secret Broker、warm pool | fencing、路径/symlink、快照证明、隔离等级不夸大 | 生产 gVisor/Kata/microVM/SSH、escape/tenant bleed |
| P0-06 Distributed Runtime Plane | IMPLEMENTED | worker/admission、event cursor、REST/WS/gRPC、Temporal | quota/backpressure、fencing、认证作用域、cursor 防篡改 | 真实集群伸缩、Temporal history、OTel、SLO/容量 |
| P0-07 Context/Condenser | IMPLEMENTED | typed sources、persistent candidates/views、ranking/conflict | tenant/security/freshness、must-retain、token budget、fingerprint | 真实 repo graph/vector/cache、模型 token parity、Golden |
| P0-08 Firewall/Security | IMPLEMENTED | deterministic firewall、DSL、taint、approval、kill switch | RBAC/path/network/secret/injection/destructive、R6 双人审批 | 生产网络隔离、红队、独立安全签字 |
| P0-09 Hooks/Verification Gates | IMPLEMENTED | deterministic hooks、profiled gates、traceability、signed evidence | required evidence、zero-tolerance、waiver expiry、repair bound | 真实 CI/E2E/security evidence、独立 verifier、release gate |
| P1-01 Skill Disclosure/Router | IMPLEMENTED | metadata/index、semantic/history routing、progressive metering | permission/tenant/risk/conflict、L0-L3 顺序、并发 token quota | 真实 embedding/benchmark corpus、成本/延迟基线 |
| P1-02 Capability Package | IMPLEMENTED | deterministic ZIP、Ed25519/KMS interface、registry/pin/revoke | path/digest/signature/lock/SBOM/provenance/lifecycle/conformance | 生产 KMS、registry、publisher identity、供应链独审 |
| P1-03 Durable Agent DAG | IMPLEMENTED | DAG、Temporal definitions、plan update、merge/compensation | cycle/fencing/budget/conflict、running node immutability、state transfer | 真实 Temporal、large fan-out、worker death、Golden merge |
| P1-04 Provider/ACP Layer | IMPLEMENTED | six adapters、HTTP/SSE、durable sessions、routing/reconciliation | exact idempotency、stream sequence、checkpoint/cancel/usage、shadow | Codex/Claude/OpenHands 等真实 Provider 合同和账单 |
| P1-05 Browser Evidence/Replay | IMPLEMENTED | Playwright driver、device matrix、masking、CAS evidence、flake block | semantic locator、origin、binary safety、PII/secret、allowlist expiry | 真实浏览器/设备、视频/trace、跨构建 replay、独立验收 |

## 横切交付

| 交付 | 仓库资产 | 当前状态 |
|---|---|---|
| PostgreSQL schema | `0001`、`0002` forward migrations 与两份 down migration | CODE_IMPLEMENTED；真实数据库 NOT_RUN |
| Object/event persistence | S3 CAS、NATS/Kafka publisher、transactional outbox adapters | CODE_IMPLEMENTED；真实服务 NOT_RUN |
| Production API | authenticated REST、WebSocket、protobuf `Struct` gRPC gateway | CODE_IMPLEMENTED；真实 FastAPI/gRPC 部署、E2E、压测 NOT_RUN |
| Evidence governance | signed pack、trust/revocation、独立角色、retention/export/delete | CODE_IMPLEMENTED；外部签名/删除证明 NOT_RUN |
| Qualification | 8 类 campaign 的 digest-bound runner/store/CLI plan | CODE_IMPLEMENTED；全部 campaign NOT_RUN |
| Release | deterministic package、pin/revoke/rollback、runbooks | CODE_IMPLEMENTED；canary/GA NOT_RUN/NOT_GA |

## 固定结论

代码实现已完成；本地 disposable 探针已有局部工程 evidence，但真实生产等价
Temporal/PostgreSQL、生产 sandbox、外部 Provider 成功、浏览器 physical device、
独立 Golden holdout、representative load/Chaos、独立安全审查尚未闭合，因此当前
仍保持 `NOT_CERTIFIED / NOT_GA`，不能冒充生产认证或 GA。详见
`evidence/QUALIFICATION_EXECUTION_2026-08-28.md`。
