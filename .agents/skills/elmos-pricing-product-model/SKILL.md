---
name: elmos-pricing-product-model
description: "Define and implement Elmos's hybrid monetization product model: subscription plus prepaid execution credits, pay-as-used tasks, capped/fixed-price projects, and enterprise annual contracts. Use when creating pricing concepts, customer segments, commercial rules, price-book versioning, or monetization decisions; not for ledger posting or payment-provider integration."
metadata:
  source_package: "elmos-pricing-billing-skills"
  source_version: "1.0.0"
  source_skill_sha256: "sha256:e1cc373b714fa956f2b947642dd20ae031b88579288b18c5e54df79377b641b0"
  package_namespace: "elmos.pricing-billing.v1"
  package_local_batches: "B03,B04,B05"
  guidance_state: "GUIDANCE_IMPORTED"
  installation_state: "INSTALLED"
  runtime_implementation: "LOCAL_REFERENCE_BOUND"
  runtime_binding: "verification-packs/pricing-billing-local-v1/runtime-binding.json"
  runtime_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

# Pricing Product Model

## Objective

把商业模式变成可配置、可版本化、可审计的产品域模型，并明确什么按实际消耗、什么按封顶/固定项目价、什么进入企业合同。

## Trigger boundaries

**Use this skill when:**

- 设计套餐、额度、项目包或企业合同
- 定义托管模型与 BYOK 的收费差异
- 建立价格版本和实验策略
- 评审新业务是否可计费

**Do not use this skill for:**

- 直接修改钱包余额
- 直接调用支付渠道
- 把未经批准的示例价格启用到生产

## Required dependencies

`elmos-billing-orchestrator`

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

- 定价领域模型与决策表
- 价格簿、费率卡、项目包和合同模板
- 范围与变更规则
- 价格审批、发布时间和回滚方案

## Workflow

1. 确认客户分层：试用、个人、重度开发者、团队、企业。
2. 把成本拆为模型、缓存、沙箱、测试、存储、网络、第三方工具与平台编排。
3. 定义外部计价：订阅、执行额度、按量任务、封顶项目、固定项目、企业承诺用量。
4. 定义 managed model 与 BYOK 的可计费组件和排除项。
5. 建立 price book、rate card、plan、project SKU、contract term 的版本关系。
6. 给每个价格版本配置生效区间、审批人、币种、税含义与回滚版本。
7. 把示例价格标记为 draft；未通过财务审批不得进入 production。
8. 为价格实验定义租户分桶、护栏指标和不可追溯修改禁令。
9. 输出对下游账本、报价、订阅、发票和分析的稳定契约。
10. 通过场景评审验证每种任务都能唯一映射到收费路径。

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
- 一个已结算对象只能绑定一个确定的价格簿版本；禁止结算后重新选价。
- 示例价格和生产价格必须物理或状态隔离，并具有独立审批。

## Required tests

- 价格版本时点测试
- 任务到收费路径决策表测试
- BYOK 计费排除测试
- 多币种舍入测试
- 价格回滚与历史不变测试

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

- All assigned requirements (EB-02-001, EB-02-002, EB-02-003, EB-02-004, EB-02-005, EB-02-006, EB-02-007, EB-02-008, EB-02-009, EB-02-010) have a five-state classification.
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

- `B03`
- `B04`
- `B05`
## Repository integration boundary

This is imported guidance from `elmos-pricing-billing-skills` `1.0.0`. Its source Skill SHA-256 is `e1cc373b714fa956f2b947642dd20ae031b88579288b18c5e54df79377b641b0`.
All `B00`–`B53` identifiers are package-local to `elmos.pricing-billing.v1`; they are not Migration Pack, Product Batch, strict-suite, or other repository Batch identifiers.
The user-supplied pinned SHA-256 proves byte identity only; it does not establish authorship, signature, SBOM, or provenance attestation.
Import state is `GUIDANCE_IMPORTED` / `INSTALLED` and the repository-owned bounded handler is `LOCAL_REFERENCE_BOUND`. Exact local execution is reported only by `verification-packs/pricing-billing-local-v1/runtime-binding.json`; importer evidence and external evidence remain `NOT_RUN`, and certification remains `NOT_CERTIFIED` until independently executed evidence proves otherwise.
Package prompts, scripts, examples, prices, policies, schemas, and SQL are reference inputs. They do not grant authority to run bundled code, activate prices, mutate financial state, deploy, or certify the product.
