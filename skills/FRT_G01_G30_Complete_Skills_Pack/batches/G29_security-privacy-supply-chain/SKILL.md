---
name: generation-batch-g29-security-privacy-supply-chain
description: 威胁建模、身份权限、供应链、AI安全、隐私合规与持续安全认证，用于FRT大型前端仓库转换平台的Production Closure层。
version: 1.0.0
batch: G29
risk_model: R0-R5
certificate_level: SC0-SC6
status: implementation-ready
---

# Generation Batch G29：威胁建模、身份权限、供应链、AI安全、隐私合规与持续安全认证

## 1. 使命

从：

> 系统在基础设施和依赖故障下仍能安全恢复

推进到：

> 面对恶意用户、越权、注入、供应链、恶意Skill/Pack、Prompt Injection、凭证窃取和协议滥用时可预防、检测、限制、响应和再认证

本Batch必须形成可执行Skill、结构化Schema、CLI、管理端入口、测试、Evidence和Certificate，不能只生成设计文档。

## 2. 核心能力

- Asset、Threat、Trust Boundary、Attack Surface
- Authentication、Authorization、Object/Field Scope、Tenant Isolation
- Session/Token、API、Input、File、SSRF/XSS/Command/Prompt Injection
- Secret/Key、Skill/Pack/Container/Dependency/Model Supply Chain
- SBOM、Vulnerability、SAST、DAST、Fuzz、Abuse
- Privacy、Consent、Deletion、Incident、Pentest、SC0–SC6

## 3. 全局不变量

- 所有R4/R5 Gate采用非补偿式判断，任何Critical缺口均不可被平均分掩盖。
- 模型负责提出候选；编译器、类型系统、状态机、测试、Proof、设备和运行证据决定是否通过。
- Source Repository只读；所有生成、Mutation和修复在隔离Worktree、Sandbox和受控环境中完成。
- 所有正式结果绑定Commit、Artifact、Pack Lock、Policy、Environment和Toolchain Digest。
- 禁止Fake Success、Silent Semantic Loss、空异常处理、UI-only Authorization和直接修改Critical数据库状态。
- 所有Critical Side Effect都必须具备Idempotency、Audit、Reconciliation和明确Authority。
- 任何证据依赖变化后，相关Certificate必须自动变为STALE或RETEST_REQUIRED。

## 4. Skill清单

- **FRT-2900 — Security Assurance Orchestrator**
- **FRT-2901 — Threat Model Generator**
- **FRT-2902 — Attack Surface Inventory**
- **FRT-2903 — Authentication Security Validator**
- **FRT-2904 — Authorization and Policy Validator**
- **FRT-2905 — Tenant Isolation Security Validator**
- **FRT-2906 — Session and Token Security Validator**
- **FRT-2907 — API Security Validator**
- **FRT-2908 — Input Validation and Injection Validator**
- **FRT-2909 — File Upload and Content Security Validator**
- **FRT-2910 — Secrets and Key Management Validator**
- **FRT-2911 — Supply Chain Security Validator**
- **FRT-2912 — SBOM and Vulnerability Governance**
- **FRT-2913 — SAST Coordinator**
- **FRT-2914 — DAST Coordinator**
- **FRT-2915 — Fuzzing and Protocol Abuse Generator**
- **FRT-2916 — Rate Abuse and Bot Protection Validator**
- **FRT-2917 — Privacy and Consent Validator**
- **FRT-2918 — Retention and Deletion Compliance**
- **FRT-2919 — Security Incident Response Generator**
- **FRT-2920 — Penetration Test Evidence Manager**
- **FRT-2921 — Secure Admin Console Validator**
- **FRT-2922 — Security Regression and Recertification**

