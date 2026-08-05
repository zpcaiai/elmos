---
name: generation-batch-g28-resilience-ha-dr
description: 高可用、故障隔离、Chaos、灾难恢复与持续韧性认证，用于FRT大型前端仓库转换平台的Production Closure层。
version: 1.0.0
batch: G28
risk_model: R0-R5
certificate_level: RC0-RC6
status: implementation-ready
---

# Generation Batch G28：高可用、故障隔离、Chaos、灾难恢复与持续韧性认证

## 1. 使命

从：

> 系统在目标并发和压力下稳定运行

推进到：

> 服务、数据库、队列、Worker、存储、Provider、设备和Region故障时仍可隔离、保护、恢复并满足RTO/RPO

本Batch必须形成可执行Skill、结构化Schema、CLI、管理端入口、测试、Evidence和Certificate，不能只生成设计文档。

## 2. 核心能力

- Dependency Failure Model与Common Cause分析
- 端到端Deadline、Retry Budget、Circuit Breaker、Bulkhead
- Queue Durability、Replay、Stateful Failover、Fence Token
- Control Plane/Worker/Artifact/Evidence/DB/Region HA
- Chaos、Backup Restore、DR Drill、RTO/RPO
- Safe/Read-Only/Partial Availability与RC0–RC6

## 3. 全局不变量

- 所有R4/R5 Gate采用非补偿式判断，任何Critical缺口均不可被平均分掩盖。
- 模型负责提出候选；编译器、类型系统、状态机、测试、Proof、设备和运行证据决定是否通过。
- Source Repository只读；所有生成、Mutation和修复在隔离Worktree、Sandbox和受控环境中完成。
- 所有正式结果绑定Commit、Artifact、Pack Lock、Policy、Environment和Toolchain Digest。
- 禁止Fake Success、Silent Semantic Loss、空异常处理、UI-only Authorization和直接修改Critical数据库状态。
- 所有Critical Side Effect都必须具备Idempotency、Audit、Reconciliation和明确Authority。
- 任何证据依赖变化后，相关Certificate必须自动变为STALE或RETEST_REQUIRED。

## 4. Skill清单

- **FRT-2800 — Resilience Orchestrator**
- **FRT-2801 — Dependency Failure Model Registry**
- **FRT-2802 — Timeout, Retry and Circuit Breaker Validator**
- **FRT-2803 — Bulkhead and Failure Isolation Validator**
- **FRT-2804 — Graceful Degradation Runtime**
- **FRT-2805 — Queue Durability and Replay Validator**
- **FRT-2806 — Stateful Failover Validator**
- **FRT-2807 — Control Plane High Availability**
- **FRT-2808 — Worker Pool High Availability**
- **FRT-2809 — Artifact and Evidence Store Resilience**
- **FRT-2810 — Database Failover Validator**
- **FRT-2811 — Region Failure Validator**
- **FRT-2812 — Chaos Experiment Generator**
- **FRT-2813 — Backup and Restore Validator**
- **FRT-2814 — Disaster Recovery Drill Generator**
- **FRT-2815 — RTO and RPO Compliance Validator**
- **FRT-2816 — Safe Mode and Read-Only Mode Generator**
- **FRT-2817 — Partial-Service Availability Validator**
- **FRT-2818 — Resilience Runbook Generator**
- **FRT-2819 — Resilience Certification**

