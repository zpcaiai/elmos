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

# Product Batch B34-B55 commercialization controls

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
- Product B40-B55 enterprise-domain Skills are separate from Migration Packs
  M40-M45. B40A has approved conversation-design provenance; B40B-B55C are a
  generated planning edition and require domain-owner refinement before any
  production implementation or certification claim.
- Reuse authoritative Tenant, Identity, Organization, Artifact, Policy, Audit,
  Workflow, Case, Contract, Finance, Customer, Data and Infrastructure
  aggregates. Keep source facts immutable and interpretations, plans, models,
  policies, snapshots and provider mappings versioned.
- Enforce tenant and resource isolation at API, database, cache, event, search,
  analytics, connector and export boundaries. Preserve source identity,
  effective dates, provider versions, actor/workload, purpose, decisions and
  evidence. Unknown, partial, timed-out or unreconciled states are non-success.
- Use typed, least-privileged automation and provider adapters. AI output cannot
  approve regulated, financial, employment, security, safety, healthcare,
  energy-control or contractual outcomes without an explicit governed policy.
  Side effects must be idempotent, auditable, reconcilable and independently
  evidenced; static Skill checks remain engineering evidence only.

The Product control-plane APIs only prepare `READY_FOR_EXTERNAL_GATE` or
`READY_FOR_HUMAN_DECISION`. They never certify, approve, merge, deploy, execute
provider operations, or manufacture enforcement receipts. Keep those fields
false and external evidence `NOT_RUN` until the operation actually occurs.

## Combined Batch 1-55 Skill distribution

- `elmos-codex-skills-batch1-55-complete` is a dual-namespace distribution:
  Migration Packs M1-M45 and Product commercialization B34-B55. Numeric labels
  from the two namespaces are never interchangeable.
- Every installed name is at most 64 characters. Deterministic aliases retain
  `source_name`, exact provenance and content digest in `manifest.json`.
- `normalized-source-incomplete` and `generated-planning-edition` contracts are
  locally invocable guidance, not authoritative production completion.
- Only `make batch1-55-skills` determines structural package readiness. It does
  not alter the separate Batch 1-37 strict certification results or external
  evidence, which remain `NOT_RUN` until independently executed.


## Batch 36 developer experience skills

Use `.agents/skills/b36-*` for IDE, CLI, PR bot, local preview, source-target navigation, explainability, quick fixes, semantic conflicts, ownership, local evaluation, recipe authoring, review, offline, telemetry, and certification work. Read `docs/batch36/IMPLEMENTATION_CONTRACT.md` and `QUALITY_GATES.md` first. All surfaces must consume the same typed protocol, source-map, ownership, policy, artifact, review, and evidence contracts. Never grant arbitrary shell, broad repository writes, secret access, source-code telemetry, self-approval, or certification without real host, SCM, holdout, and representative evidence.

## Batch 37 extension SDK and Marketplace skills

Use `.agents/skills/b37-*` for extension manifests, ABI and SDK contracts, sandboxing, publisher identity, dependency locks, signing/SBOM/provenance, release and revocation, Marketplace operations, private/offline distribution, settlement, support, and EOL work. Read `docs/batch37/IMPLEMENTATION_CONTRACT.md`, `QUALITY_GATES.md`, and `CLOSURE_QUALITY_GATES.md` first. Treat every extension, version, publisher, tenant, runtime, and product tuple as exact. Missing, stale, synthetic, `UNKNOWN`, `INCONCLUSIVE`, or `NOT_RUN` evidence never certifies; corpus evidence must be independently attested and digest-bound. Research and experimental packs may pass structural validation but remain `NOT_CERTIFIED`.

## Batch 1-37 strict test suite

