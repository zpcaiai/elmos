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

# Batch 35-45 mature product skills

- Use the smallest applicable `$b35-*` Skill for advanced correctness and formal verification; never treat a solver, fuzz run, coverage number, or generated oracle as proof without replayable counterexamples and independent evidence.
- Use `$b36-*` for IDE, CLI, and pull-request workflows. Preserve protected regions, provenance, review authority, offline boundaries, and least privilege.
- Use `$b37-*` for SDK and Marketplace extensions. Require ABI compatibility, sandboxing, signing, provenance, publisher identity, revocation, and commercial-policy evidence.
- Use `$b38-*` for edition deployment and upgrades. Treat each topology and version tuple independently; prove rollback, mixed-version behavior, recovery, and offline update integrity.
- Use `$b39-*` for global SRE work. Bind SLO, incident, restore, DR, support, and service-credit claims to real operational evidence and accountable owners.
- Use `$b40-*` for supply-chain and compliance work. Do not equate a control crosswalk or scan with certification; preserve independent assessment and unresolved risk.
- Use `$b41-*` for migration knowledge and prediction. Enforce provenance, freshness, calibration, consent, tenant isolation, and privacy-preserving aggregation.
- Use `$b42-*` for the governed Agent factory. Keep tools least-privileged, autonomy bounded and degradable, human takeover available, and kill-switch behavior tested.
- Use `$b43-*` for product compatibility and LTS. Treat every API, event, Schema, SDK, Runner, Recipe, Pack, database, and mixed-version path as an explicit compatibility contract.
- Use `$b44-*` for FinOps and economics. Reconcile metering to bills and evidence; include model, Runner, storage, egress, human review, support, and residual operating costs.
- Use `$b45-*` only for comprehensive maturity certification. The final gate cannot override failed domain gates, unresolved critical risk, missing independent review, or absent customer outcome evidence.
- For Batch 35, run `scripts/batch35/validate_verification_pack.py` and only `scripts/batch35/run_verification_gate.py` may determine certification readiness.
- For Batch 36, run `scripts/batch36/validate_developer_experience_pack.py` and only `scripts/batch36/run_developer_experience_gate.py` may determine certification readiness.
- For Batch 37, run `scripts/batch37/validate_marketplace_pack.py` and `scripts/batch37/validate_marketplace_closure.py`; only `scripts/batch37/run_marketplace_gate.py` and `scripts/batch37/run_marketplace_closure_gate.py` may determine core and closure certification readiness.
- For Batches 38-45, run `python scripts/mature_product_toolkit.py validate --batch <n>` and the applicable conservative gate. Keep field evidence `NOT_RUN` until actually executed and authorized.


## Batch 35 advanced correctness and formal verification skills

Use the `.agents/skills/b35-*` skills for property, metamorphic, mutation, fuzz, symbolic, model, contract, data, security, concurrency, numeric, solver, oracle, counterexample, coverage, assurance, and certification work. Read `docs/batch35/IMPLEMENTATION_CONTRACT.md` and `QUALITY_GATES.md` first. Do not claim formal proof, certified correctness, or production assurance without immutable real evidence and the conservative Batch 35 gate.

# Product Batch B34-B39 commercialization controls

These Product batches are a separate namespace from Migration Packs M35-M45.
Product Skills live under `agent-skills/runtime/`; `.agents/skills/b35-*` through
`.agents/skills/b45-*` continue to mean Migration Pack capabilities.

- B34: derive tenant context only from authenticated identity and trusted
  resource bindings. Enforce tenant isolation in authorization, PostgreSQL RLS,
  caches, events, artifacts and service boundaries. Human and workload identity,
  JIT grants, break-glass access and credential leases are exact, short-lived,
  revocable and auditable; missing or ambiguous context fails closed.
- B35: keep provider DTOs behind adapters, identify repositories by provider
  instance plus native ID, use short-lived scoped credential leases, resolve
  exact commits, authorize submodules separately, verify LFS objects, and mark
  partial/sparse workspaces incomplete until hydrated. Never persist tokens or
  treat sparse checkout as a security boundary.
- B36: separate the ELMOS scheduler from infrastructure providers. Runner
  capabilities require attestation and independent verification. Sandbox
  policy is rootless, read-only-source, default-deny-network and cannot be
  weakened by repository content. Offline permits cannot create new rights;
  use epochs, idempotency, receipts and reconciliation instead of exactly-once
  claims.
- B37: keep content objects, artifacts, attestations, verification decisions,
  evidence graphs and packs distinct. Producer and verifier must be separate.
  Preserve native and normalized external evidence separately. `UNKNOWN`,
  `INCONCLUSIVE` and `NOT_RUN` never pass. Metrics require versioned definitions,
  grain and denominator; critical failures cannot be hidden by aggregation.
- B38: separate PAP, PIP, PDP and PEP. Signed bundles are immutable, versioned
  and revocable. Missing context, evaluation error, unsupported mandatory
  obligations, `INDETERMINATE` and `NOT_APPLICABLE` fail closed. Exceptions are
  exact, expiring and compensating; deployment gates bind artifact digests;
  typed remediation is simulated, approved where irreversible, and reverified.
- B39 Finance is separate from Migration Pack M39 Global SRE. Use exact decimal
  money and quantity values, explicit currencies, periods, effective dates and
  rounding rules. Usage, charge, invoice, cash, revenue and journal states are
  distinct; corrections are versioned and reconciled. Unknown provider or bank
  results block retry, close and publication until reconciled. Enforce tenant,
  legal-entity, segregation-of-duties, payment-data and Secret Reference
  boundaries. Static Skill validation is not accounting, tax, payment, bank or
  management-reporting certification.

The Product control-plane APIs only prepare `READY_FOR_EXTERNAL_GATE` or
`READY_FOR_HUMAN_DECISION`. They never certify, approve, merge, deploy, execute
provider operations, or manufacture enforcement receipts. Keep those fields
false and external evidence `NOT_RUN` until the operation actually occurs.


## Batch 36 developer experience skills

Use `.agents/skills/b36-*` for IDE, CLI, PR bot, local preview, source-target navigation, explainability, quick fixes, semantic conflicts, ownership, local evaluation, recipe authoring, review, offline, telemetry, and certification work. Read `docs/batch36/IMPLEMENTATION_CONTRACT.md` and `QUALITY_GATES.md` first. All surfaces must consume the same typed protocol, source-map, ownership, policy, artifact, review, and evidence contracts. Never grant arbitrary shell, broad repository writes, secret access, source-code telemetry, self-approval, or certification without real host, SCM, holdout, and representative evidence.

## Batch 37 extension SDK and Marketplace skills

Use `.agents/skills/b37-*` for extension manifests, ABI and SDK contracts, sandboxing, publisher identity, dependency locks, signing/SBOM/provenance, release and revocation, Marketplace operations, private/offline distribution, settlement, support, and EOL work. Read `docs/batch37/IMPLEMENTATION_CONTRACT.md`, `QUALITY_GATES.md`, and `CLOSURE_QUALITY_GATES.md` first. Treat every extension, version, publisher, tenant, runtime, and product tuple as exact. Missing, stale, synthetic, `UNKNOWN`, `INCONCLUSIVE`, or `NOT_RUN` evidence never certifies; corpus evidence must be independently attested and digest-bound. Research and experimental packs may pass structural validation but remain `NOT_CERTIFIED`.