| ID | Skill | 建议实现目录 |
|---|---|---|
| FRT-2900 | `Security Assurance Orchestrator` | `skills/security-assurance-orchestrator/SKILL.md` |
| FRT-2901 | `Threat Model Generator` | `skills/threat-model-generator/SKILL.md` |
| FRT-2902 | `Attack Surface Inventory` | `skills/attack-surface-inventory/SKILL.md` |
| FRT-2903 | `Authentication Security Validator` | `skills/authentication-security-validator/SKILL.md` |
| FRT-2904 | `Authorization and Policy Validator` | `skills/authorization-and-policy-validator/SKILL.md` |
| FRT-2905 | `Tenant Isolation Security Validator` | `skills/tenant-isolation-security-validator/SKILL.md` |
| FRT-2906 | `Session and Token Security Validator` | `skills/session-and-token-security-validator/SKILL.md` |
| FRT-2907 | `API Security Validator` | `skills/api-security-validator/SKILL.md` |
| FRT-2908 | `Input Validation and Injection Validator` | `skills/input-validation-and-injection-validator/SKILL.md` |
| FRT-2909 | `File Upload and Content Security Validator` | `skills/file-upload-and-content-security-validator/SKILL.md` |
| FRT-2910 | `Secrets and Key Management Validator` | `skills/secrets-and-key-management-validator/SKILL.md` |
| FRT-2911 | `Supply Chain Security Validator` | `skills/supply-chain-security-validator/SKILL.md` |
| FRT-2912 | `SBOM and Vulnerability Governance` | `skills/sbom-and-vulnerability-governance/SKILL.md` |
| FRT-2913 | `SAST Coordinator` | `skills/sast-coordinator/SKILL.md` |
| FRT-2914 | `DAST Coordinator` | `skills/dast-coordinator/SKILL.md` |
| FRT-2915 | `Fuzzing and Protocol Abuse Generator` | `skills/fuzzing-and-protocol-abuse-generator/SKILL.md` |
| FRT-2916 | `Rate Abuse and Bot Protection Validator` | `skills/rate-abuse-and-bot-protection-validator/SKILL.md` |
| FRT-2917 | `Privacy and Consent Validator` | `skills/privacy-and-consent-validator/SKILL.md` |
| FRT-2918 | `Retention and Deletion Compliance` | `skills/retention-and-deletion-compliance/SKILL.md` |
| FRT-2919 | `Security Incident Response Generator` | `skills/security-incident-response-generator/SKILL.md` |
| FRT-2920 | `Penetration Test Evidence Manager` | `skills/penetration-test-evidence-manager/SKILL.md` |
| FRT-2921 | `Secure Admin Console Validator` | `skills/secure-admin-console-validator/SKILL.md` |
| FRT-2922 | `Security Regression and Recertification` | `skills/security-regression-and-recertification/SKILL.md` |

## 5. 输入

- G21–G28资产、数据流、权限、服务、依赖、运行和恢复模型
- Source、Generated Code、Pack/Skill、Container、Dependency、Model和Environment
- Security Policy、Privacy Policy、Pentest Scope和Incident History

### 统一请求Envelope

```yaml
apiVersion: frt.openai.dev/v1alpha1
kind: GenerationBatchRequest
metadata:
  projectId: project://frt-platform
  releaseId: release://candidate
  runId: run://g29
spec:
  batch: G29
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

- Asset/Threat/Attack Surface Registry
- Identity/Authorization/Tenant/API/Injection/File/Secret Reports
- Supply Chain/SBOM/Vulnerability/SAST/DAST/Fuzz Reports
- Privacy and Deletion Evidence
- Incident/Pentest Evidence
- Security Certificate

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
  skillId: FRT-2900
  executionId: execution://controlled
status:
  state: succeeded | failed | blocked | inconclusive
  findings:
    critical: 0
    high: 0
  evidence:
    - artifact://evidence
  certificate:
    ref: certificate://g29
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
frt g29 plan --project frt-platform --release release://candidate
frt g29 execute --plan .frt/g29/plan.yaml
frt g29 verify --criticality R4,R5
frt g29 findings list --severity critical,high
frt g29 evidence build --release release://candidate
frt g29 certify --release release://candidate --level 5
```

REST/API至少提供：

```text
POST /v1/g29/plans
POST /v1/g29/executions
GET  /v1/g29/executions/{id}
GET  /v1/g29/findings
GET  /v1/g29/evidence/{id}
POST /v1/g29/certificates
POST /v1/g29/certificates/{id}/invalidate
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

统一错误前缀：`FRT-29XX`。

示例：

```text
FRT-29XX-0001  Critical输入或Owner缺失
FRT-29XX-0002  Scope或Tenant边界缺失
FRT-29XX-0003  Evidence无法追踪到Requirement/Artifact
FRT-29XX-0004  Critical Gate失败
FRT-29XX-0005  Certificate Scope与Release不一致
FRT-29XX-0006  Stale Evidence被错误计入通过结果
```

## 14. Release Gates

- [ ] Critical Authentication/Authorization绕过=0
- [ ] Cross-Tenant Leak=0
- [ ] Critical Injection/Secret Leak=0
- [ ] Unsigned Production Skill/Pack/Container=0
- [ ] Reachable Critical Vulnerability=0
- [ ] Prompt Injection Capability Escalation=0
- [ ] Critical Privacy违规=0
- [ ] 未解决Critical Pentest Finding=0

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
