---
name: generation-batch-g27-performance-concurrency-capacity
description: 高并发正确性、性能容量、压力稳定性与安全降级，用于FRT大型前端仓库转换平台的Production Closure层。
version: 1.0.0
batch: G27
risk_model: R0-R5
certificate_level: PC0-PC6
status: implementation-ready
---

# Generation Batch G27：高并发正确性、性能容量、压力稳定性与安全降级

## 1. 使命

从：

> 全系统具备稳定、并行、可重复的回归资格认证

推进到：

> 系统在声明的数据规模、并发用户、任务并发、事件吞吐和长时间压力下保持业务正确、资源稳定、延迟可预测并安全降级

本Batch必须形成可执行Skill、结构化Schema、CLI、管理端入口、测试、Evidence和Certificate，不能只生成设计文档。

## 2. 核心能力

- 业务化Workload Model
- 并发线性化点、Race、Lost Update、Idempotency Under Load
- Load/Stress/Spike/Soak与Recovery
- Queue/Backpressure、Quota、Cache Stampede、DB Hotspot、Pool Limits
- Capacity Forecast、Autoscaling Downstream Constraints
- Graceful Degradation与PC0–PC6认证

## 3. 全局不变量

- 所有R4/R5 Gate采用非补偿式判断，任何Critical缺口均不可被平均分掩盖。
- 模型负责提出候选；编译器、类型系统、状态机、测试、Proof、设备和运行证据决定是否通过。
- Source Repository只读；所有生成、Mutation和修复在隔离Worktree、Sandbox和受控环境中完成。
- 所有正式结果绑定Commit、Artifact、Pack Lock、Policy、Environment和Toolchain Digest。
- 禁止Fake Success、Silent Semantic Loss、空异常处理、UI-only Authorization和直接修改Critical数据库状态。
- 所有Critical Side Effect都必须具备Idempotency、Audit、Reconciliation和明确Authority。
- 任何证据依赖变化后，相关Certificate必须自动变为STALE或RETEST_REQUIRED。

## 4. Skill清单

- **FRT-2700 — Performance and Capacity Orchestrator**
- **FRT-2701 — Workload Model Registry**
- **FRT-2702 — Concurrency Correctness Validator**
- **FRT-2703 — Race and Lost-Update Detector**
- **FRT-2704 — Idempotency Under Load Validator**
- **FRT-2705 — Throughput and Latency Test Generator**
- **FRT-2706 — Load Test Coordinator**
- **FRT-2707 — Stress Test Coordinator**
- **FRT-2708 — Spike Test Coordinator**
- **FRT-2709 — Soak and Memory Leak Test Coordinator**
- **FRT-2710 — Queue and Backpressure Validator**
- **FRT-2711 — Rate Limit and Quota Validator**
- **FRT-2712 — Cache Performance and Stampede Validator**
- **FRT-2713 — Database Hotspot and Query Validator**
- **FRT-2714 — Connection Pool and Resource Validator**
- **FRT-2715 — Capacity Planning Generator**
- **FRT-2716 — Autoscaling Policy Validator**
- **FRT-2717 — Graceful Degradation Validator**
- **FRT-2718 — Performance Budget Governor**
- **FRT-2719 — Performance and Capacity Certificate**

