---
name: generation-batch-g25-functional-usability-accessibility
description: 任务可完成性、全旅程可用性、无障碍、多端适配与感知性能，用于FRT大型前端仓库转换平台的Production Closure层。
version: 1.0.0
batch: G25
risk_model: R0-R5
certificate_level: UX0-UX6
status: implementation-ready
---

# Generation Batch G25：任务可完成性、全旅程可用性、无障碍、多端适配与感知性能

## 1. 使命

从：

> 管理端和业务功能已经完整存在并可治理

推进到：

> 普通用户、开发者、运营和管理员能在真实设备、语言和异常条件下发现、理解、完成并恢复关键任务

本Batch必须形成可执行Skill、结构化Schema、CLI、管理端入口、测试、Evidence和Certificate，不能只生成设计文档。

## 2. 核心能力

- Actor/Goal驱动Task Contract与Completion Oracle
- Loading/Empty/Error/Retry/Unsupported完整状态矩阵
- Form Validation、Data Preservation、Single Flight
- Accessibility、Keyboard、Touch、Gesture、IME
- i18n/RTL、多浏览器、多设备、Responsive、Visual与Perceived Performance
- UX0–UX6 Evidence Certification

## 3. 全局不变量

- 所有R4/R5 Gate采用非补偿式判断，任何Critical缺口均不可被平均分掩盖。
- 模型负责提出候选；编译器、类型系统、状态机、测试、Proof、设备和运行证据决定是否通过。
- Source Repository只读；所有生成、Mutation和修复在隔离Worktree、Sandbox和受控环境中完成。
- 所有正式结果绑定Commit、Artifact、Pack Lock、Policy、Environment和Toolchain Digest。
- 禁止Fake Success、Silent Semantic Loss、空异常处理、UI-only Authorization和直接修改Critical数据库状态。
- 所有Critical Side Effect都必须具备Idempotency、Audit、Reconciliation和明确Authority。
- 任何证据依赖变化后，相关Certificate必须自动变为STALE或RETEST_REQUIRED。

## 4. Skill清单

- **FRT-2500 — Functional Usability Orchestrator**
- **FRT-2501 — Task Completion Test Generator**
- **FRT-2502 — User Journey Usability Validator**
- **FRT-2503 — Admin Journey Usability Validator**
- **FRT-2504 — Form and Validation Usability Validator**
- **FRT-2505 — Loading, Empty, Error and Retry State Validator**
- **FRT-2506 — Navigation Discoverability Validator**
- **FRT-2507 — User Guidance and Recovery Generator**
- **FRT-2508 — Accessibility Acceptance Suite**
- **FRT-2509 — Keyboard, Pointer, Touch and Gesture Matrix**
- **FRT-2510 — IME and International Input Validator**
- **FRT-2511 — Internationalization and RTL Acceptance**
- **FRT-2512 — Browser and Device Compatibility Matrix**
- **FRT-2513 — Responsive and Adaptive Acceptance**
- **FRT-2514 — Visual Consistency Validator**
- **FRT-2515 — Perceived Performance Validator**
- **FRT-2516 — Feature Availability and Unsupported-State UX**
- **FRT-2517 — Usability Evidence Generator**

