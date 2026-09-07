---
name: generation-batch-g30-production-readiness-sre-closure
description: Production Readiness、SRE运营、渐进发布、自动回滚与持续认证总收口，用于FRT大型前端仓库转换平台的Production Closure层。
version: 1.0.0
batch: G30
risk_model: R0-R5
certificate_level: PR0-PR6
status: implementation-ready
---

# Generation Batch G30：Production Readiness、SRE运营、渐进发布、自动回滚与持续认证总收口

## 1. 使命

从：

> 需求、业务、数据、管理、可用性、测试、性能、韧性和安全均分别通过认证

推进到：

> 所有证书、运行指标、发布、告警、值班、回滚、Cutover、Support和持续再认证汇聚成唯一Production Release Gate

本Batch必须形成可执行Skill、结构化Schema、CLI、管理端入口、测试、Evidence和Certificate，不能只生成设计文档。

## 2. 核心能力

- 九类Certificate聚合与唯一Production Authority
- Service Catalog、Owner、Tier、Dependency
- SLI/SLO、Business SLI、Error Budget和Burn Rate
- Metrics/Logs/Traces/Audit/Synthetic、Alert、Runbook、On-Call、Incident
- Release Train、Canary、Feature Flag、Rollback
- Data Cutover、Legacy Coexistence、Customer Support
- Continuous Verification/Security/Performance、Post-Release、Incident Learning、PR0–PR6

## 3. 全局不变量

- 所有R4/R5 Gate采用非补偿式判断，任何Critical缺口均不可被平均分掩盖。
- 模型负责提出候选；编译器、类型系统、状态机、测试、Proof、设备和运行证据决定是否通过。
- Source Repository只读；所有生成、Mutation和修复在隔离Worktree、Sandbox和受控环境中完成。
- 所有正式结果绑定Commit、Artifact、Pack Lock、Policy、Environment和Toolchain Digest。
- 禁止Fake Success、Silent Semantic Loss、空异常处理、UI-only Authorization和直接修改Critical数据库状态。
- 所有Critical Side Effect都必须具备Idempotency、Audit、Reconciliation和明确Authority。
- 任何证据依赖变化后，相关Certificate必须自动变为STALE或RETEST_REQUIRED。

## 4. Skill清单

- **FRT-3000 — Production Readiness Orchestrator**
- **FRT-3001 — Production Readiness Checklist Compiler**
- **FRT-3002 — Service Catalog Generator**
- **FRT-3003 — SLI and SLO Generator**
- **FRT-3004 — Business SLI Generator**
- **FRT-3005 — Observability Coverage Validator**
- **FRT-3006 — Alert Quality Validator**
- **FRT-3007 — Runbook Completeness Validator**
- **FRT-3008 — On-Call Readiness Generator**
- **FRT-3009 — Incident Management Workflow**
- **FRT-3010 — Release Train Orchestrator**
- **FRT-3011 — Canary and Progressive Delivery**
- **FRT-3012 — Feature Flag Safety Validator**
- **FRT-3013 — Automated Rollback Generator**
- **FRT-3014 — Database and Data Cutover Manager**
- **FRT-3015 — Legacy Coexistence and Cutover Validator**
- **FRT-3016 — Customer Support Readiness**
- **FRT-3017 — Operational Dashboard Generator**
- **FRT-3018 — Continuous Verification Scheduler**
- **FRT-3019 — Continuous Security Recertification**
- **FRT-3020 — Continuous Performance Recertification**
- **FRT-3021 — Production Closure Certificate**
- **FRT-3022 — Post-Release Verification**
- **FRT-3023 — Production Incident Learning Pack**

