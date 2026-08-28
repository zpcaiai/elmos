---
name: elmos-security-compliance
description: "Apply tenant isolation, RBAC/ABAC, separation of duties, encryption, secrets management, audit logging, anti-fraud, webhook security, privacy, retention, export, deletion, and financial-control evidence to Elmos billing. Use for threat modeling, control implementation, compliance gates, or red-team review."
metadata:
  source_package: "elmos-pricing-billing-skills"
  source_version: "1.0.0"
  source_skill_sha256: "sha256:f2ef583299deeea1610976e685ee4fe562c722b9546f3874d304ff8e7f447973"
  package_namespace: "elmos.pricing-billing.v1"
  package_local_batches: "B42,B43,B44"
  guidance_state: "GUIDANCE_IMPORTED"
  installation_state: "INSTALLED"
  runtime_implementation: "LOCAL_REFERENCE_BOUND"
  runtime_binding: "verification-packs/pricing-billing-local-v1/runtime-binding.json"
  runtime_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

# Billing Security and Compliance

## Objective

保护支付、账本、合同、用量和模型密钥，防止越权、重复扣费、账务篡改、欺诈和敏感数据泄露。

## Trigger boundaries

**Use this skill when:**

- 设计账单安全架构
- 权限、审计和职责分离
- 支付和 webhook 防护
- 隐私、保留、导出、删除和合规证据

**Do not use this skill for:**

- 用日志替代数据库约束
- 让超级管理员无审计地改账
- 声称满足具体法域法律而无专业审查

## Required dependencies

`elmos-credit-wallet-ledger`, `elmos-usage-metering`, `elmos-payments-reconciliation`, `elmos-enterprise-byok`

Before implementation, read the shared repository kit installed at `.elmos-billing-kit/`, especially:

- `docs/00-PRODUCT-DECISIONS.md`
- `docs/02-ARCHITECTURE.md`
- `docs/03-DOMAIN-MODEL.md`
- `docs/04-STATE-MACHINES.md`
- `manifests/requirements.traceability.csv`
- `tests/SCENARIO-MATRIX.md`

Then read this skill's [requirements](references/REQUIREMENTS.md) and use the [completion report template](assets/COMPLETION-REPORT.md).

## Inputs

- 目标代码仓库及其 AGENTS.md/CLAUDE.md、构建与测试命令
- 现有租户、账号、任务、模型路由、支付与财务数据模型
- 业务地区、结算币种、税务/发票边界和合规要求
- 当前模型供应商价格、沙箱/存储/网络成本和目标毛利
- 本次实施范围、验收标准、迁移窗口与回滚约束
- 威胁模型、角色矩阵、数据分类、密钥管理、法域和审计要求

If a required input is absent, inspect the repository and current runtime evidence first. Record unresolved assumptions in the completion report; never invent financial or legal facts.

## Outputs

- 威胁模型和控制矩阵
- 租户隔离、最小权限和职责分离实现
- 审计、防欺诈与安全告警
- 合规证据、保留与数据主体流程

## Workflow

1. 识别资产、信任边界、攻击者、滥用路径和高风险财务动作。
2. 为数据库、缓存、队列、对象存储和分析层实施 tenant_id 强制隔离。
3. 定义客户、团队管理员、财务、客服、安全和系统角色的最小权限。
4. 人工调整、退款、价格发布、密钥操作实施职责分离和双人审批。
5. 对传输、静态、备份和字段级敏感数据加密并轮换密钥。
6. 支付和供应商 secret 只存在 secret manager，日志全链路脱敏。
7. 审计日志追加、签名/哈希链、不可变保留并覆盖读写与授权决定。
8. 检测充值欺诈、盗刷、退款滥用、并发套利、机器人和异常项目。
9. 实现隐私访问、导出、删除、保留；财务法定记录采用合法保留例外。
10. 执行越权、注入、重放、竞态、密钥泄漏和审计篡改红队测试。

## Repository implementation rules

1. Preserve the target repository's established language, framework, module layout, migration tool, test runner, error format, telemetry, and deployment conventions unless an approved ADR changes them.
2. Search before editing. Map every requirement to existing modules and classify it as `IMPLEMENTED`, `PARTIAL`, `STUB`, `MISSING`, or `NOT VERIFIED`.
3. Prefer database constraints, transactional boundaries, idempotency, and deterministic scripts over prompt-only correctness.
4. Use expand/migrate/contract for schema changes. A destructive change needs a tested rollback or a documented irreversible approval.
5. Do not mark work complete based only on source inspection. Run the smallest relevant tests, then the repository's required full checks.
6. Keep financial side effects behind explicit command handlers. Read models and projections must not perform billing writes.
7. Keep customer-visible pricing configuration separate from vendor-cost configuration and secrets.
8. Add structured audit fields: `tenant_id`, `actor_id`, `correlation_id`, `causation_id`, `idempotency_key`, `occurred_at`, and version identifiers where applicable.

## Hard invariants