- Start full qualification with `$tst-strict-suite-orchestrator`, then use the exact `$tst-bXX-*` Skill and the smallest relevant cross-cutting `$tst-*` Skills.
- Preserve the 408 exact seed cases and all eight variants per Batch. Expand them with executable repository-specific fixtures; do not replace them with smoke tests or file-presence checks.
- Local build and toolkit evidence is engineering evidence only. It must not update certification case results; external or production-equivalent evidence stays `not-run` / `NOT_RUN` until actually executed and authorized.
- Every passed case must bind exact case/catalog, artifact, environment, raw evidence roles, replay command, executor, independent verifier, authorization, and required independent corpora.
- Only `scripts/test-suite/run_strict_test_gate.py` may produce the Batch 1-37 certification decision. Certification requires a signed request covering all 408 result/evidence digests and a separate non-revoked trust store.
- Run `make test-suite-check` for structural/toolkit validation. `make test-suite-gate` is expected to fail closed while any required case is not run.

## Batch 1-65 supplemental test suite

- Treat `test-suites/batch1-65-slightly-strict/` as supplemental design and engineering qualification only; it never replaces the 408-case Batch 1-37 certification suite.
- Use `scripts/test-suite/validate_batch1_65_slightly_strict.py` and only `scripts/test-suite/run_batch1_65_slightly_strict_gate.py` for the supplemental decision. The supplied source evaluator is non-authoritative because it does not enforce exact 750-case completeness.
- Preserve all 750 cases, 88 test Skills and 1,296 direct source-Skill coverage edges. `NOT_RUN`, missing results, fabricated evidence, self-verification and incomplete deterministic repeats fail closed.
- The maximum supplemental decision is `READY_FOR_EXTERNAL_GATE`; it cannot certify Batch 1-65 or update Batch 1-37 certification results.

## Batch 66-80 polyglot project synthesis Skills

- Canonical PG223-PG417 sources live in `elmos-codex-skills-batch66-80-complete/`; installed Runtime Skills live under `agent-skills/runtime/b66-*` through `b80-*` and retain exact source digests plus Codex interfaces.
- Start with `$elmos-project-synthesis`, then invoke only the smallest exact `$b66-*` through `$b80-*` Skill for TypeScript/JavaScript, Go, Kotlin, PHP, C/C++, Rust, Flutter/Dart, Swift, shell, SQL/API contracts, build/proxy configuration, containers, IaC/Kubernetes/Helm, CI/CD, or polyglot operations.
- Treat repository hooks, plugins, lifecycle scripts, macros, actions, modules, images, templates, pipelines, and executable configuration as untrusted. Parse and plan first; default-deny undeclared network, secrets, permissions, signing, provider, cluster, CI, and deployment effects.
- Static package validation and the Java/Python/C# starter engine do not prove other language/SDK, device, database, cluster, cloud, signing, CI provider, or production execution. Preserve unsupported and unavailable checks as `NOT_RUN`.
- Run `make batch66-80-skills` for immutable package, installed interface, and PG001-PG417 integration validation. Certification Skills may only report the highest state supported by exact real toolchain and independent evidence.

## Batch 66-80 supplemental qualification suite

- `test-suites/batch66-80-slightly-strict/` is supplemental design and local engineering qualification only; it neither replaces nor updates the Batch 1-37 strict certification suite.
- Canonical inputs live in `elmos-codex-skills-batch66-80-slightly-strict-tests/`. Preserve its 544 manifest-owned files, 35 test Skills, 450 cases, 195 source Skills, 390 source-specific positive/negative cases, 60 cross-cutting cases, P0/P1/P2 counts 312/120/18, 103 zero-tolerance cases, and one exact result file per case.
- Start with `$tst-b66-80-slightly-strict-suite-orchestrator`, then use the exact Batch owner and the smallest applicable cross-cutting test Skill. Bind PG223-PG417 cases to `SOURCE_SKILL_HASHES.csv`; source or environment drift invalidates prior evidence.
- Use `scripts/test-suite/validate_batch66_80_slightly_strict.py`; only `scripts/test-suite/run_batch66_80_slightly_strict_gate.py` may produce the supplemental decision. The maximum is `READY_FOR_EXTERNAL_GATE`, never certification.
- `not-run`, skipped, flaky, missing results, stale/tampered digests, fabricated or synthetic execution, static-as-runtime claims, self-verification, missing authorization/evidence roles, blocked or failed cases fail closed. Zero-tolerance cases cannot be waived. The supplied package gate is useful static tooling but the repository wrapper is the conservative supplemental authority.
- The earlier generated 120-case design is superseded. Do not use `tooling/generate_batch66_80_supplemental_suite.py` to overwrite the imported 450-case suite.

