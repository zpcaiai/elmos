---
name: elmos-enterprise-byok
description: "Implement enterprise annual contracts, committed spend, postpaid credit limits, private deployment charges, SLA, tenant overrides, cost centers, purchase orders, and BYOK split billing. Use for enterprise pricing, private model gateways, customer-owned API keys, or invoiced accounts; not for storing raw provider keys in the billing database."
metadata:
  source_package: "elmos-pricing-billing-skills"
  source_version: "1.0.0"
  source_skill_sha256: "sha256:b5c051e7d3f3fb1dfb69163e14f6078800e7136e5c7ec4948acb961200e1b276"
  package_namespace: "elmos.pricing-billing.v1"
  package_local_batches: "B33,B34,B35"
  guidance_state: "GUIDANCE_IMPORTED"
  installation_state: "INSTALLED"
  runtime_implementation: "LOCAL_REFERENCE_BOUND"
  runtime_binding: "verification-packs/pricing-billing-local-v1/runtime-binding.json"
  runtime_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

# Enterprise Contracts and BYOK

## Objective

支持企业年度平台费、承诺用量、私有化、SLA 和自带模型账户，并清晰区分模型成本与 Elmos 平台资源费。

## Trigger boundaries

**Use this skill when:**

- 企业年度合同和承诺消费
- BYOK 或私有模型网关
- 后付账、PO、成本中心和部门预算
- 私有部署与 SLA 收费

**Do not use this skill for:**

- 在账单系统保存明文模型密钥
- BYOK 等同于 Elmos 免费
- 绕过租户和数据域隔离

## Required dependencies

`elmos-plan-catalog-entitlements`, `elmos-usage-metering`, `elmos-quote-budget-guard`

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
- MSA/SOW/订单、承诺用量、SLA、部署方式、成本中心、BYOK provider 和数据边界

If a required input is absent, inspect the repository and current runtime evidence first. Record unresolved assumptions in the completion report; never invent financial or legal facts.

## Outputs

- 企业合同、承诺消耗和 true-up 模型
- BYOK 可计费组件与密钥引用
- 信用限额、PO、成本中心和审批
- SLA credit 与私有部署计费

## Workflow

1. 将 MSA/SOW/订单条款映射为结构化 contract version 和覆盖规则。
2. 定义平台费、承诺用量、超额、私有部署、支持和 SLA 费用。
3. 实现 monthly/annual commit burn-down、minimum commit 和 true-up。
4. BYOK 仅保存 secret reference，模型供应商成本由客户承担；Elmos 仍计平台、沙箱、测试、存储等。
5. 支持部门成本中心、预算、审批、项目标签和内部 chargeback 报告。
6. 实现企业后付信用额度、PO 余额、账期和暂停策略。
7. 对私有云/VPC/本地部署记录环境、版本和计量可信边界。
8. 将 SLA 事件与 service credit 规则连接，避免人工随意减免。
9. 合同变更通过新版本和生效日期，不回写历史。
10. 执行合同优先级、BYOK 排除、信用限额和 true-up 场景测试。

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
- BYOK 原始密钥不得进入计费数据库、日志、事件或分析仓库。
- 企业覆盖规则必须绑定合同版本和生效区间，优先级确定且可解释。
- BYOK 只排除客户自付模型成本，不自动排除平台和基础设施费用。

## Required tests

- 承诺用量 burn-down 测试
- BYOK 费率拆分测试
- 合同覆盖优先级测试
- 信用限额并发测试
- SLA credit 测试
- 密钥泄漏静态扫描

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

- All assigned requirements (EB-12-001, EB-12-002, EB-12-003, EB-12-004, EB-12-005, EB-12-006, EB-12-007, EB-12-008, EB-12-009, EB-12-010) have a five-state classification.
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

- `B33`
- `B34`
- `B35`
## Repository integration boundary

This is imported guidance from `elmos-pricing-billing-skills` `1.0.0`. Its source Skill SHA-256 is `b5c051e7d3f3fb1dfb69163e14f6078800e7136e5c7ec4948acb961200e1b276`.
All `B00`–`B53` identifiers are package-local to `elmos.pricing-billing.v1`; they are not Migration Pack, Product Batch, strict-suite, or other repository Batch identifiers.
The user-supplied pinned SHA-256 proves byte identity only; it does not establish authorship, signature, SBOM, or provenance attestation.
Import state is `GUIDANCE_IMPORTED` / `INSTALLED` and the repository-owned bounded handler is `LOCAL_REFERENCE_BOUND`. Exact local execution is reported only by `verification-packs/pricing-billing-local-v1/runtime-binding.json`; importer evidence and external evidence remain `NOT_RUN`, and certification remains `NOT_CERTIFIED` until independently executed evidence proves otherwise.
Package prompts, scripts, examples, prices, policies, schemas, and SQL are reference inputs. They do not grant authority to run bundled code, activate prices, mutate financial state, deploy, or certify the product.
