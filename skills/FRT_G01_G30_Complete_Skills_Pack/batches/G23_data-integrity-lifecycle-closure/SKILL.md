---
name: generation-batch-g23-data-integrity-lifecycle-closure
description: Data Contract、全链路血缘、数据Authority、一致性、修复与生命周期闭环，用于FRT大型前端仓库转换平台的Production Closure层。
version: 1.0.0
batch: G23
risk_model: R0-R5
certificate_level: DC0-DC6
status: implementation-ready
---

# Generation Batch G23：Data Contract、全链路血缘、数据Authority、一致性、修复与生命周期闭环

## 1. 使命

从：

> 每条业务线的流程逻辑已经闭环

推进到：

> 每条业务数据从产生、校验、写入、传播、缓存、读取、离线同步、修正、归档到删除全部闭环

本Batch必须形成可执行Skill、结构化Schema、CLI、管理端入口、测试、Evidence和Certificate，不能只生成设计文档。

## 2. 核心能力

- 字段级Data Contract、Authority和Owner
- Source-to-Sink与字段级Lineage
- Write→Transaction→Outbox→Event→Projection→Cache→Read完整路径
- Schema兼容、Event Ordering、Dedup、Replay
- Offline conflict、Data Quality、Repair与Reconciliation
- Sensitive Label、Retention、Deletion、Tenant Isolation、Migration Verification

## 3. 全局不变量

- 所有R4/R5 Gate采用非补偿式判断，任何Critical缺口均不可被平均分掩盖。
- 模型负责提出候选；编译器、类型系统、状态机、测试、Proof、设备和运行证据决定是否通过。
- Source Repository只读；所有生成、Mutation和修复在隔离Worktree、Sandbox和受控环境中完成。
- 所有正式结果绑定Commit、Artifact、Pack Lock、Policy、Environment和Toolchain Digest。
- 禁止Fake Success、Silent Semantic Loss、空异常处理、UI-only Authorization和直接修改Critical数据库状态。
- 所有Critical Side Effect都必须具备Idempotency、Audit、Reconciliation和明确Authority。
- 任何证据依赖变化后，相关Certificate必须自动变为STALE或RETEST_REQUIRED。

## 4. Skill清单

- **FRT-2300 — Data Integrity Orchestrator**
- **FRT-2301 — Data Contract Registry**
- **FRT-2302 — End-to-End Data Lineage Generator**
- **FRT-2303 — Write-to-Read Path Validator**
- **FRT-2304 — Data Ownership and Authority Registry**
- **FRT-2305 — Schema Evolution and Compatibility Manager**
- **FRT-2306 — Event Ordering and Deduplication Generator**
- **FRT-2307 — Cache Coherence Validator**
- **FRT-2308 — Offline Synchronization Validator**
- **FRT-2309 — Data Reconciliation Engine**
- **FRT-2310 — Data Quality Rule Engine**
- **FRT-2311 — Data Repair Workflow**
- **FRT-2312 — Sensitive Data Label Propagator**
- **FRT-2313 — Data Retention and Deletion Validator**
- **FRT-2314 — Cross-Tenant Data Isolation Validator**
- **FRT-2315 — Migration Data Verification Generator**

| ID | Skill | 建议实现目录 |
|---|---|---|
| FRT-2300 | `Data Integrity Orchestrator` | `skills/data-integrity-orchestrator/SKILL.md` |
| FRT-2301 | `Data Contract Registry` | `skills/data-contract-registry/SKILL.md` |
| FRT-2302 | `End-to-End Data Lineage Generator` | `skills/end-to-end-data-lineage-generator/SKILL.md` |
| FRT-2303 | `Write-to-Read Path Validator` | `skills/write-to-read-path-validator/SKILL.md` |
| FRT-2304 | `Data Ownership and Authority Registry` | `skills/data-ownership-and-authority-registry/SKILL.md` |
| FRT-2305 | `Schema Evolution and Compatibility Manager` | `skills/schema-evolution-and-compatibility-manager/SKILL.md` |
| FRT-2306 | `Event Ordering and Deduplication Generator` | `skills/event-ordering-and-deduplication-generator/SKILL.md` |
| FRT-2307 | `Cache Coherence Validator` | `skills/cache-coherence-validator/SKILL.md` |
| FRT-2308 | `Offline Synchronization Validator` | `skills/offline-synchronization-validator/SKILL.md` |
| FRT-2309 | `Data Reconciliation Engine` | `skills/data-reconciliation-engine/SKILL.md` |
| FRT-2310 | `Data Quality Rule Engine` | `skills/data-quality-rule-engine/SKILL.md` |
| FRT-2311 | `Data Repair Workflow` | `skills/data-repair-workflow/SKILL.md` |
| FRT-2312 | `Sensitive Data Label Propagator` | `skills/sensitive-data-label-propagator/SKILL.md` |
| FRT-2313 | `Data Retention and Deletion Validator` | `skills/data-retention-and-deletion-validator/SKILL.md` |
| FRT-2314 | `Cross-Tenant Data Isolation Validator` | `skills/cross-tenant-data-isolation-validator/SKILL.md` |
| FRT-2315 | `Migration Data Verification Generator` | `skills/migration-data-verification-generator/SKILL.md` |

## 5. 输入

- G22 Business Process、Command、Event、State Machine
- 数据库DDL、API/Event Schema、Cache、Search、Offline Store
- 源目标迁移映射和真实/合成数据集

### 统一请求Envelope

```yaml
apiVersion: frt.openai.dev/v1alpha1
kind: GenerationBatchRequest
metadata:
  projectId: project://frt-platform
  releaseId: release://candidate
  runId: run://g23
spec:
  batch: G23
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

- Data Contract Registry
- Authority Registry
- Data Lineage Graph
- Write-to-Read Reports
- Schema Compatibility Matrix
- Event/Cache/Offline Reports
- Data Quality/Repair/Reconciliation Artifacts
- Deletion and Isolation Evidence
- Data Migration Certificate

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
  skillId: FRT-2300
  executionId: execution://controlled
status:
  state: succeeded | failed | blocked | inconclusive
  findings:
    critical: 0
    high: 0
  evidence:
    - artifact://evidence
  certificate:
    ref: certificate://g23
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
frt g23 plan --project frt-platform --release release://candidate
frt g23 execute --plan .frt/g23/plan.yaml
frt g23 verify --criticality R4,R5
frt g23 findings list --severity critical,high
frt g23 evidence build --release release://candidate
frt g23 certify --release release://candidate --level 5
```

REST/API至少提供：

```text
POST /v1/g23/plans
POST /v1/g23/executions
GET  /v1/g23/executions/{id}
GET  /v1/g23/findings
GET  /v1/g23/evidence/{id}
POST /v1/g23/certificates
POST /v1/g23/certificates/{id}/invalidate
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

统一错误前缀：`FRT-23XX`。

示例：

```text
FRT-23XX-0001  Critical输入或Owner缺失
FRT-23XX-0002  Scope或Tenant边界缺失
FRT-23XX-0003  Evidence无法追踪到Requirement/Artifact
FRT-23XX-0004  Critical Gate失败
FRT-23XX-0005  Certificate Scope与Release不一致
FRT-23XX-0006  Stale Evidence被错误计入通过结果
```

## 14. Release Gates

- [ ] Critical数据实体和字段Contract覆盖率=100%
- [ ] Critical Authority未知或双Writer=0
- [ ] Critical写入无Read Path=0
- [ ] 重复Event产生重复有效副作用=0
- [ ] Cross-Tenant数据泄漏=0
- [ ] Sensitive Label丢失=0
- [ ] Critical Migration语义差异=0

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