## Batch 81-95 specialized Language Packs

- Canonical sources live in `elmos-language-packs-batch81-95-complete/`. Its PG223-PG402 IDs are package-local to `elmos.language-packs` and collide with global Batch 66-80 IDs; never merge, renumber, or present them as a continuation of global PG417.
- Installed Runtime Skills use deterministic `$b81-*` through `$b95-*` aliases. Every normalized Skill must preserve `source_package`, `source_id`, `source_name`, source digest, Batch, proposed status, and the `package-local-language-pack` namespace in `docs/language-packs-batch81-95/installed-manifest.json`.
- Start with `$elmos-project-synthesis`, then select the narrowest exact alias for COBOL/mainframe, SAP ABAP, database procedural languages, IEC 61131-3 PLC, MATLAB/Simulink, Modelica/FMI, VB/Office, IBM i RPG, R, SAS, Salesforce, Objective-C/Swift, Delphi/Object Pascal, BEAM, or Lua/OpenResty.
- Treat source, macros, plugins, binaries, models, vendor metadata, generated code, and project configuration as untrusted. Default-deny vendor systems, production databases, devices, physical actuation, tenant/org access, credentials, signing, deployment, cutover, and decommissioning.
- Static validation is not native parser/compiler/simulator/runtime, numerical/transaction/timing equivalence, safety, scientific, financial, clinical, physical-system, vendor-platform, parallel-run, production, or certification evidence. Missing representative execution stays `NOT_RUN`.
- Run `make language-packs-batch81-95`. Certification or cutover Skills may only report the highest state supported by exact source/installed identity, real native evidence, authorization, Batch safety boundary, and independent qualified review.

## Batch 81-95 supplemental qualification suite

- Canonical test inputs live in `elmos-batch81-95-slightly-strict-test-skills/`. Preserve exactly 40 test Skills T081-T120, 640 cases CASE-0001-CASE-0640, 180 direct package-local source-Skill edges, 47,700 total case-target links, severities Critical/High/Medium 170/400/70, and one result per case under `test-suites/batch81-95-language-packs-slightly-strict/`.
- Use `scripts/test-suite/validate_batch81_95_language_packs.py`; only `scripts/test-suite/run_batch81_95_language_pack_gate.py` may produce the supplemental decision. The maximum is `READY_FOR_EXTERNAL_GATE`, never certification or vendor/physical/production approval.
- Bind each direct case and coverage row to its `LP-Bxx-PGxxx` key, original package-local ID/name/digest, installed alias/digest/interface, exact target profile, environment, authorization, executor, independent verifier, replay, cleanup, and required raw evidence roles. Never suppress or globally relabel the PG223-PG402 collision.
- The supplied source evaluator is non-authoritative because it does not enforce exact 640-result completeness or fail-closed `NOT_RUN`. Use the installed source-coverage, evidence-integrity, anti-cheating, and final-release test Skills as scoped guidance; the repository validator and gate remain authoritative for this supplement.
- `NOT_RUN`, missing or reordered results, ID relabeling, namespace collision suppression, static-as-native claims, fabricated/synthetic evidence, self-verification, missing authorization, incomplete repeats, weakened tolerances or safety controls, and zero-tolerance findings fail closed. The earlier generated 120-case design is superseded and must not overwrite the imported suite.

## Batch 97-104 product-closure Skills

