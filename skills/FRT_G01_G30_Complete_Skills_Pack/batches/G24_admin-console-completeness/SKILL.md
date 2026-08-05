---
name: generation-batch-g24-admin-console-completeness
description: 管理端能力矩阵、运营治理、异常处置、数据修正与全后台闭环，用于FRT大型前端仓库转换平台的Production Closure层。
version: 1.0.0
batch: G24
risk_model: R0-R5
certificate_level: AC0-AC6
status: implementation-ready
---

# Generation Batch G24：管理端能力矩阵、运营治理、异常处置、数据修正与全后台闭环

## 1. 使命

从：

> 业务与数据已经实现完整闭环

推进到：

> 管理端完整查看、治理、审批、修正、对账、恢复和审计所有关键能力，且不依赖数据库脚本

本Batch必须形成可执行Skill、结构化Schema、CLI、管理端入口、测试、Evidence和Certificate，不能只生成设计文档。

## 2. 核心能力

- Admin Object × Action × Role × Scope × Environment矩阵
- 高风险操作Impact Preview、Reason、Approval、Typed Command、Audit
- Manual Case、Data Repair、Reconciliation正式后台流程
- Job/Worker/Skill/Pack/Model/Artifact/Certificate全治理
- 安全批量操作、Search、KPI、Admin E2E

## 3. 全局不变量

- 所有R4/R5 Gate采用非补偿式判断，任何Critical缺口均不可被平均分掩盖。
- 模型负责提出候选；编译器、类型系统、状态机、测试、Proof、设备和运行证据决定是否通过。
- Source Repository只读；所有生成、Mutation和修复在隔离Worktree、Sandbox和受控环境中完成。
- 所有正式结果绑定Commit、Artifact、Pack Lock、Policy、Environment和Toolchain Digest。
- 禁止Fake Success、Silent Semantic Loss、空异常处理、UI-only Authorization和直接修改Critical数据库状态。
- 所有Critical Side Effect都必须具备Idempotency、Audit、Reconciliation和明确Authority。
- 任何证据依赖变化后，相关Certificate必须自动变为STALE或RETEST_REQUIRED。

## 4. Skill清单

- **FRT-2400 — Admin Console Completeness Orchestrator**
- **FRT-2401 — Admin Capability Matrix**
- **FRT-2402 — Organization and Tenant Administration**
- **FRT-2403 — User, Role and Permission Administration**
- **FRT-2404 — Business Operations Administration**
- **FRT-2405 — Order, Payment and Refund Administration**
- **FRT-2406 — Inventory and Resource Administration**
- **FRT-2407 — Content and Configuration Administration**
- **FRT-2408 — Notification and Message Administration**
- **FRT-2409 — Workflow and Approval Administration**
- **FRT-2410 — Exception and Manual Intervention Console**
- **FRT-2411 — Data Correction and Reconciliation Console**
- **FRT-2412 — Job and Worker Administration**
- **FRT-2413 — Skill, Pack and Model Administration**
- **FRT-2414 — Artifact, Evidence and Certificate Administration**
- **FRT-2415 — Audit and Security Administration**
- **FRT-2416 — Bulk Operation and Import-Export Generator**
- **FRT-2417 — Admin Search and Advanced Filtering**
- **FRT-2418 — Admin Dashboard and KPI Pack**
- **FRT-2419 — Admin End-to-End Test Generator**

