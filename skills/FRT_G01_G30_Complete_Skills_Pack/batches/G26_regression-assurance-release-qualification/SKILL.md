---
name: generation-batch-g26-regression-assurance-release-qualification
description: 全量回归测试、并行测试平台、Flaky治理与Release Qualification，用于FRT大型前端仓库转换平台的Production Closure层。
version: 1.0.0
batch: G26
risk_model: R0-R5
certificate_level: RQ0-RQ6
status: implementation-ready
---

# Generation Batch G26：全量回归测试、并行测试平台、Flaky治理与Release Qualification

## 1. 使命

从：

> 关键功能在真实用户条件下可发现、理解、完成、恢复

推进到：

> 全系统回归稳定、并行、可重复地覆盖需求、业务、数据、管理、可用性、安全和性能，并成为Release强制资格认证

本Batch必须形成可执行Skill、结构化Schema、CLI、管理端入口、测试、Evidence和Certificate，不能只生成设计文档。

## 2. 核心能力

- Requirement/Acceptance/State Machine派生Test Obligation
- Unit/Component/Contract/Integration/Journey分层协调
- Differential、Mutation、Visual/Semantic、Security和Performance Regression
- Synthetic Tenant、Deterministic Test Data、Environment Parity
- Flaky分类与Critical Quarantine阻断
- Impacted Test Selection、Parallel Grid、Worker Failover、RQ0–RQ6

## 3. 全局不变量

- 所有R4/R5 Gate采用非补偿式判断，任何Critical缺口均不可被平均分掩盖。
- 模型负责提出候选；编译器、类型系统、状态机、测试、Proof、设备和运行证据决定是否通过。
- Source Repository只读；所有生成、Mutation和修复在隔离Worktree、Sandbox和受控环境中完成。
- 所有正式结果绑定Commit、Artifact、Pack Lock、Policy、Environment和Toolchain Digest。
- 禁止Fake Success、Silent Semantic Loss、空异常处理、UI-only Authorization和直接修改Critical数据库状态。
- 所有Critical Side Effect都必须具备Idempotency、Audit、Reconciliation和明确Authority。
- 任何证据依赖变化后，相关Certificate必须自动变为STALE或RETEST_REQUIRED。

## 4. Skill清单

- **FRT-2600 — Regression Assurance Orchestrator**
- **FRT-2601 — Requirement-Derived Test Generator**
- **FRT-2602 — Model-Based Business Test Generator**
- **FRT-2603 — Unit and Component Test Coordinator**
- **FRT-2604 — API and Event Contract Test Coordinator**
- **FRT-2605 — End-to-End Journey Test Coordinator**
- **FRT-2606 — Differential Test Coordinator**
- **FRT-2607 — Mutation Test Coordinator**
- **FRT-2608 — Visual and Semantic Regression Coordinator**
- **FRT-2609 — Security Regression Coordinator**
- **FRT-2610 — Performance Regression Coordinator**
- **FRT-2611 — Test Data Management**
- **FRT-2612 — Synthetic Tenant and Account Generator**
- **FRT-2613 — Environment Parity Validator**
- **FRT-2614 — Flaky Test Detection and Quarantine**
- **FRT-2615 — Impacted Test Selection**
- **FRT-2616 — Parallel Test Grid**
- **FRT-2617 — Test Worker Failover**
- **FRT-2618 — Release Qualification Engine**
- **FRT-2619 — Regression Evidence Certificate**