| ID | Skill | 建议实现目录 |
|---|---|---|
| FRT-3000 | `Production Readiness Orchestrator` | `skills/production-readiness-orchestrator/SKILL.md` |
| FRT-3001 | `Production Readiness Checklist Compiler` | `skills/production-readiness-checklist-compiler/SKILL.md` |
| FRT-3002 | `Service Catalog Generator` | `skills/service-catalog-generator/SKILL.md` |
| FRT-3003 | `SLI and SLO Generator` | `skills/sli-and-slo-generator/SKILL.md` |
| FRT-3004 | `Business SLI Generator` | `skills/business-sli-generator/SKILL.md` |
| FRT-3005 | `Observability Coverage Validator` | `skills/observability-coverage-validator/SKILL.md` |
| FRT-3006 | `Alert Quality Validator` | `skills/alert-quality-validator/SKILL.md` |
| FRT-3007 | `Runbook Completeness Validator` | `skills/runbook-completeness-validator/SKILL.md` |
| FRT-3008 | `On-Call Readiness Generator` | `skills/on-call-readiness-generator/SKILL.md` |
| FRT-3009 | `Incident Management Workflow` | `skills/incident-management-workflow/SKILL.md` |
| FRT-3010 | `Release Train Orchestrator` | `skills/release-train-orchestrator/SKILL.md` |
| FRT-3011 | `Canary and Progressive Delivery` | `skills/canary-and-progressive-delivery/SKILL.md` |
| FRT-3012 | `Feature Flag Safety Validator` | `skills/feature-flag-safety-validator/SKILL.md` |
| FRT-3013 | `Automated Rollback Generator` | `skills/automated-rollback-generator/SKILL.md` |
| FRT-3014 | `Database and Data Cutover Manager` | `skills/database-and-data-cutover-manager/SKILL.md` |
| FRT-3015 | `Legacy Coexistence and Cutover Validator` | `skills/legacy-coexistence-and-cutover-validator/SKILL.md` |
| FRT-3016 | `Customer Support Readiness` | `skills/customer-support-readiness/SKILL.md` |
| FRT-3017 | `Operational Dashboard Generator` | `skills/operational-dashboard-generator/SKILL.md` |
| FRT-3018 | `Continuous Verification Scheduler` | `skills/continuous-verification-scheduler/SKILL.md` |
| FRT-3019 | `Continuous Security Recertification` | `skills/continuous-security-recertification/SKILL.md` |
| FRT-3020 | `Continuous Performance Recertification` | `skills/continuous-performance-recertification/SKILL.md` |
| FRT-3021 | `Production Closure Certificate` | `skills/production-closure-certificate/SKILL.md` |
| FRT-3022 | `Post-Release Verification` | `skills/post-release-verification/SKILL.md` |
| FRT-3023 | `Production Incident Learning Pack` | `skills/production-incident-learning-pack/SKILL.md` |

## 5. 输入

- G21–G29所有Certificate和Evidence
- Production Environment、Service/Deployment/Config/Policy/Flag Manifest
- On-Call、Runbook、Support、Release和Cutover计划

### 统一请求Envelope

```yaml
apiVersion: frt.openai.dev/v1alpha1
kind: GenerationBatchRequest
metadata:
  projectId: project://frt-platform
  releaseId: release://candidate
  runId: run://g30
spec:
  batch: G30
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

- Production Readiness Checklist
- Service Catalog
- SLI/SLO/Business SLI Registry
- Observability/Alert/Runbook/On-Call Reports
- Release/Canary/Flag/Rollback/Cutover Plans
- Support and Continuous Certification Plans
- Production Closure Certificate

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
  skillId: FRT-3000
  executionId: execution://controlled
status:
  state: succeeded | failed | blocked | inconclusive
  findings:
    critical: 0
    high: 0
  evidence:
    - artifact://evidence
  certificate:
    ref: certificate://g30
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
frt g30 plan --project frt-platform --release release://candidate
frt g30 execute --plan .frt/g30/plan.yaml
frt g30 verify --criticality R4,R5
frt g30 findings list --severity critical,high
frt g30 evidence build --release release://candidate
frt g30 certify --release release://candidate --level 5
```

REST/API至少提供：

```text
POST /v1/g30/plans
POST /v1/g30/executions
GET  /v1/g30/executions/{id}
GET  /v1/g30/findings
GET  /v1/g30/evidence/{id}
POST /v1/g30/certificates
POST /v1/g30/certificates/{id}/invalidate
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

统一错误前缀：`FRT-30XX`。

示例：

```text
FRT-30XX-0001  Critical输入或Owner缺失
FRT-30XX-0002  Scope或Tenant边界缺失
FRT-30XX-0003  Evidence无法追踪到Requirement/Artifact
FRT-30XX-0004  Critical Gate失败
FRT-30XX-0005  Certificate Scope与Release不一致
FRT-30XX-0006  Stale Evidence被错误计入通过结果
```

## 14. Release Gates

- [ ] 九类Critical前置Certificate全部有效且Scope一致
- [ ] Critical Service Owner、SLI/SLO、Alert、Runbook、On-Call覆盖率=100%
- [ ] Canary必须有Technical/Business/Data/Security Gate和Auto Halt
- [ ] Critical Rollback与Cutover演练通过
- [ ] Support不得依赖数据库直连
- [ ] Post-Release Critical Journey/Data/Security验证通过
- [ ] 唯一Production Release Authority且PR5通过

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
