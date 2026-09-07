---
name: elmos-billing-admin-ux
description: "Implement customer quote cards, wallet, invoices, usage detail, project contracts, budget controls, team cost centers, and admin operations with clear explanations and audit-safe actions. Use for billing UI/API journeys and operator consoles; not for embedding financial rules only in the frontend."
compatibility: Open Agent Skills; Codex repository skills and Claude Code project skills. Bundled validators require Python 3.10+; implementation may use the target repository's existing stack.
metadata:
  author: elmos
  version: "1.0.0"
  package: elmos-pricing-billing
---

# Billing Customer and Admin UX

## Objective

把复杂计费规则转成用户可理解、管理员可操作且不绕过后端门禁的产品体验。

## Trigger boundaries

**Use this skill when:**

- 实现报价卡和费用进度条
- 展示钱包、账单、用量和退款
- 团队预算与成本中心
- 运营后台的价格、调整、对账和争议工作台

**Do not use this skill for:**

- 只在前端校验预算
- 向普通用户暴露原始内部成本或密钥
- 无二次确认执行高风险财务动作

## Required dependencies

`elmos-quote-budget-guard`, `elmos-subscription-invoicing`, `elmos-refunds-disputes`, `elmos-enterprise-byok`

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
- 设计系统、角色权限、可访问性标准、审计字段和用户语言/币种

If a required input is absent, inspect the repository and current runtime evidence first. Record unresolved assumptions in the completion report; never invent financial or legal facts.

## Outputs

- 客户账单中心和报价/运行中控制体验
- 团队预算、成本中心和合同页面
- 管理员工作台与审批流
- 错误、空态、延迟和无障碍规范

## Workflow

1. 梳理客户、团队管理员、财务、客服、安全和超级管理员旅程。
2. 报价卡显示扫描范围、模式、费用区间、cap、ETA、人工时间对比、测试和验收。
3. 任务中显示已用/预留/预计剩余、阈值和暂停原因。
4. 提供追加预算、降级、缩小范围、仅修阻断项和停止导出动作。
5. 钱包区分付费、赠送、冻结、已用、退款和到期。
6. 发票和用量支持从汇总下钻到任务、运行、节点和资源。
7. 项目页展示范围基线、里程碑、验收、变更单和 cap。
8. 管理员高风险动作要求原因、预览、二次确认、审批和审计。
9. 所有财务规则由后端返回，前端只负责呈现和发起命令。
10. 验证移动端、键盘、屏幕阅读器、长数字、多币种和延迟状态。

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
- UI 不得成为预算、权限、价格或余额正确性的唯一执行点。
- 任何管理员金额调整都必须展示交易预览并由后端重新校验。

## Required tests

- 关键旅程 E2E
- 无障碍测试
- 多币种与大数显示测试
- 过期报价 UI 测试
- 管理员审批测试
- 断线重连与延迟事件测试

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

- All assigned requirements (EB-14-001, EB-14-002, EB-14-003, EB-14-004, EB-14-005, EB-14-006, EB-14-007, EB-14-008, EB-14-009, EB-14-010) have a five-state classification.
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

- `B39`
- `B40`
- `B41`
