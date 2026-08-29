---
name: elmos-billing-testing-certification
description: "Design and run unit, property, contract, integration, concurrency, chaos, security, financial reconciliation, migration, and end-to-end tests for Elmos billing. Use to verify implementation claims, certify releases, or audit regressions; not for accepting mocked success as production evidence."
compatibility: Open Agent Skills; Codex repository skills and Claude Code project skills. Bundled validators require Python 3.10+; implementation may use the target repository's existing stack.
metadata:
  author: elmos
  version: "1.0.0"
  package: elmos-pricing-billing
---

# Billing Testing and Production Certification

## Objective

以不变量和场景驱动测试证明收费系统在并发、失败、重放、迁移和真实支付条件下正确。

## Trigger boundaries

**Use this skill when:**

- 建立计费测试金字塔
- 验证账本和预算不变量
- 发布前生产认证
- 审计‘已完成’声明

**Do not use this skill for:**

- 只运行 happy path
- 把 mock 通过当作支付/账本生产验证
- 跳过并发、重放或故障注入

## Required dependencies

`elmos-security-compliance`, `elmos-billing-observability-ops`, `elmos-cost-margin-analytics`

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
- 需求追踪、场景矩阵、测试环境、供应商 sandbox、历史事故和迁移数据

If a required input is absent, inspect the repository and current runtime evidence first. Record unresolved assumptions in the completion report; never invent financial or legal facts.

## Outputs

- 分层测试套件和场景目录
- 账务与并发属性测试
- E1-E5 生产认证报告
- 需求级证据和阻断缺陷

## Workflow

1. 从每条 P0/P1 需求生成测试和证据要求。
2. 为账本平衡、非负余额、幂等、cap、退款上限建立 property tests。
3. 为 API、事件、数据库迁移和供应商适配建立 contract tests。
4. 执行 1000+ 并发预留、重复 webhook、迟到用量、网络分区和崩溃恢复。
5. 运行支付 sandbox、真实结算样本和日终对账。
6. 执行跨租户、权限、密钥、重放、注入和欺诈红队测试。
7. 在影子模式比较旧新账单，不允许无解释差异。
8. 按 E1 静态、E2 单元/契约、E3 集成、E4 影子/压测、E5 生产门禁认证。
9. 把失败映射到需求和责任 skill，禁止带 P0 缺陷发布。
10. 生成机器可读和人类可读认证报告。

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
- 所有 P0 需求必须至少有一个自动测试和一个可复核运行证据。
- 存在账本不平、重复收费、跨租户、硬预算突破或不可恢复数据丢失时禁止发布。

## Required tests

- 包自身静态验证
- 需求追踪覆盖率
- 属性与并发测试
- 故障注入与恢复
- 影子账单差分
- E1-E5 认证

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

- All assigned requirements (EB-17-001, EB-17-002, EB-17-003, EB-17-004, EB-17-005, EB-17-006, EB-17-007, EB-17-008, EB-17-009, EB-17-010) have a five-state classification.
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

- `B48`
- `B49`
- `B50`
