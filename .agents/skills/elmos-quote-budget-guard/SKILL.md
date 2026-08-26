---
name: elmos-quote-budget-guard
description: "Create task quote cards, authorize credit holds, enforce soft/hard budget thresholds, pause before overspend, support top-ups and low-cost replanning, and settle actual usage. Use for pre-run quotations and in-run cost controls; not for defining the base price book itself."
metadata:
  source_package: "elmos-pricing-billing-skills"
  source_version: "1.0.0"
  source_skill_sha256: "sha256:d48e5f20fbed5ebbcf6d1871d4291e71f12341c1f064b48649826a69dc37b411"
  package_namespace: "elmos.pricing-billing.v1"
  package_local_batches: "B18,B19,B20"
  guidance_state: "GUIDANCE_IMPORTED"
  installation_state: "INSTALLED"
  runtime_implementation: "LOCAL_REFERENCE_BOUND"
  runtime_binding: "verification-packs/pricing-billing-local-v1/runtime-binding.json"
  runtime_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

# Quote and Budget Guard

## Objective

让用户在执行前知道预计费用、最大预算和自主运行时间，并在运行中获得不可绕过的预算保护。

## Trigger boundaries

**Use this skill when:**

- 生成任务报价卡
- 冻结最大预算
- 实现 50/80/95% 阈值提醒
- 暂停、追加预算、降级模型或按实际结算

**Do not use this skill for:**

- 允许任务先超预算再补扣
- 将软提醒当作硬门禁
- 在报价过期后继续用旧价格启动

## Required dependencies

`elmos-task-cost-estimation`, `elmos-credit-wallet-ledger`

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
- 估算快照、价格簿版本、用户模型模式、预算偏好和任务验收范围

If a required input is absent, inspect the repository and current runtime evidence first. Record unresolved assumptions in the completion report; never invent financial or legal facts.

## Outputs

- 版本化 quote、授权 hold 和预算策略
- 报价卡 API/UI contract
- 阈值通知、暂停、追加与重规划流程
- 完成/失败/取消的结算证据

## Workflow

1. 基于不可变估算快照和价格簿生成 quote，包含 min/max、P90 cap、ETA、过期时间。
2. 展示扫描范围、模型模式、测试范围、验收标准和费用构成。
3. 用户接受后创建预算授权并原子 reserve 最大预算或企业授信额度。
4. 任务节点在产生可计费用量前检查剩余预算和预测剩余成本。
5. 在 50%、80%、95% 触发可配置通知和模型降级建议。
6. 硬上限前先停止后续可计费节点并进入 PAUSED_BUDGET。
7. 提供追加预算、降低质量模式、缩小范围、只修阻断项或停止导出。
8. 任务完成后按实际用量 capture 并 release 未使用预留。
9. 失败/取消时按责任和已获得成果规则结算，保留理由代码。
10. 对报价误差、暂停次数和用户选择建立反馈闭环。

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
- 任何任务开始前必须存在有效 quote 和成功的预算授权。
- 硬预算检查必须位于资源调用之前的执行控制面，UI 检查不能替代。
- 实际扣款不得超过用户已接受的硬上限，除非存在明确追加授权。

## Required tests

- 报价过期测试
- 并发预算消费测试
- 硬上限前暂停测试
- 追加预算幂等测试
- 部分捕获释放测试
- 断线重连状态恢复测试

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

- All assigned requirements (EB-07-001, EB-07-002, EB-07-003, EB-07-004, EB-07-005, EB-07-006, EB-07-007, EB-07-008, EB-07-009, EB-07-010) have a five-state classification.
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

- `B18`
- `B19`
- `B20`
## Repository integration boundary

This is imported guidance from `elmos-pricing-billing-skills` `1.0.0`. Its source Skill SHA-256 is `d48e5f20fbed5ebbcf6d1871d4291e71f12341c1f064b48649826a69dc37b411`.
All `B00`–`B53` identifiers are package-local to `elmos.pricing-billing.v1`; they are not Migration Pack, Product Batch, strict-suite, or other repository Batch identifiers.
The user-supplied pinned SHA-256 proves byte identity only; it does not establish authorship, signature, SBOM, or provenance attestation.
Import state is `GUIDANCE_IMPORTED` / `INSTALLED` and the repository-owned bounded handler is `LOCAL_REFERENCE_BOUND`. Exact local execution is reported only by `verification-packs/pricing-billing-local-v1/runtime-binding.json`; importer evidence and external evidence remain `NOT_RUN`, and certification remains `NOT_CERTIFIED` until independently executed evidence proves otherwise.
Package prompts, scripts, examples, prices, policies, schemas, and SQL are reference inputs. They do not grant authority to run bundled code, activate prices, mutate financial state, deploy, or certify the product.
