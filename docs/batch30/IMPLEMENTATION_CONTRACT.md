# Batch 30 Codex Implementation Contract

## Objective

Implement directional, version-specific framework migration, upgrade, modernization, and coexistence packs. A pack is not complete when annotations or APIs are renamed. It is complete only when active source runtime behavior is fingerprinted, represented in a framework-neutral Framework Contract Model, mapped to an exact target profile, built and started with real tools, tested through P0 framework contracts, evaluated on holdout and representative repositories, and recorded in machine-readable evidence.

## Required engineering behavior

1. Inspect before editing. Reuse Batch 20-29 engines, UIR, FCM, Runner, Repair, Behavior, and Evidence systems.
2. Implement one complete vertical slice before broad framework coverage.
3. Treat source-to-target direction, framework versions, runtime versions, and provider versions as one certification tuple.
4. Discover active runtime behavior using static plus safe runtime/build-time evidence; declared dependencies alone are insufficient.
5. Extract behavior into FCM before target code generation. Source annotations and target APIs belong in namespaced extensions or mappings, not core neutral contracts.
6. Preserve web, DI, configuration precedence, validation, authentication, authorization, persistence, transaction, messaging, cache, scheduler, error, lifecycle, and operational contracts.
7. Prefer deterministic recipes and certified adapters. Agent output is candidate code and must pass ordinary gates.
8. Keep development, holdout, and representative-repository corpora physically separate.
9. Never make tests green by disabling security, weakening assertions, swallowing errors, relaxing data constraints, or replacing real integrations with weaker mocks without approval.
10. Record exact commits, framework/runtime/provider versions, pack/recipe/profile digests, toolchains, models/prompts, tests, and evidence.
11. Protect customer-owned target code and use Batch 27 ownership/merge rules for incremental regeneration.
12. Change support claims only through the certification gate.

## Pack statuses

- `research`
- `experimental`
- `limited`
- `certified`
- `deprecated`
- `blocked`

## Capability statuses

- `certified`
- `supported`
- `conditional`
- `experimental`
- `detected-only`
- `blocked`

## Required evidence

- exact source and target version tuple
- source static/runtime fingerprint and coverage
- FCM contract artifact and conformance result
- target profile, dependency locks, SBOM/license/security evidence
- real source build/runtime result
- real target build/startup result
- P0 contract suites for declared domains
- negative and unsupported cases
- holdout corpus result
- representative repository result
- source-map coverage
- test-integrity result
- compatibility/coexistence budget
- lifecycle/maintenance owner and review date
