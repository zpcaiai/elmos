## Batch 29 route skills

Use `$b29-route-factory` for new directed language routes. Use the route-specific certification skill when the source and target are known. A route may be declared certified only through `$b29-route-certification-gate`; unsupported or unknown semantics must remain explicit and must never be hidden with permissive types or weakened tests.

# Batch 30 framework skills

For framework migration, upgrade, modernization, target-profile, or coexistence work, use the applicable `$b30-*` skill. Treat every pack as directional and version-specific. Extract active source behavior into FCM before target generation, use real source/target builds and startup, preserve security/data/transaction/test integrity, and run the Batch 30 gate before raising support status.

# Batch 31 database and data-platform skills

For database-engine, SQL, routine, ETL/ELT, warehouse, data-quality, lineage, reconciliation, or cutover work, use the applicable `$b31-*` skill. Treat every pack as directional and exact. Use real source and target engines, typed canonical DB IR, safe disposable data, detail-level reconciliation, independent holdout workloads, and the Batch 31 gate. Never certify regex-only SQL conversion, lossy money/type mappings, weakened constraints/security, or production writes without an approved workflow.


# Batch 32 client modernization skills

- Repository-scoped Codex skills live in `.agents/skills/b32-*/SKILL.md`.
- Invoke the smallest relevant skill explicitly with `$b32-...` while developing or debugging.
- Every client pack is exact, directional, versioned, journey-scoped, browser/device-scoped, and evidence-backed.
- Transform through the typed UI Interaction IR and target profile; do not implement migration as regex or template replacement.
- Use real source and target builds and real browser/device execution.
- Preserve route, state, form, identity/permission, rendering, accessibility, i18n, and visual contracts.
- Do not update visual baselines, weaken tests, add `any`, disable accessibility checks, or broaden permissions merely to make a gate pass.
- Keep development, negative, holdout, and representative workload corpora independent.
- Only `scripts/batch32/run_client_gate.py` may determine certification readiness.


# Batch 33 Cloud, IaC, and DevOps modernization skills

- Repository-scoped Codex skills live in `.agents/skills/b33-*/SKILL.md`.
- Invoke the smallest relevant skill explicitly with `$b33-...` while implementing or debugging.
- Every Cloud Pack is exact, directional, provider/version/region/account/tool/runtime specific, and evidence-backed.
- Transform through the typed Runtime Architecture Contract and provider-neutral IaC IR; do not use regex or raw text substitution as the semantic core.
- Use real source and target plans and approved isolated apply/runtime validation where required.
- Never broaden IAM, public exposure, network egress, data residency, retention, or secret access merely to make a gate pass.
- Keep development, negative, holdout, and representative workload corpora independent.
- Verify rollback, destroy, and orphan cleanup.
- Only `scripts/batch33/run_cloud_gate.py` may determine certification readiness.


# Batch 34 ultra-large portfolio scale skills

- Repository-scoped Codex skills live in `.agents/skills/b34-*/SKILL.md`.
- Invoke the smallest relevant skill explicitly with `$b34-...`.
- Every portfolio pack is exact, immutable-scope, tenant/region/toolchain specific, and evidence-backed.
- Use typed inventory, graph, work-unit, scale, campaign, and DR contracts; do not use unbounded scripts as the scale core.
- All distributed work is bounded, idempotent or compensatable, checkpointed, tenant isolated, and replayable.
- Keep development, negative, holdout, and representative portfolio corpora independent.
- Do not hide inaccessible, failed, unsupported, or over-budget repositories from metrics.
- Only `scripts/batch34/run_portfolio_gate.py` may determine certification readiness.


## Batch 35 advanced correctness and formal verification skills

Use the `.agents/skills/b35-*` skills for property, metamorphic, mutation, fuzz, symbolic, model, contract, data, security, concurrency, numeric, solver, oracle, counterexample, coverage, assurance, and certification work. Read `docs/batch35/IMPLEMENTATION_CONTRACT.md` and `QUALITY_GATES.md` first. Do not claim formal proof, certified correctness, or production assurance without immutable real evidence and the conservative Batch 35 gate.


## Batch 36 developer experience skills

Use `.agents/skills/b36-*` for IDE, CLI, PR bot, local preview, source-target navigation, explainability, quick fixes, semantic conflicts, ownership, local evaluation, recipe authoring, review, offline, telemetry, and certification work. Read `docs/batch36/IMPLEMENTATION_CONTRACT.md` and `QUALITY_GATES.md` first. All surfaces must consume the same typed protocol, source-map, ownership, policy, artifact, review, and evidence contracts. Never grant arbitrary shell, broad repository writes, secret access, source-code telemetry, self-approval, or certification without real host, SCM, holdout, and representative evidence.


# Batch 37 extension SDK and marketplace

Use `$b37-*` skills for extension SDK, sandbox, publisher, signing, release, installation, revocation, and commercial marketplace work. Never mark an extension or Marketplace Pack certified without immutable evidence and the Batch 37 gate.


## Batch 37 complete extension ecosystem

Use `.agents/skills/b37-*` for SDK, marketplace, dependency, runtime, catalog, publisher, continuous certification, migration, continuity, legal/support, private/offline, SRE, settlement, and EOL implementation. Never claim ecosystem closure until `run_marketplace_closure_gate.py` passes on exact evidence.

## Batch 1–37 strict test suite

Use `$tst-strict-suite-orchestrator` to plan full qualification. Use the exact `$tst-bXX-*` skill for each product batch and relevant `$tst-*` cross-cutting skills. Do not claim a feature or release passed from file presence, mock-only execution, screenshots, edited status, weakened tests or stale evidence. The authoritative gate is `scripts/test-suite/run_strict_test_gate.py`.

## Batch 38: 企业部署矩阵与升级生命周期
Use `.agents/skills/b38-*` for implementation and certification. Never mark a pack certified without immutable real evidence, holdout, representative workloads and the Batch 38 gate.

## Batch 39: 全球SRE与平台运营
Use `.agents/skills/b39-*` for implementation and certification. Never mark a pack certified without immutable real evidence, holdout, representative workloads and the Batch 39 gate.

## Batch 40: 安全供应链与合规认证
Use `.agents/skills/b40-*` for implementation and certification. Never mark a pack certified without immutable real evidence, holdout, representative workloads and the Batch 40 gate.

## Batch 41: 迁移知识图谱与智能飞轮
Use `.agents/skills/b41-*` for implementation and certification. Never mark a pack certified without immutable real evidence, holdout, representative workloads and the Batch 41 gate.

## Batch 42: 成熟Agent迁移工厂
Use `.agents/skills/b42-*` for implementation and certification. Never mark a pack certified without immutable real evidence, holdout, representative workloads and the Batch 42 gate.

## Batch 43: 产品版本、兼容与LTS生命周期
Use `.agents/skills/b43-*` for implementation and certification. Never mark a pack certified without immutable real evidence, holdout, representative workloads and the Batch 43 gate.

## Batch 44: FinOps与迁移经济优化
Use `.agents/skills/b44-*` for implementation and certification. Never mark a pack certified without immutable real evidence, holdout, representative workloads and the Batch 44 gate.

## Batch 45: 成熟产品综合认证
Use `.agents/skills/b45-*` for implementation and certification. Never mark a pack certified without immutable real evidence, holdout, representative workloads and the Batch 45 gate.


## Batch 46 Complete product convergence
Use `$b46-product-convergence-reference-implementation-factory` as the only entry point for product convergence. Do not create parallel workflow, policy, evidence, capability, or skill-registry kernels. The final state is decided only by `run_convergence_gate.py`.