| ID | Skill | 建议实现目录 |
|---|---|---|
| FRT-2500 | `Functional Usability Orchestrator` | `skills/functional-usability-orchestrator/SKILL.md` |
| FRT-2501 | `Task Completion Test Generator` | `skills/task-completion-test-generator/SKILL.md` |
| FRT-2502 | `User Journey Usability Validator` | `skills/user-journey-usability-validator/SKILL.md` |
| FRT-2503 | `Admin Journey Usability Validator` | `skills/admin-journey-usability-validator/SKILL.md` |
| FRT-2504 | `Form and Validation Usability Validator` | `skills/form-and-validation-usability-validator/SKILL.md` |
| FRT-2505 | `Loading, Empty, Error and Retry State Validator` | `skills/loading,-empty,-error-and-retry-state-validator/SKILL.md` |
| FRT-2506 | `Navigation Discoverability Validator` | `skills/navigation-discoverability-validator/SKILL.md` |
| FRT-2507 | `User Guidance and Recovery Generator` | `skills/user-guidance-and-recovery-generator/SKILL.md` |
| FRT-2508 | `Accessibility Acceptance Suite` | `skills/accessibility-acceptance-suite/SKILL.md` |
| FRT-2509 | `Keyboard, Pointer, Touch and Gesture Matrix` | `skills/keyboard,-pointer,-touch-and-gesture-matrix/SKILL.md` |
| FRT-2510 | `IME and International Input Validator` | `skills/ime-and-international-input-validator/SKILL.md` |
| FRT-2511 | `Internationalization and RTL Acceptance` | `skills/internationalization-and-rtl-acceptance/SKILL.md` |
| FRT-2512 | `Browser and Device Compatibility Matrix` | `skills/browser-and-device-compatibility-matrix/SKILL.md` |
| FRT-2513 | `Responsive and Adaptive Acceptance` | `skills/responsive-and-adaptive-acceptance/SKILL.md` |
| FRT-2514 | `Visual Consistency Validator` | `skills/visual-consistency-validator/SKILL.md` |
| FRT-2515 | `Perceived Performance Validator` | `skills/perceived-performance-validator/SKILL.md` |
| FRT-2516 | `Feature Availability and Unsupported-State UX` | `skills/feature-availability-and-unsupported-state-ux/SKILL.md` |
| FRT-2517 | `Usability Evidence Generator` | `skills/usability-evidence-generator/SKILL.md` |

## 5. 输入

- G21 User/Admin Journey
- G24 Admin Console与Permission Matrix
- 各平台UI、路由、组件、表单、Design Token、Locale、Device Profile

### 统一请求Envelope

```yaml
apiVersion: frt.openai.dev/v1alpha1
kind: GenerationBatchRequest
metadata:
  projectId: project://frt-platform
  releaseId: release://candidate
  runId: run://g25
spec:
  batch: G25
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

- Task Registry
- Task Completion Scenarios
- Usability Journey Results
- Form/UI State Reports
- Accessibility/Input/IME/i18n Reports
- Compatibility/Responsive/Visual/Performance Reports
- Usability Certificate

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
  skillId: FRT-2500
  executionId: execution://controlled
status:
  state: succeeded | failed | blocked | inconclusive
  findings:
    critical: 0
    high: 0
  evidence:
    - artifact://evidence
  certificate:
    ref: certificate://g25
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
frt g25 plan --project frt-platform --release release://candidate
frt g25 execute --plan .frt/g25/plan.yaml
frt g25 verify --criticality R4,R5
frt g25 findings list --severity critical,high
frt g25 evidence build --release release://candidate
frt g25 certify --release release://candidate --level 5
```

REST/API至少提供：

```text
POST /v1/g25/plans
POST /v1/g25/executions
GET  /v1/g25/executions/{id}
GET  /v1/g25/findings
GET  /v1/g25/evidence/{id}
POST /v1/g25/certificates
POST /v1/g25/certificates/{id}/invalidate
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

统一错误前缀：`FRT-25XX`。

示例：

```text
FRT-25XX-0001  Critical输入或Owner缺失
FRT-25XX-0002  Scope或Tenant边界缺失
FRT-25XX-0003  Evidence无法追踪到Requirement/Artifact
FRT-25XX-0004  Critical Gate失败
FRT-25XX-0005  Certificate Scope与Release不一致
FRT-25XX-0006  Stale Evidence被错误计入通过结果
```

## 14. Release Gates

- [ ] Critical Task可发现、可理解、可完成、可恢复=100%
- [ ] Critical Task Dead End=0
- [ ] Critical Accessibility失败=0
- [ ] IME误提交Critical=0
- [ ] 声明支持的Platform/Device Critical失败=0
- [ ] False Success反馈=0

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
