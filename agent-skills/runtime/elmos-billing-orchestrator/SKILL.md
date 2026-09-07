---
name: elmos-billing-orchestrator
description: "Orchestrate repository-wide implementation of Elmos hybrid billing: subscriptions, prepaid execution credits, capped or fixed-price projects, enterprise contracts, BYOK, metering, ledger, invoicing, controls, and evidence. Use for planning, sequencing, auditing, or completing the full billing program; do not use for a single isolated endpoint when a narrower billing skill applies."
compatibility: Open Agent Skills; Codex repository skills and Claude Code project skills. Bundled validators require Python 3.10+; implementation may use the target repository's existing stack.
metadata:
  author: elmos
  version: "1.0.0"
  package: elmos-pricing-billing
---

# Elmos Billing Orchestrator

## Objective

建立统一实施控制面，把产品决策、数据契约、依赖顺序、迁移、测试、证据和发布门禁组织为可恢复的批次执行计划。

## Trigger boundaries

**Use this skill when:**

- 启动或继续完整收费系统建设
- 审计现有收费实现与需求差距
- 拆分跨服务、跨前后端、跨财务系统任务
- 生成实施状态、交接和证据报告

**Do not use this skill for:**

- 只修改一个价格字段
- 只回答商业模式问题而不实施代码
- 绕过财务、安全或验收门禁的快速上线

## Required dependencies

无；这是根技能。

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

- 仓库现状审计与能力矩阵
- 按依赖排序的批次计划与责任边界
- Requirement→source→symbol→test→runtime evidence→commit 追踪链
- 可恢复状态文件、风险清单、发布与回滚决策

## Workflow

1. 读取仓库根目录指导文件、构建脚本、服务拓扑、数据库迁移和现有计费代码。
2. 运行静态扫描与基线测试，按 IMPLEMENTED/PARTIAL/STUB/MISSING/NOT VERIFIED 分类。
3. 读取本包的 SKILL_INDEX、BATCH_INDEX、需求追踪表和架构决策。
4. 建立依赖 DAG；优先完成账本、计量、报价和预算硬门禁，再做 UI 与分析。
5. 为每个批次创建独立任务状态，记录输入哈希、代码基线、预算、执行节点和恢复点。
6. 每批只处理可审查范围；完成后运行定向测试、全量回归和不变量检查。
7. 把代码位置、符号、迁移、测试结果、运行日志和 commit 写入完成报告。
8. 遇到范围变化时创建 change order，不得静默扩大固定价项目范围。
9. 发布前执行双写/影子、对账、故障注入、预算超限和重复事件测试。
10. 仅在所有 P0 门禁通过、回滚可用且证据完整时标记生产就绪。

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
- 依赖未完成的批次不得被标记为 DONE；并行任务只能写入互不冲突的边界。
- 任何总体完成率都必须由需求级状态聚合，禁止凭主观判断宣称‘全部完成’。

## Required tests

- 依赖 DAG 无环测试
- 干净仓库安装与卸载测试
- 状态中断恢复测试
- 需求追踪完整性测试
- 全流程 smoke 与回滚演练

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

- All assigned requirements (EB-01-001, EB-01-002, EB-01-003, EB-01-004, EB-01-005, EB-01-006, EB-01-007, EB-01-008, EB-01-009, EB-01-010) have a five-state classification.
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

- `B00`
- `B01`
- `B02`