- Canonical normalized sources live in `elmos-codex-skills-batch97-104-complete/`; installed Runtime Skills live under `agent-skills/runtime/b97-*` through `b104-*` and retain exact source digests plus Codex interfaces.
- Preserve exactly 128 Skills, 16 per Batch, with Batch-local IDs `B97-S01` through `B104-S16`. These IDs belong to the `batch-local-product-closure` namespace; never infer, mutate, or advertise a global PG allocation without a separately approved namespace authority.
- Compile each Markdown Skill through `scripts/compile_skill_contract.py` before runtime use. Inputs, outputs, permissions, ordered steps, rollback, unit/integration/negative tests, evidence requirements and verification states must remain non-empty and schema-valid.
- Product-closure certification is fail-closed. Content-addressed evidence must be byte-bound, authorized and independently verified; templates, static validation and generated artifacts remain engineering evidence. The local gate may return at most `ready_for_external_gate` and never `certified`.
- Run `make batch97-104-skills` for immutable package, DAG, compiled-contract, Schema, installer, installed-interface and anti-fabrication validation. Real runners, golden routes, equivalence, scale, security, customer, support and external certification evidence remain `NOT_RUN` until authorized execution occurs.

## Batch 38-45 strict test suite

- Start this qualification with `$tst-b38-45-strict-suite-orchestrator`, then use the exact Batch or cross-cutting `$tst-*` Skill owning the selected case IDs.
- Preserve all 400 exact cases, 30 test Skills, product Skills 1325-1496, two direct cases per strict category per Batch, and the checked-in `not-run` results.
- Local structural validation and the synthetic signed gate fixture are engineering evidence only. They never count as customer, independent-review, M38-M45 domain, production, recovery, financial, or field evidence.
- Every passed case must bind exact case/catalog, artifact/environment files, byte-counted raw evidence roles, replay, authorization, separate executor/verifier, and independent development/holdout/representative corpora.
- Only `scripts/test-suite-b38-45/run_strict_gate.py` may derive the Batch 38-45 suite decision. Certification requires eight eligible `CERTIFIED` M38-M45 domain gates, two distinct design partners, one independent review, an exact 400-result signed request, and a separate non-revoked trust store.
- Run `make test-suite-b38-45-check` for local toolkit validation. `make test-suite-b38-45-gate` must fail closed while field evidence remains `NOT_RUN`.

## Product closure Batch 56A and convergence overlay

- Product Batch 56A is a reviewed-design closure overlay, not Migration Pack M56 and not a numeric continuation that changes Product B34-B55 semantics. Start closure work with `$elmos-product-closure-maturity-orchestrator`, then invoke the smallest exact Product 56A Runtime Skill.
- Product Convergence is a cross-Batch implementation/reference overlay, not a new feature Batch. Start with `$conv-product-convergence-orchestrator`, then use the narrowest exact `$conv-*` Skill.
- Preserve the immutable canonical sources under `elmos-codex-skills-batch56a-product-closure/` and `elmos-product-convergence-reference-skills/`. Installed aliases, provenance digests and Codex interfaces are governed by `tooling/import_product_closure_convergence.py`.
- Source validators and static package tests are engineering evidence only. They cannot prove real providers, Private Runner isolation, runtime journeys, customer acceptance, independent review, unit economics, GA, production safety or certification.
- The checked-in convergence plan, capability registry, dependency graph, evidence graph, benchmark corpus, handoff package and Reference Route are fail-closed scaffolds. Empty graphs, draft plans, fuzzy `current`/`latest`/`x` versions, boolean-only criteria or arbitrary digest strings cannot prepare an external readiness review.
- Only `scripts/product-closure-batch56a/run_product_closure_gate.py` and `scripts/product-convergence/run_repository_convergence_gate.py` may prepare the corresponding repository readiness decisions. Their maximum local result is `READY_FOR_EXTERNAL_GATE`; they never approve GA or production certification.
- `NOT_RUN`, missing evidence files, digest or byte-count mismatch, path escape, self-verification, fewer than two independent design-partner organizations, missing independent review, or any P0/zero-tolerance finding fails closed. Keep current external evidence `NOT_RUN` until authorized real execution occurs.
- Run `make product-closure-convergence-skills` for source, install, interface and anti-fabrication regression validation. `make product-closure-gate` and `make product-convergence-gate` are expected to fail closed for the checked-in templates.
