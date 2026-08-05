---
name: generation-batch-g21-requirements-traceability-product-closure
description: Requirements Traceability 与全系统功能闭环，用于FRT大型前端仓库转换平台的Production Closure层。
version: 1.0.0
batch: G21
risk_model: R0-R5
certificate_level: FC0-FC6
status: implementation-ready
---

# Generation Batch G21：Requirements Traceability 与全系统功能闭环

## 1. 使命

从：

> 每项功能、代码、测试和管理页面分别存在

推进到：

> 每项需求都可追踪到能力、旅程、实现、数据、权限、测试、监控、Runbook、Evidence 与 Release

本Batch必须形成可执行Skill、结构化Schema、CLI、管理端入口、测试、Evidence和Certificate，不能只生成设计文档。

## 2. 核心能力

- 统一 Product Closure Graph
- Requirement、Capability、Journey、Command、API、Data、Permission、Test、Monitoring、Runbook、Certificate 双向追踪
- 孤儿 UI/API/Command/Event/Data Write 检测
- 非补偿式 Feature Completeness Matrix
- Release Scope Freeze 与 FC0–FC6 认证

## 3. 全局不变量

- 所有R4/R5 Gate采用非补偿式判断，任何Critical缺口均不可被平均分掩盖。
- 模型负责提出候选；编译器、类型系统、状态机、测试、Proof、设备和运行证据决定是否通过。
- Source Repository只读；所有生成、Mutation和修复在隔离Worktree、Sandbox和受控环境中完成。
- 所有正式结果绑定Commit、Artifact、Pack Lock、Policy、Environment和Toolchain Digest。
- 禁止Fake Success、Silent Semantic Loss、空异常处理、UI-only Authorization和直接修改Critical数据库状态。
- 所有Critical Side Effect都必须具备Idempotency、Audit、Reconciliation和明确Authority。
- 任何证据依赖变化后，相关Certificate必须自动变为STALE或RETEST_REQUIRED。

## 4. Skill清单

- **FRT-2100 — Product Closure Orchestrator**
- **FRT-2101 — Requirement Registry**
- **FRT-2102 — Business Capability Map Generator**
- **FRT-2103 — Requirement-to-Artifact Traceability**
- **FRT-2104 — Acceptance Criteria Compiler**
- **FRT-2105 — Feature Completeness Matrix**
- **FRT-2106 — Critical User Journey Registry**
- **FRT-2107 — Critical Admin Journey Registry**
- **FRT-2108 — Orphan Feature and Dead Flow Detector**
- **FRT-2109 — Missing Implementation Link Detector**
- **FRT-2110 — Release Scope Closure Manager**
- **FRT-2111 — Functional Coverage Certification**

| ID | Skill | 建议实现目录 |
|---|---|---|
| FRT-2100 | `Product Closure Orchestrator` | `skills/product-closure-orchestrator/SKILL.md` |
| FRT-2101 | `Requirement Registry` | `skills/requirement-registry/SKILL.md` |
| FRT-2102 | `Business Capability Map Generator` | `skills/business-capability-map-generator/SKILL.md` |
| FRT-2103 | `Requirement-to-Artifact Traceability` | `skills/requirement-to-artifact-traceability/SKILL.md` |
| FRT-2104 | `Acceptance Criteria Compiler` | `skills/acceptance-criteria-compiler/SKILL.md` |
| FRT-2105 | `Feature Completeness Matrix` | `skills/feature-completeness-matrix/SKILL.md` |
| FRT-2106 | `Critical User Journey Registry` | `skills/critical-user-journey-registry/SKILL.md` |
| FRT-2107 | `Critical Admin Journey Registry` | `skills/critical-admin-journey-registry/SKILL.md` |
| FRT-2108 | `Orphan Feature and Dead Flow Detector` | `skills/orphan-feature-and-dead-flow-detector/SKILL.md` |
| FRT-2109 | `Missing Implementation Link Detector` | `skills/missing-implementation-link-detector/SKILL.md` |
| FRT-2110 | `Release Scope Closure Manager` | `skills/release-scope-closure-manager/SKILL.md` |
| FRT-2111 | `Functional Coverage Certification` | `skills/functional-coverage-certification/SKILL.md` |

## 5. 输入

- PRD、用户故事、ADR、API Contract、安全和运营政策
- G1–G20 生成的 Semantic IR、代码、测试、Proof 与 Artifact
- Source/Target Repository、管理端和发布清单

### 统一请求Envelope

```yaml
apiVersion: frt.openai.dev/v1alpha1
kind: GenerationBatchRequest
metadata:
  projectId: project://frt-platform
  releaseId: release://candidate
  runId: run://g21
spec:
  batch: G21
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

- Requirement Registry
- Business Capability Map
- User/Admin Journey Registry
- Traceability Graph
- Acceptance Criteria Set
- Feature Completeness Matrix
- Orphan/Dead Flow Findings
- Functional Coverage Certificate

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
  skillId: FRT-2100
  executionId: execution://controlled
status:
  state: succeeded | failed | blocked | inconclusive
  findings:
    critical: 0
    high: 0
  evidence:
    - artifact://evidence
  certificate:
    ref: certificate://g21
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
frt g21 plan --project frt-platform --release release://candidate
frt g21 execute --plan .frt/g21/plan.yaml
frt g21 verify --criticality R4,R5
frt g21 findings list --severity critical,high
frt g21 evidence build --release release://candidate
frt g21 certify --release release://candidate --level 5
```

REST/API至少提供：

```text
POST /v1/g21/plans
POST /v1/g21/executions
GET  /v1/g21/executions/{id}
GET  /v1/g21/findings
GET  /v1/g21/evidence/{id}
POST /v1/g21/certificates
POST /v1/g21/certificates/{id}/invalidate
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

统一错误前缀：`FRT-21XX`。

示例：

```text
FRT-21XX-0001  Critical输入或Owner缺失
FRT-21XX-0002  Scope或Tenant边界缺失
FRT-21XX-0003  Evidence无法追踪到Requirement/Artifact
FRT-21XX-0004  Critical Gate失败
FRT-21XX-0005  Certificate Scope与Release不一致
FRT-21XX-0006  Stale Evidence被错误计入通过结果
```

## 14. Release Gates

- [ ] 关键需求登记率与Owner覆盖率=100%
- [ ] 关键需求到实现、数据、权限、测试、监控、Runbook和Release的追踪率=100%
- [ ] 关键User/Admin Journey无死路
- [ ] 无隐藏Production副作用入口
- [ ] 无Critical orphan API、UI action、data write
- [ ] 所有Critical Feature达到声明FC等级

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
