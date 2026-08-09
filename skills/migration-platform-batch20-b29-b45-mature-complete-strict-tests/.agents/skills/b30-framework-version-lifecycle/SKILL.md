---
name: b30-framework-version-lifecycle
description: Create and enforce framework version support, EOL, upgrade, compatibility, deprecation, and maintenance policies for Batch 30 framework packs. Use when adding version tuples, changing support claims, or planning customer upgrades.
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


## Skill 1163: Framework version and lifecycle governance

Make every framework claim exact, time-bounded, testable, and maintainable across source, target, runtime, build, serializer, ORM, broker, cache, scheduler, and security-provider versions.

## Use this skill when

- A pack adds or changes supported source/target versions.
- A framework, runtime, build tool, or provider reaches EOL or changes behavior.
- Customers require an LTS commitment, upgrade path, backport, or deprecation schedule.

## Framework-specific risks and invariants

- Broad version ranges hide changes in namespaces, defaults, serializers, security DSLs, ORM providers, and build plugins.
- A framework may be supported while one critical provider tuple is not.
- Provider upgrades can invalidate evidence without changing application source.
- Long-running projects require old pack/toolchain replay and funded security maintenance.

## Workflow

1. Inventory exact versions in manifests, lock files, images, CI matrices, corpora, evidence, and customer deployments.
2. Define exact supported tuples, including framework, runtime, build tool, serializer, ORM/database, auth, broker, cache, scheduler, and observability providers.
3. Classify each tuple as research, preview, stable, LTS, maintenance, deprecated, EOL, or blocked.
4. Define tested upgrade edges, prerequisites, known breaking changes, rollback requirements, and customer migration guides.
5. Implement CI matrices for active tuples and backport/security matrices for maintained tuples.
6. Define notice periods, support end dates, artifact retention, and customer impact.
7. Reject floating `latest`, `*`, mutable tags, and unsupported default-based claims.
8. Run the framework gate whenever tuple status changes.

## Required repository outputs

- `framework-packs/<pack>/version-matrix.json` and upgrade edges
- Exact dependency/toolchain/image locks
- Customer migration guide and compatibility notes
- Deprecation/EOL and security-backport records
- CI compatibility matrix

## Verification

- Run all active tuples through source fingerprint, target build/startup, and applicable P0 contracts.
- Verify no certified manifest uses floating versions or mutable tags.
- Execute at least one representative upgrade edge and rollback or forward-recovery path.
- Run the framework gate for every changed tuple.

## Stop and escalate when

- Exact framework or provider versions are unknown.
- A broad band is requested without evidence for materially different versions.
- EOL software is proposed as a new certified target without a formal exception.
- Customer migration or maintenance obligations cannot be funded.

## Definition of done

The pack has an exact tuple-based matrix, executable compatibility tests, lifecycle states, upgrade edges, customer guidance, maintenance ownership, and no unsupported floating dependencies.
