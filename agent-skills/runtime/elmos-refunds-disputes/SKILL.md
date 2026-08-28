---
name: elmos-refunds-disputes
description: "Implement policy-driven refunds, partial refunds, credits, chargebacks, disputes, platform-fault compensation, user-fault settlement, manual adjustments, approvals, and evidence. Use when reversing charges or resolving failed-task billing complaints; not for silently deleting usage or ledger history."
metadata:
  source_package: "elmos-pricing-billing-skills"
  source_version: "1.0.0"
  source_skill_sha256: "sha256:ffd065a425c75ecbd0c387c02c0e24ad0d18839e34290883e643b7d40f4f9dd5"
  package_namespace: "elmos.pricing-billing.v1"
  package_local_batches: "B30,B31,B32"
  guidance_state: "GUIDANCE_IMPORTED"
  installation_state: "INSTALLED"
  runtime_implementation: "LOCAL_REFERENCE_BOUND"
  runtime_binding: "verification-packs/pricing-billing-local-v1/runtime-binding.json"
  runtime_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

# Refunds, Adjustments, and Disputes

## Objective

以可解释、可审批、可对账的方式处理平台失败、用户原因、未达验收、重复收费和支付争议。

## Trigger boundaries

**Use this skill when:**

- 任务失败后的退款判定
- 处理重复收费、部分退款、补偿额度
- 支付拒付和争议
- 人工财务调整

**Do not use this skill for:**

- 删除原用量或账本记录
- 无证据直接改余额
- 把所有模型自我修复都额外转嫁给用户

## Required dependencies

`elmos-payments-reconciliation`, `elmos-credit-wallet-ledger`

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
- 任务责任分类、成果证据、原交易、支付渠道限制、项目验收状态

If a required input is absent, inspect the repository and current runtime evidence first. Record unresolved assumptions in the completion report; never invent financial or legal facts.

## Outputs

- 退款资格决策和原因代码
- 全额/部分退款、额度补偿和 chargeback 状态机
- 双人审批与证据包
- 供应商、发票、账本和钱包一致性

## Workflow

1. 分类平台责任、模型可预期修复、用户原因、第三方原因、范围变化和验收失败。
2. 读取原 quote、预算授权、用量、成果、合同和支付交易。
3. 按版本化 policy 计算可退金额、可退额度、不可退已交付价值和手续费。
4. 使用反向账本交易或 credit note，不删除原记录。
5. 支付退款与钱包回退分阶段执行并通过 saga 补偿。
6. 平台故障导致的无价值消耗自动退回或免收。
7. 固定价未达验收按合同进入继续修复、部分退款、专家介入或终止。
8. 大额或人工调整要求双人审批和职责分离。
9. chargeback 冻结相关资金并保留证据与响应期限。
10. 对退款时效、重复退款、失败补偿和对账进行测试。

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
- 退款不得删除或覆盖原交易；必须以关联反向交易表达。
- 同一可退款额度累计不得超过原可退款基数。
- 人工和高额退款必须满足职责分离。

## Required tests

- 全额和部分退款测试
- 重复退款上限测试
- 支付退款失败补偿测试
- chargeback 状态机测试
- 平台责任自动退回测试
- 双人审批测试

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

- All assigned requirements (EB-11-001, EB-11-002, EB-11-003, EB-11-004, EB-11-005, EB-11-006, EB-11-007, EB-11-008, EB-11-009, EB-11-010) have a five-state classification.
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

- `B30`
- `B31`
- `B32`
## Repository integration boundary

This is imported guidance from `elmos-pricing-billing-skills` `1.0.0`. Its source Skill SHA-256 is `ffd065a425c75ecbd0c387c02c0e24ad0d18839e34290883e643b7d40f4f9dd5`.
All `B00`–`B53` identifiers are package-local to `elmos.pricing-billing.v1`; they are not Migration Pack, Product Batch, strict-suite, or other repository Batch identifiers.
The user-supplied pinned SHA-256 proves byte identity only; it does not establish authorship, signature, SBOM, or provenance attestation.
Import state is `GUIDANCE_IMPORTED` / `INSTALLED` and the repository-owned bounded handler is `LOCAL_REFERENCE_BOUND`. Exact local execution is reported only by `verification-packs/pricing-billing-local-v1/runtime-binding.json`; importer evidence and external evidence remain `NOT_RUN`, and certification remains `NOT_CERTIFIED` until independently executed evidence proves otherwise.
Package prompts, scripts, examples, prices, policies, schemas, and SQL are reference inputs. They do not grant authority to run bundled code, activate prices, mutate financial state, deploy, or certify the product.