| ID | Skill | 建议实现目录 |
|---|---|---|
| FRT-2600 | `Regression Assurance Orchestrator` | `skills/regression-assurance-orchestrator/SKILL.md` |
| FRT-2601 | `Requirement-Derived Test Generator` | `skills/requirement-derived-test-generator/SKILL.md` |
| FRT-2602 | `Model-Based Business Test Generator` | `skills/model-based-business-test-generator/SKILL.md` |
| FRT-2603 | `Unit and Component Test Coordinator` | `skills/unit-and-component-test-coordinator/SKILL.md` |
| FRT-2604 | `API and Event Contract Test Coordinator` | `skills/api-and-event-contract-test-coordinator/SKILL.md` |
| FRT-2605 | `End-to-End Journey Test Coordinator` | `skills/end-to-end-journey-test-coordinator/SKILL.md` |
| FRT-2606 | `Differential Test Coordinator` | `skills/differential-test-coordinator/SKILL.md` |
| FRT-2607 | `Mutation Test Coordinator` | `skills/mutation-test-coordinator/SKILL.md` |
| FRT-2608 | `Visual and Semantic Regression Coordinator` | `skills/visual-and-semantic-regression-coordinator/SKILL.md` |
| FRT-2609 | `Security Regression Coordinator` | `skills/security-regression-coordinator/SKILL.md` |
| FRT-2610 | `Performance Regression Coordinator` | `skills/performance-regression-coordinator/SKILL.md` |
| FRT-2611 | `Test Data Management` | `skills/test-data-management/SKILL.md` |
| FRT-2612 | `Synthetic Tenant and Account Generator` | `skills/synthetic-tenant-and-account-generator/SKILL.md` |
| FRT-2613 | `Environment Parity Validator` | `skills/environment-parity-validator/SKILL.md` |
| FRT-2614 | `Flaky Test Detection and Quarantine` | `skills/flaky-test-detection-and-quarantine/SKILL.md` |
| FRT-2615 | `Impacted Test Selection` | `skills/impacted-test-selection/SKILL.md` |
| FRT-2616 | `Parallel Test Grid` | `skills/parallel-test-grid/SKILL.md` |
| FRT-2617 | `Test Worker Failover` | `skills/test-worker-failover/SKILL.md` |
| FRT-2618 | `Release Qualification Engine` | `skills/release-qualification-engine/SKILL.md` |
| FRT-2619 | `Regression Evidence Certificate` | `skills/regression-evidence-certificate/SKILL.md` |

## 5. 输入

- G21–G25所有Contract、Journey、Certificate和Evidence
- Release Diff、Semantic Impact Graph、Dependency/Data Lineage
- Test Environment、Device Pool、Worker Pool和Fixture Registry

### 统一请求Envelope

```yaml
apiVersion: frt.openai.dev/v1alpha1
kind: GenerationBatchRequest
metadata:
  projectId: project://frt-platform
  releaseId: release://candidate
  runId: run://g26
spec:
  batch: G26
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

- Test Obligation Set
- Impacted Test Plan
- Environment/Data Plan
- Parallel Execution Plan
- Normalized Results
- Flaky/Mutation/Differential/Security/Performance Reports
- Release Qualification Decision
- Regression Certificate

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
  skillId: FRT-2600
  executionId: execution://controlled
status:
  state: succeeded | failed | blocked | inconclusive
  findings:
    critical: 0
    high: 0
  evidence:
    - artifact://evidence
  certificate:
    ref: certificate://g26
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
frt g26 plan --project frt-platform --release release://candidate
frt g26 execute --plan .frt/g26/plan.yaml
frt g26 verify --criticality R4,R5
frt g26 findings list --severity critical,high
frt g26 evidence build --release release://candidate
frt g26 certify --release release://candidate --level 5
```

REST/API至少提供：

```text
POST /v1/g26/plans
POST /v1/g26/executions
GET  /v1/g26/executions/{id}
GET  /v1/g26/findings
GET  /v1/g26/evidence/{id}
POST /v1/g26/certificates
POST /v1/g26/certificates/{id}/invalidate
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

统一错误前缀：`FRT-26XX`。

示例：

```text
FRT-26XX-0001  Critical输入或Owner缺失
FRT-26XX-0002  Scope或Tenant边界缺失
FRT-26XX-0003  Evidence无法追踪到Requirement/Artifact
FRT-26XX-0004  Critical Gate失败
FRT-26XX-0005  Certificate Scope与Release不一致
FRT-26XX-0006  Stale Evidence被错误计入通过结果
```

## 14. Release Gates

- [ ] Critical Requirement均有Test Obligation和Oracle
- [ ] Critical Journey不只断言UI而验证Authority
- [ ] R4/R5 Mutation存活=0
- [ ] Critical Flaky=0
- [ ] Environment Critical Drift=0
- [ ] Test Data Cross-Shard污染=0
- [ ] RQ5全部非补偿式Gate通过

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