- 金额始终使用整数最小货币单位；执行额度使用整数 micro-credit，禁止浮点记账。
- 钱包账本只追加、不原地改写；任何余额变化必须由平衡的双分录交易产生。
- 所有写操作必须具备租户边界、幂等键、审计主体、关联 ID 和可重放结果。
- 价格、费率、模型策略、税率和合同条款必须版本化；历史结算不得被新版本回写。
- 用户预算达到硬上限时必须先停止可计费执行，再发通知；不得先超扣后解释。
- 任务、支付、退款和项目结算失败必须可恢复；重试不得产生重复收费或重复退款。
- 内部 Token/算力成本与用户外部价格分离；普通用户界面不得把原始 Token 当作唯一计费单位。
- 证据不足时不得把功能标记为 IMPLEMENTED；必须给出源代码、测试、运行记录和提交证据。
- 跨租户查询必须默认拒绝并由数据库或策略层强制，而非依赖调用者自律。
- 任何人不得单独创建并批准自己的高风险财务调整。
- 敏感密钥和完整支付数据不得进入日志、提示词或分析事件。

## Required tests

- 跨租户越权测试
- RBAC/ABAC 属性测试
- 职责分离测试
- secret 扫描
- webhook 重放测试
- 审计篡改检测
- 欺诈规则回放

For every P0 requirement, include at least one automated test plus one runtime or reconciliation evidence item. Mock-only tests are insufficient for payment, ledger, concurrency, migration, or recovery claims.

## Evidence contract

For each completed requirement, record:

```yaml
requirement_id: EB-XX-YYY
status: IMPLEMENTED
source_files:
  - path: path/to/file
    symbols: [ExactSymbol]
migrations: []
tests:
  - command: exact command
    result: PASS
runtime_evidence:
  - artifact: path/to/log-or-report
    assertion: what it proves
commit: git-sha-or-WORKTREE
residual_risks: []
```

Evidence must be reproducible from a clean checkout. Screenshots may supplement but never replace machine-readable logs, database assertions, or test results.

## Definition of Done

- All assigned requirements (EB-15-001, EB-15-002, EB-15-003, EB-15-004, EB-15-005, EB-15-006, EB-15-007, EB-15-008, EB-15-009, EB-15-010) have a five-state classification.
- All P0 requirements are `IMPLEMENTED` with source, symbol, test, runtime, and commit evidence.
- Database migrations apply forward and, where supported, roll back or follow a documented expand/contract path.
- Idempotency, tenant isolation, concurrency, failure recovery, and audit requirements are tested.
- No unresolved critical or high-severity defect remains.
- The completion report is written and the global traceability manifest is updated.
- Package validation is not confused with product implementation: passing `validate.sh` only proves the skill bundle is structurally valid.

## Stop and escalate

Stop the affected financial write path and report the blocker when any of these occurs:

- Ledger entries cannot be balanced or reconciled.
- A write path lacks a stable idempotency scope.
- Tenant isolation cannot be enforced at a trusted layer.
- Price, tax, contract, or refund policy is ambiguous for a production transaction.
- A change would exceed an accepted project cap or alter a frozen scope without a change order.
- Required credentials, provider sandbox, source data, or migration evidence is unavailable.
- Tests reveal duplicate charging, negative unauthorized balance, budget-cap breach, cross-tenant access, or unrecoverable data loss.

Do not bypass the blocker with a manual database edit. Preserve evidence and propose the smallest safe remediation.

## Completion report

Write the final report using `assets/COMPLETION-REPORT.md`. Include:

- Scope and repository baseline hash
- Requirements status table
- Files and symbols changed
- Schema/API/event compatibility impact
- Exact test commands and results
- Runtime/reconciliation evidence
- Security and financial-control review
- Rollout/rollback decision
- Remaining risks and explicit non-claims

## Assigned batches

- `B42`
- `B43`
- `B44`
## Repository integration boundary

This is imported guidance from `elmos-pricing-billing-skills` `1.0.0`. Its source Skill SHA-256 is `f2ef583299deeea1610976e685ee4fe562c722b9546f3874d304ff8e7f447973`.
All `B00`–`B53` identifiers are package-local to `elmos.pricing-billing.v1`; they are not Migration Pack, Product Batch, strict-suite, or other repository Batch identifiers.
The user-supplied pinned SHA-256 proves byte identity only; it does not establish authorship, signature, SBOM, or provenance attestation.
Import state is `GUIDANCE_IMPORTED` / `INSTALLED` and the repository-owned bounded handler is `LOCAL_REFERENCE_BOUND`. Exact local execution is reported only by `verification-packs/pricing-billing-local-v1/runtime-binding.json`; importer evidence and external evidence remain `NOT_RUN`, and certification remains `NOT_CERTIFIED` until independently executed evidence proves otherwise.
Package prompts, scripts, examples, prices, policies, schemas, and SQL are reference inputs. They do not grant authority to run bundled code, activate prices, mutate financial state, deploy, or certify the product.
