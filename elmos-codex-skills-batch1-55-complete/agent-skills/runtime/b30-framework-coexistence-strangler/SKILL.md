---
name: b30-framework-coexistence-strangler
description: "Design and implement framework coexistence, facade, adapter, routing, shared identity, data ownership, event bridge, dual-run, observability, cutover, and retirement patterns for gradual migration when atomic framework replacement is unsafe."
---

## Operating mode

Work in the repository. Inspect existing Batch 20-29 modules, contracts, build commands, framework packs, and tests before editing. Implement the smallest production-shaped vertical slice that satisfies this skill; do not stop at a design document when code, manifests, and executable tests can be added.

Read these shared contracts first:

- `../../../docs/batch30/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch30/QUALITY_GATES.md`
- `../../../docs/batch30/REPOSITORY_LAYOUT.md`
- `../../../docs/batch30/VERSION_POLICY.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch30/scaffold_framework_pack.py ...`
- `python3 scripts/batch30/validate_framework_pack.py ...`
- `python3 scripts/batch30/run_framework_gate.py ...`

## Global constraints

- Treat every framework migration pack as directional and version-specific. Reverse migration and version upgrade are separate packs.
- Extract runtime behavior into the framework-neutral Framework Contract Model before generating target code. Do not implement annotation-name substitution as the migration architecture.
- Invoke real source and target build/runtime tools. A generated project that only parses is not evidence of support.
- Preserve authentication, authorization, transaction, persistence, message delivery, configuration precedence, validation, lifecycle, and error contracts.
- Keep development, holdout, and representative-repository corpora physically separate. Do not author rules from holdout cases.
- Prefer deterministic mappings and certified adapters. Model-generated output is a candidate and must pass the same build, contract, behavior, security, and test-integrity gates.
- Record unsupported, conditional, and unknown behavior explicitly. Never hide it with TODOs, permissive stubs, broad exception swallowing, disabled security, or weakened tests.
- Record exact framework/runtime/provider versions, source and target commits, recipe digest, model/prompt versions, toolchain digests, and evidence references.
- Fix repeated failures in the fingerprint, contract model, recipe, adapter, or generator instead of patching many generated files.
- Run the narrowest relevant tests first, then the independent holdout suite and framework certification gate before making release claims.


## Skill 1179: Framework coexistence and Strangler migration

Provide a production-shaped transitional architecture so source and target frameworks can coexist safely while slices move incrementally and compatibility components have explicit exit plans.

## Use this skill when

- A framework migration cannot be completed atomically.
- Source and target must share traffic, identity, data, events, or operations during transition.
- A pack needs a facade, sidecar, anti-corruption layer, retained runtime, or compatibility window.

## Framework-specific risks and invariants

- Dual writes, shared sessions, duplicate schedulers/consumers, and inconsistent security can create irreversible errors.
- Temporary facades become permanent without owners, SLOs, cost budgets, and exit criteria.
- Source and target may disagree on data authority, IDs, errors, cache invalidation, or observability.
- Traffic mirroring can trigger real write side effects.

## Workflow

1. Identify migration slices, authorities, callers, sessions, identity, data stores, events, jobs, caches, and operational dependencies.
2. Define transitional FCM and a coexistence manifest covering routing, write/read authority, adapters, event bridges, identity/session, telemetry, rollback, and exit dates.
3. Choose boundary patterns: reverse proxy, facade, API adapter, message bridge, CDC, view, sidecar, retained service, or feature flag.
4. Implement safe routing/adapters for one slice and prevent mirrored writes or duplicate consumer/job ownership.
5. Add shared correlation, source-target observability, and data/message reconciliation.
6. Run source-only, target-only, coexistence, shadow/canary, failure, and rollback tests.
7. Define consumer migration and compatibility-layer retirement checks.
8. Publish runbooks, risk register, latency/cost budget, ownership, SLOs, and exit evidence.

## Required repository outputs

- `framework-packs/<source>-to-<target>/coexistence/manifest.json`
- Routing/facade/adapter implementation
- Write authority/data sync/event bridge contracts
- Shared identity/session/observability plan
- Rollback/retirement runbooks
- Coexistence and failure corpus

## Verification

- Run source-only, target-only, and mixed environments.
- Verify no duplicate writes, consumers, schedulers, payments, notifications, or other side effects.
- Run reconciliation, security/session, routing, failure, rollback, and retirement-readiness tests.
- Run the framework gate for declared coexistence scope.

## Stop and escalate when

- Source and target can independently write the same entity.
- Mirrored requests can reach real side-effecting providers.
- Identity, authorization, or session behavior diverges.
- Compatibility components lack owners, SLOs, budgets, or exit dates.

## Definition of done

The coexistence path is implemented/tested for a real slice, has single authority, shared security/telemetry, verified rollback, explicit budgets, and measurable retirement criteria.