| ID | Skill | 建议实现目录 |
|---|---|---|
| FRT-2800 | `Resilience Orchestrator` | `skills/resilience-orchestrator/SKILL.md` |
| FRT-2801 | `Dependency Failure Model Registry` | `skills/dependency-failure-model-registry/SKILL.md` |
| FRT-2802 | `Timeout, Retry and Circuit Breaker Validator` | `skills/timeout,-retry-and-circuit-breaker-validator/SKILL.md` |
| FRT-2803 | `Bulkhead and Failure Isolation Validator` | `skills/bulkhead-and-failure-isolation-validator/SKILL.md` |
| FRT-2804 | `Graceful Degradation Runtime` | `skills/graceful-degradation-runtime/SKILL.md` |
| FRT-2805 | `Queue Durability and Replay Validator` | `skills/queue-durability-and-replay-validator/SKILL.md` |
| FRT-2806 | `Stateful Failover Validator` | `skills/stateful-failover-validator/SKILL.md` |
| FRT-2807 | `Control Plane High Availability` | `skills/control-plane-high-availability/SKILL.md` |
| FRT-2808 | `Worker Pool High Availability` | `skills/worker-pool-high-availability/SKILL.md` |
| FRT-2809 | `Artifact and Evidence Store Resilience` | `skills/artifact-and-evidence-store-resilience/SKILL.md` |
| FRT-2810 | `Database Failover Validator` | `skills/database-failover-validator/SKILL.md` |
| FRT-2811 | `Region Failure Validator` | `skills/region-failure-validator/SKILL.md` |
| FRT-2812 | `Chaos Experiment Generator` | `skills/chaos-experiment-generator/SKILL.md` |
| FRT-2813 | `Backup and Restore Validator` | `skills/backup-and-restore-validator/SKILL.md` |
| FRT-2814 | `Disaster Recovery Drill Generator` | `skills/disaster-recovery-drill-generator/SKILL.md` |
| FRT-2815 | `RTO and RPO Compliance Validator` | `skills/rto-and-rpo-compliance-validator/SKILL.md` |
| FRT-2816 | `Safe Mode and Read-Only Mode Generator` | `skills/safe-mode-and-read-only-mode-generator/SKILL.md` |
| FRT-2817 | `Partial-Service Availability Validator` | `skills/partial-service-availability-validator/SKILL.md` |
| FRT-2818 | `Resilience Runbook Generator` | `skills/resilience-runbook-generator/SKILL.md` |
| FRT-2819 | `Resilience Certification` | `skills/resilience-certification/SKILL.md` |

## 5. 输入

- G27 Workload、Capacity、Degradation与Performance Certificate
- 生产依赖图、拓扑、Region、Backup、Queue和State Store
- Critical Capability与Recovery Objective

### 统一请求Envelope

```yaml
apiVersion: frt.openai.dev/v1alpha1
kind: GenerationBatchRequest
metadata:
  projectId: project://frt-platform
  releaseId: release://candidate
  runId: run://g28
spec:
  batch: G28
  sourceArtifacts:
    - artifact://previous-batches
  targetEnvironment:
    ref: environment://controlled
  requiredCriticality:
    - R4
    - R5
  requestedCertificateLevel: 5
```

## 6. 输出

- Failure Model Set
- Timeout/Retry/Circuit Plans
- Isolation Matrix
- HA/Failover/Queue/Artifact/DB/Region Reports
- Chaos and Restore Evidence
- DR Drill and RTO/RPO Report
- Runbooks
- Resilience Certificate

所有输出必须：

- 使用稳定ID和版本号；
- 记录Producer Skill、Execution、Input Digests与Toolchain；
- 写入Evidence Graph；
- 支持从Requirement、Capability、Data、Test、Finding、Certificate双向查询；
- 不允许覆盖旧Evidence，只能追加新版本和失效关系。

## 7. Orchestrator工作流

```text
加载上游Certificate与Artifact
→ 校验Scope、Digest与Freshness
→ 建立本Batch Registry / Contract / Model
→ 生成验证义务
→ 创建隔离环境与Synthetic Data
→ 执行静态、动态、差分、Mutation和故障场景
→ 归一化Finding和Evidence
→ 应用非补偿式Release Gates
→ 生成管理端视图与Runbook
→ 签发或阻断本Batch Certificate
→ 注册持续重新认证触发器
```

## 8. Skill Runtime Contract

每个子Skill必须实现：

```text
manifest()
validate_input()
plan()
execute()
collect_evidence()
classify_findings()
apply_release_gates()
render_admin_views()
issue_or_invalidate_certificate()
```

### 统一执行结果

```yaml
apiVersion: frt.openai.dev/v1alpha1
kind: SkillExecutionResult
metadata:
  skillId: FRT-2800
  executionId: execution://controlled
status:
  state: succeeded | failed | blocked | inconclusive
  findings:
    critical: 0
    high: 0
  evidence:
    - artifact://evidence
  certificate:
    ref: certificate://g28
```

## 9. 数据与Schema要求

