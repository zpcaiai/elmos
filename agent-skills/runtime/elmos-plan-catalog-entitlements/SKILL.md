---
name: elmos-plan-catalog-entitlements
description: "Implement plan catalog, subscriptions, seats, included credits, feature entitlements, concurrency limits, retention, and tenant-level overrides for Elmos. Use when adding Free/Pro/Builder/Team/Enterprise capabilities or enforcing plan access; not for usage cost calculation or invoice payment settlement."
compatibility: Open Agent Skills; Codex repository skills and Claude Code project skills. Bundled validators require Python 3.10+; implementation may use the target repository's existing stack.
metadata:
  author: elmos
  version: "1.0.0"
  package: elmos-pricing-billing
---

# Plan Catalog and Entitlements

## Objective

将套餐权益、并发限制、成员席位、包含额度、保留期和企业覆盖规则实现为统一授权源。

## Trigger boundaries

**Use this skill when:**

- 新增或调整套餐权益
- 实现团队席位和共享额度
- 控制任务并发、制品保留、模型等级
- 处理升级、降级、试用和宽限期

**Do not use this skill for:**

- 直接估算任务成本
- 直接记账或退款
- 在业务代码中散落硬编码套餐判断

## Required dependencies

`elmos-pricing-product-model`

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

If a required input is absent, inspect the repository and current runtime evidence first. Record unresolved assumptions in the completion report; never invent financial or legal facts.

## Outputs

- 计划目录和权益快照
- 租户订阅与席位状态机
- 统一 entitlement evaluation API
- 升级/降级/试用/宽限测试

## Workflow

1. 盘点所有需要套餐控制的功能、配额、并发和保留策略。
2. 定义 plan、plan_version、feature、entitlement、seat、override 数据模型。
3. 明确 included paid credits 与 promotional credits 的来源和有效期。
4. 实现租户级权益快照，保存其来源版本和计算时间。
5. 实现升级立即生效、降级周期末生效等可配置策略。
6. 实现试用、宽限、暂停、取消和重新激活状态机。
7. 通过单一授权服务执行并发、模型、存储、导出和团队功能检查。
8. 禁止业务服务自行复制套餐常量；提供缓存和失效事件。
9. 为企业合同覆盖提供优先级和审计可见性。
10. 验证时间边界、席位变更和并发竞争。

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
- 每次授权决定必须能回溯到 plan_version、合同覆盖和租户 override。
- 升级/降级不得重复发放包含额度或造成席位越权。

## Required tests

- 订阅状态机测试
- 升级降级边界测试
- 并发配额竞争测试
- 企业覆盖优先级测试
- 权益缓存失效测试

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

- All assigned requirements (EB-03-001, EB-03-002, EB-03-003, EB-03-004, EB-03-005, EB-03-006, EB-03-007, EB-03-008, EB-03-009, EB-03-010) have a five-state classification.
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

- `B06`
- `B07`
- `B08`