| ID | Skill | 建议实现目录 |
|---|---|---|
| FRT-2700 | `Performance and Capacity Orchestrator` | `skills/performance-and-capacity-orchestrator/SKILL.md` |
| FRT-2701 | `Workload Model Registry` | `skills/workload-model-registry/SKILL.md` |
| FRT-2702 | `Concurrency Correctness Validator` | `skills/concurrency-correctness-validator/SKILL.md` |
| FRT-2703 | `Race and Lost-Update Detector` | `skills/race-and-lost-update-detector/SKILL.md` |
| FRT-2704 | `Idempotency Under Load Validator` | `skills/idempotency-under-load-validator/SKILL.md` |
| FRT-2705 | `Throughput and Latency Test Generator` | `skills/throughput-and-latency-test-generator/SKILL.md` |
| FRT-2706 | `Load Test Coordinator` | `skills/load-test-coordinator/SKILL.md` |
| FRT-2707 | `Stress Test Coordinator` | `skills/stress-test-coordinator/SKILL.md` |
| FRT-2708 | `Spike Test Coordinator` | `skills/spike-test-coordinator/SKILL.md` |
| FRT-2709 | `Soak and Memory Leak Test Coordinator` | `skills/soak-and-memory-leak-test-coordinator/SKILL.md` |
| FRT-2710 | `Queue and Backpressure Validator` | `skills/queue-and-backpressure-validator/SKILL.md` |
| FRT-2711 | `Rate Limit and Quota Validator` | `skills/rate-limit-and-quota-validator/SKILL.md` |
| FRT-2712 | `Cache Performance and Stampede Validator` | `skills/cache-performance-and-stampede-validator/SKILL.md` |
| FRT-2713 | `Database Hotspot and Query Validator` | `skills/database-hotspot-and-query-validator/SKILL.md` |
| FRT-2714 | `Connection Pool and Resource Validator` | `skills/connection-pool-and-resource-validator/SKILL.md` |
| FRT-2715 | `Capacity Planning Generator` | `skills/capacity-planning-generator/SKILL.md` |
| FRT-2716 | `Autoscaling Policy Validator` | `skills/autoscaling-policy-validator/SKILL.md` |
| FRT-2717 | `Graceful Degradation Validator` | `skills/graceful-degradation-validator/SKILL.md` |
| FRT-2718 | `Performance Budget Governor` | `skills/performance-budget-governor/SKILL.md` |
| FRT-2719 | `Performance and Capacity Certificate` | `skills/performance-and-capacity-certificate/SKILL.md` |

## 5. 输入

- G26 Regression Certificate与Test Grid
- 业务Workload、数据规模、Provider Quota、生产拓扑
- API/Queue/DB/Cache/Worker Metrics和Capacity Requirement

### 统一请求Envelope

```yaml
apiVersion: frt.openai.dev/v1alpha1
kind: GenerationBatchRequest
metadata:
  projectId: project://frt-platform
  releaseId: release://candidate
  runId: run://g27
spec:
  batch: G27
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

- Workload Registry
- Concurrency/Race/Idempotency Reports
- Load/Stress/Spike/Soak Reports
- Queue/Cache/DB/Resource Reports
- Capacity and Autoscaling Plan
- Degradation Plan
- Performance Certificate

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
  skillId: FRT-2700
  executionId: execution://controlled
status:
  state: succeeded | failed | blocked | inconclusive
  findings:
    critical: 0
    high: 0
  evidence:
    - artifact://evidence
  certificate:
    ref: certificate://g27
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
frt g27 plan --project frt-platform --release release://candidate
frt g27 execute --plan .frt/g27/plan.yaml
frt g27 verify --criticality R4,R5
frt g27 findings list --severity critical,high
frt g27 evidence build --release release://candidate
frt g27 certify --release release://candidate --level 5
```

REST/API至少提供：

```text
POST /v1/g27/plans
POST /v1/g27/executions
GET  /v1/g27/executions/{id}
GET  /v1/g27/findings
GET  /v1/g27/evidence/{id}
POST /v1/g27/certificates
POST /v1/g27/certificates/{id}/invalidate
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

统一错误前缀：`FRT-27XX`。

示例：

```text
FRT-27XX-0001  Critical输入或Owner缺失
FRT-27XX-0002  Scope或Tenant边界缺失
FRT-27XX-0003  Evidence无法追踪到Requirement/Artifact
FRT-27XX-0004  Critical Gate失败
FRT-27XX-0005  Certificate Scope与Release不一致
FRT-27XX-0006  Stale Evidence被错误计入通过结果
```

## 14. Release Gates

- [ ] Critical Concurrency错误、Lost Update、Duplicate Effective Side Effect=0
- [ ] Target Normal/Peak Load业务正确性和SLO通过
- [ ] Unbounded Critical Queue=0
- [ ] Critical Resource Leak=0
- [ ] DB在目标负载前饱和=0
- [ ] Autoscaling不得压垮下游或终止有效Lease
- [ ] Unsafe Degradation=0

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
