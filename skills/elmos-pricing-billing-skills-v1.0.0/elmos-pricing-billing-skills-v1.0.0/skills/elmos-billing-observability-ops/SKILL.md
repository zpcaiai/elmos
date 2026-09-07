---
name: elmos-billing-observability-ops
description: "Implement metrics, logs, traces, SLOs, alerts, runbooks, replay, reconciliation operations, disaster recovery, and incident controls for Elmos billing. Use for production readiness, anomaly response, stuck settlement, missing usage, budget drift, or financial incidents; not for masking invariant violations with retries."
compatibility: Open Agent Skills; Codex repository skills and Claude Code project skills. Bundled validators require Python 3.10+; implementation may use the target repository's existing stack.
metadata:
  author: elmos
  version: "1.0.0"
  package: elmos-pricing-billing
---

# Billing Observability and Operations

## Objective

确保长任务、用量、预算、账本、支付和项目结算可观测、可恢复、可对账，并能在财务事故中安全止损。

## Trigger boundaries

**Use this skill when:**

- 建立计费监控和 SLO
- 处理卡住任务或结算
- 恢复队列、投影和对账
- 演练灾备与财务事故

**Do not use this skill for:**

- 无限重试财务写操作
- 只看应用日志判断账务正确
- 未验证账本不变量就解除事故

## Required dependencies

`elmos-credit-wallet-ledger`, `elmos-usage-metering`, `elmos-quote-budget-guard`, `elmos-payments-reconciliation`

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
- 拓扑、SLO、告警渠道、RTO/RPO、运行手册、值班和事故分级

If a required input is absent, inspect the repository and current runtime evidence first. Record unresolved assumptions in the completion report; never invent financial or legal facts.

## Outputs

- 端到端 trace 与财务关联 ID
- SLO、仪表盘、告警和异常队列
- 重放、投影重建、对账和灾备 runbook
- 事故冻结、恢复和事后复盘证据

## Workflow

1. 定义 quote、reserve、run、usage、capture、invoice、payment、refund 的关联 ID。
2. 采集吞吐、延迟、失败、重复、迟到、预算漂移、账本不平和对账差异指标。
3. 建立 SLO：报价、任务授权、用量延迟、支付处理、退款和日终对账。
4. 对重复扣费、负余额、账本不平、硬预算突破设置零容忍告警。
5. 为卡住 saga、死信、缺失 webhook、迟到用量和投影漂移建立工作队列。
6. 实现只读事故模式、支付/扣费 kill switch 和受控恢复。
7. 编写重放、投影重建、重新对账、回滚价格和恢复任务 runbook。
8. 备份不可变账本、合同、发票和审计；验证 RPO/RTO。
9. 每次恢复先在影子环境重演并检查不变量。
10. 演练供应商中断、数据库故障、队列重复、网络分区和区域灾难。

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
- 严重财务不变量告警必须能够自动阻止进一步风险扩大。
- 恢复和重放前后都必须运行账本平衡、幂等和对账检查。

## Required tests

- 端到端 trace 测试
- kill switch 演练
- 死信重放测试
- 投影重建测试
- 数据库恢复和 RPO/RTO 演练
- 供应商中断故障注入

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

- All assigned requirements (EB-16-001, EB-16-002, EB-16-003, EB-16-004, EB-16-005, EB-16-006, EB-16-007, EB-16-008, EB-16-009, EB-16-010) have a five-state classification.
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

- `B45`
- `B46`
- `B47`