- 所有Registry对象必须有`id`、`version`、`owner`、`criticality`、`scope`、`status`。
- 所有关系使用显式Edge：`IMPLEMENTS`、`VERIFIES`、`DEPENDS_ON`、`GOVERNS`、`INVALIDATES`、`RELEASED_IN`。
- 所有Critical对象必须绑定Tenant/Workspace/Environment Scope。
- 所有时间字段使用明确Instant/Deadline/Duration语义。
- Money不得使用二进制浮点。
- Unknown、Missing、Null、Empty必须分离。

## 10. API与CLI

```bash
frt g28 plan --project frt-platform --release release://candidate
frt g28 execute --plan .frt/g28/plan.yaml
frt g28 verify --criticality R4,R5
frt g28 findings list --severity critical,high
frt g28 evidence build --release release://candidate
frt g28 certify --release release://candidate --level 5
```

REST/API至少提供：

```text
POST /v1/g28/plans
POST /v1/g28/executions
GET  /v1/g28/executions/{id}
GET  /v1/g28/findings
GET  /v1/g28/evidence/{id}
POST /v1/g28/certificates
POST /v1/g28/certificates/{id}/invalidate
```

## 11. 管理端要求

- Registry/Contract/Model Explorer；
- Findings、Owner、Deadline和Remediation；
- Evidence Graph与Certificate Scope；
- Release Gate和Blocking Reason；
- 仅允许Typed Command，不允许通用数据库字段编辑器；
- R4/R5操作必须有权限、Reason、Impact Preview、Approval和Audit。

## 12. 测试要求

至少覆盖：

```text
Schema Validation
Positive / Negative Contract Tests
Permission and Tenant Isolation
State Machine and Model-Based Tests
Failure / Timeout / Retry / Cancellation
Differential and Mutation
Environment Parity
Worker Failover
Evidence Integrity
Certificate Invalidation
```

Critical测试不得因重试最终通过而隐藏首次失败；必须区分Flaky、Infrastructure Failure和Deterministic Failure。

## 13. Diagnostics

统一错误前缀：`FRT-28XX`。

示例：

```text
FRT-28XX-0001  Critical输入或Owner缺失
FRT-28XX-0002  Scope或Tenant边界缺失
FRT-28XX-0003  Evidence无法追踪到Requirement/Artifact
FRT-28XX-0004  Critical Gate失败
FRT-28XX-0005  Certificate Scope与Release不一致
FRT-28XX-0006  Stale Evidence被错误计入通过结果
```

## 14. Release Gates

- [ ] Critical依赖Failure Model和Recovery Plan覆盖率=100%
- [ ] Unsafe Retry、Split Brain、Critical Message Loss=0
- [ ] Old Leader/Expired Lease提交正式结果=0
- [ ] Critical Artifact/Evidence不可恢复丢失=0
- [ ] Critical Backup必须真实Restore通过
- [ ] Critical RTO/RPO违规=0
- [ ] Safe Mode不得关闭授权、隔离、审计和幂等

## 15. Definition of Done

- [ ] 所有子Skill均有独立`SKILL.md`、Manifest、Input/Output Schema和单元测试。
- [ ] Orchestrator支持全量和增量执行。
- [ ] 管理端支持查询、下钻、Evidence、Finding和Certificate。
- [ ] Critical路径覆盖正向、负向、异常、并发、故障和对抗场景。
- [ ] 本Batch Certificate可签发、失效、撤销和重放。
- [ ] 所有Blocking Finding关闭后必须重新执行受影响测试，而不是手工改状态。
- [ ] 与G21–G30统一Production Closure Graph兼容。

## 16. Codex实施边界

Codex应生成完整可运行项目代码，不得只生成接口或TODO。必须包括：

```text
Domain Models
Persistence Migrations
API
Background Workers
CLI
Admin UI
Tests
Observability
Runbooks
Docker / Local Compose
CI Release Gates
```

遇到信息不足时：

1. 将假设写入`assumptions.yaml`；
2. 生成保守、Default-Deny、无真实不可逆副作用的实现；
3. 对R4/R5不确定项创建Blocking Product Decision；
4. 不得以Mock通过替代Production实现。