| ID | Skill | 建议实现目录 |
|---|---|---|
| FRT-2400 | `Admin Console Completeness Orchestrator` | `skills/admin-console-completeness-orchestrator/SKILL.md` |
| FRT-2401 | `Admin Capability Matrix` | `skills/admin-capability-matrix/SKILL.md` |
| FRT-2402 | `Organization and Tenant Administration` | `skills/organization-and-tenant-administration/SKILL.md` |
| FRT-2403 | `User, Role and Permission Administration` | `skills/user,-role-and-permission-administration/SKILL.md` |
| FRT-2404 | `Business Operations Administration` | `skills/business-operations-administration/SKILL.md` |
| FRT-2405 | `Order, Payment and Refund Administration` | `skills/order,-payment-and-refund-administration/SKILL.md` |
| FRT-2406 | `Inventory and Resource Administration` | `skills/inventory-and-resource-administration/SKILL.md` |
| FRT-2407 | `Content and Configuration Administration` | `skills/content-and-configuration-administration/SKILL.md` |
| FRT-2408 | `Notification and Message Administration` | `skills/notification-and-message-administration/SKILL.md` |
| FRT-2409 | `Workflow and Approval Administration` | `skills/workflow-and-approval-administration/SKILL.md` |
| FRT-2410 | `Exception and Manual Intervention Console` | `skills/exception-and-manual-intervention-console/SKILL.md` |
| FRT-2411 | `Data Correction and Reconciliation Console` | `skills/data-correction-and-reconciliation-console/SKILL.md` |
| FRT-2412 | `Job and Worker Administration` | `skills/job-and-worker-administration/SKILL.md` |
| FRT-2413 | `Skill, Pack and Model Administration` | `skills/skill,-pack-and-model-administration/SKILL.md` |
| FRT-2414 | `Artifact, Evidence and Certificate Administration` | `skills/artifact,-evidence-and-certificate-administration/SKILL.md` |
| FRT-2415 | `Audit and Security Administration` | `skills/audit-and-security-administration/SKILL.md` |
| FRT-2416 | `Bulk Operation and Import-Export Generator` | `skills/bulk-operation-and-import-export-generator/SKILL.md` |
| FRT-2417 | `Admin Search and Advanced Filtering` | `skills/admin-search-and-advanced-filtering/SKILL.md` |
| FRT-2418 | `Admin Dashboard and KPI Pack` | `skills/admin-dashboard-and-kpi-pack/SKILL.md` |
| FRT-2419 | `Admin End-to-End Test Generator` | `skills/admin-end-to-end-test-generator/SKILL.md` |

## 5. 输入

- G21 Admin Journey与Requirement
- G22 Manual Case、Saga、Reconciliation
- G23 Data Repair、Authority、Audit和Deletion Contract

### 统一请求Envelope

```yaml
apiVersion: frt.openai.dev/v1alpha1
kind: GenerationBatchRequest
metadata:
  projectId: project://frt-platform
  releaseId: release://candidate
  runId: run://g24
spec:
  batch: G24
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

- Admin Capability Matrix
- Admin Object/Command Registry
- Permission Matrix
- Impact Preview Models
- Bulk Operation Plans
- Admin Search/KPI Definitions
- Admin E2E Suite
- Admin Completeness Certificate

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
  skillId: FRT-2400
  executionId: execution://controlled
status:
  state: succeeded | failed | blocked | inconclusive
  findings:
    critical: 0
    high: 0
  evidence:
    - artifact://evidence
  certificate:
    ref: certificate://g24
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
frt g24 plan --project frt-platform --release release://candidate
frt g24 execute --plan .frt/g24/plan.yaml
frt g24 verify --criticality R4,R5
frt g24 findings list --severity critical,high
frt g24 evidence build --release release://candidate
frt g24 certify --release release://candidate --level 5
```

REST/API至少提供：

```text
POST /v1/g24/plans
POST /v1/g24/executions
GET  /v1/g24/executions/{id}
GET  /v1/g24/findings
GET  /v1/g24/evidence/{id}
POST /v1/g24/certificates
POST /v1/g24/certificates/{id}/invalidate
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

统一错误前缀：`FRT-24XX`。

示例：

```text
FRT-24XX-0001  Critical输入或Owner缺失
FRT-24XX-0002  Scope或Tenant边界缺失
FRT-24XX-0003  Evidence无法追踪到Requirement/Artifact
FRT-24XX-0004  Critical Gate失败
FRT-24XX-0005  Certificate Scope与Release不一致
FRT-24XX-0006  Stale Evidence被错误计入通过结果
```

## 14. Release Gates

- [ ] 关键业务异常均有管理入口
- [ ] 高风险管理动作服务端权限、Scope、Reason、Approval和Audit覆盖率=100%
- [ ] 直接修改Critical DB字段路径=0
- [ ] Critical Admin Journey E2E通过
- [ ] Bulk操作均有Snapshot、Preview、Limit、Partial Failure、Audit
- [ ] Search跨Tenant泄漏=0

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
