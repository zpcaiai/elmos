---
name: elmos-project-pricing-contracts
description: "Implement discovery quotes, capped-price and fixed-price project contracts, scope freeze, milestones, acceptance criteria, included revisions, change orders, risk reserves, and project settlement. Use for repository conversions, modernization, full-project generation, migrations, or standardized project SKUs; not for open-ended exploratory tasks."
compatibility: Open Agent Skills; Codex repository skills and Claude Code project skills. Bundled validators require Python 3.10+; implementation may use the target repository's existing stack.
metadata:
  author: elmos
  version: "1.0.0"
  package: elmos-pricing-billing
---

# Capped and Fixed-Price Project Contracts

## Objective

把中大型、范围明确的工作转为可控的封顶价或固定价项目，同时通过范围保护、验收和变更单避免无限修改。

## Trigger boundaries

**Use this skill when:**

- 完整项目生成或老系统翻新
- 跨语言转换、框架升级、数据库迁移
- 标准化项目包报价
- 处理范围变更、里程碑验收和项目结算

**Do not use this skill for:**

- 需求持续变化的探索任务
- 没有代码基线和验收测试就承诺固定价
- 把系统生成过代码等同于完成交付

## Required dependencies

`elmos-quote-budget-guard`

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
- 源仓库哈希、冻结需求版本、验收测试、包含修改轮数、外部依赖责任边界

If a required input is absent, inspect the repository and current runtime evidence first. Record unresolved assumptions in the completion report; never invent financial or legal facts.

## Outputs

- discovery、capped、fixed 合同状态机
- scope baseline、里程碑、验收与 change order
- 风险准备金和项目 P80/P90 定价
- 完成、部分退款或终止结算

## Workflow

1. 先执行低成本 discovery，生成仓库基线、风险和范围建议。
2. 冻结输入仓库 commit/hash、需求版本、功能清单和环境依赖。
3. 选择 capped price 或 fixed price；固定价仅用于高标准化、低方差任务。
4. 按 P80/P90 历史成本、目标毛利、验收成本、支持成本和风险准备金定价。
5. 定义里程碑、验收测试、性能/安全指标、包含修改轮数和排除项。
6. 任务执行期间监测范围漂移和成本耗尽风险。
7. 发现新增需求时暂停相关分支并生成 change order 候选。
8. 里程碑验收使用机器测试和人工批准的组合，保存证据。
9. 未达固定价验收时进入继续修复、部分退款、专家介入或合同终止路径。
10. 项目结算关联实际成本、确认收入、递延收入和毛利复盘。

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
- 固定或封顶项目必须绑定不可变 scope baseline 和源代码基线。
- 范围变化未经变更单批准不得消耗原合同的无限资源。
- 交付完成必须以验收标准和证据为准，不得以生成文件数量为准。

## Required tests

- 范围哈希变化测试
- change order 触发测试
- 里程碑验收状态机测试
- 封顶价不超扣测试
- 固定价失败处理测试
- 收入确认事件测试

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

- All assigned requirements (EB-08-001, EB-08-002, EB-08-003, EB-08-004, EB-08-005, EB-08-006, EB-08-007, EB-08-008, EB-08-009, EB-08-010) have a five-state classification.
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

- `B21`
- `B22`
- `B23`
