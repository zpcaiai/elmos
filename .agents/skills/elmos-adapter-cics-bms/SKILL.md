---
name: elmos-adapter-cics-bms
description: Implement CICS BMS repository-dsl parsing, semantic lowering, framework/runtime
  mapping, target emission and verification for repository-scale modernization.
version: 1.0.0
skill_id: ELMOS-POLY-103
layer: technology-adapter
risk: critical
readiness: not-run
dependencies:
- elmos-legacy-build-runtime-discovery
triggers:
- Use when implementing or executing `elmos-adapter-cics-bms`.
- Use when the migration DAG requires `technology-adapter` capability.
- Use when `cics-bms` is detected as source, target or repository support surface.
outputs:
- adapters/cics-bms/adapter-manifest.json
- adapters/cics-bms/semantic-mapping.yaml
- adapters/cics-bms/verification-profile.yaml
---

# Adapter Cics Bms

## Objective

Implement CICS BMS repository-dsl parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.

This Skill is an **implementation and execution contract** for ELMOS. File presence, prompt execution, generated code volume, or static validation alone never proves runtime correctness or production readiness.

## When to use

- Use when implementing or executing `elmos-adapter-cics-bms`.
- Use when repository-scale conversion needs this capability in the migration DAG.
- Use for authorized modernization work only; preserve explicit source/target scope and customer data policy.

## Preconditions

- Immutable repository snapshot and source provenance are available.
- Authorization, secret handling, network/tool policy, runner identity and resource budgets are bound to the run.
- Upstream artifacts are schema-valid and fresh for the current snapshot.
- Source-native baseline evidence exists when the source can be executed.
- Readiness starts as `not-run`; unavailable source runtimes are recorded as a verification limitation, never silently waived.

### Hard dependencies

- `elmos-legacy-build-runtime-discovery`

## Inputs

- `run_id`, immutable `snapshot_id`, source/target technology IDs and route mode.
- authorized source tree, build/runtime descriptors and bounded artifact references.
- Repository IR plus relevant semantic IR artifacts and behavior baselines.
- target profile, semantic-loss budget, coexistence policy, verification and rollback policy.

## Outputs

- `adapters/cics-bms/adapter-manifest.json`
- `adapters/cics-bms/semantic-mapping.yaml`
- `adapters/cics-bms/verification-profile.yaml`

### Technology profile

- Technology ID: `cics-bms`
- Display: CICS BMS
- Kind: repository-dsl
- File/build markers: .bms
- Build systems: owner runtime/toolchain
- Preferred analyzers: BMS parser
- Runtime/framework surface: repository support surface
- Native verification: parse/roundtrip fixtures, owner-runtime characterization

### Semantic risk register

- map coordinates/attributes.
- AID keys.
- field protection.
- terminal state.

## Guardrails

- Never perform blind line-by-line translation when source semantics are not structurally equivalent.
- Never invent business rules, copybook layouts, transaction behavior, database semantics, UI events, scheduler dependencies, proof results or unavailable runtime observations.
- Never weaken tests, suppress scanner/compiler errors, broaden privileges or convert missing evidence to `pass`.
- Money, data integrity, security, concurrency, numerical precision, ABI, real-time and irreversible state changes require explicit validation obligations.
- Preserve source encoding, byte layout and original coordinates where they affect behavior or auditability.
- Changes must be checkpointed, idempotent and limited to the authorized worktree.

## Workflow

1. Detect dialect/version, compiler/runtime, include/copy search paths, generated/binary assets and target-specific conditional compilation.
2. Parse with a native/compiler-grade frontend where available; use tolerant grammar fallback only for discovery and preserve confidence/provenance.
3. Resolve symbols and lower source constructs into Repository IR plus the relevant Business, Record, Transaction, Batch, UI, Numerical, Safety, 4GL or ABI IR.
4. Record dynamic, platform-owned, generated, binary-only and unsupported behavior in the semantic-loss register rather than guessing.
5. Emit target-neutral mappings and route-ready transformation obligations with stable source spans and reversible edit provenance.
6. Run native compilation/interpreter and representative characterization fixtures in the trusted runner before allowing route execution.

## Implementation Contract

- Implement capability behind a stable CLI/service boundary; prompts may orchestrate but are not the semantic source of truth.
- Prefer native compiler/runtime semantic APIs and symbol resolution over syntax-only parsing.
- Version adapters, rules, schemas, IR dialects, target profiles and evidence producers independently.
- Maintain `source span -> IR -> rule/decision -> patch -> test/evidence` provenance.
- Route every unsupported construct to a typed semantic-loss/blocker record with severity, owner and safe alternatives.
- Use deterministic codemods for mechanically provable changes; bounded agents may address residuals only under explicit patch and verification budgets.
- Support pause/resume/cancel/retry, worker fencing, artifact hashing and server-side long-task recovery.
- Keep proprietary source and large artifacts outside model messages; pass references and bounded excerpts under data policy.
- Production certification requires executed target-native evidence and, where applicable, source-target differential or shadow evidence.

## Required Tests

- [ ] Dialect/version matrix fixture with parser/compiler agreement.
- [ ] Positive and negative symbol-resolution fixtures.
- [ ] Round-trip/source-span stability test for normalized source.
- [ ] Representative runtime/framework behavior characterization.
- [ ] Unsupported/dynamic construct must produce an explicit blocker or semantic-loss item.
- [ ] Unauthorized path, command, network and secret-access tests.
- [ ] Clean-environment reproducibility or documented nondeterminism test.
- [ ] Semantic-loss blocker test for a critical unsupported construct.

## Verification

1. Validate machine-readable artifacts against versioned schemas.
2. Re-run on a clean checkpoint to detect hidden state and non-idempotent writes.
3. Execute native source/target toolchains where available in a trusted sandbox.
4. Attach command line, toolchain/runtime identity, exit code, logs, hashes and environment fingerprint.
5. Compare source/target behavior using route-specific validators and declared tolerances.
6. Reject stale, mismatched-snapshot or policy-incompatible evidence.

## Stop and Escalate

Stop safely and preserve the last good checkpoint when:

- authorization, source snapshot, required runtime/toolchain, schema or dependency artifact is missing/stale;
- critical semantic loss affects money, data integrity, security, concurrency, numerical correctness, ABI, real-time safety or irreversible state;
- source behavior cannot be characterized enough to distinguish a correct migration from a plausible rewrite;
- required migration/verification resource budget is exhausted;
- a conversion would require unapproved license, platform, data residency or production access.

Return a structured blocker with affected symbols/modules, evidence, severity, owner, safe alternatives and the exact approval or implementation work required.

## Definition of Done

- [ ] Stable implementation interface and versioned configuration exist.
- [ ] Source dialect/runtime coverage is explicitly bounded and tested.
- [ ] Required IR/schema outputs validate and retain provenance.
- [ ] Unit, integration, negative, recovery and representative end-to-end tests pass.
- [ ] Source/target native verification has executed where required.
- [ ] Semantic losses, waivers and residual risk are explicit.
- [ ] Evidence is fresh and bound to the same snapshot, route, policies and toolchain identities.
- [ ] Rollback/coexistence plan is executable for production-affecting changes.
- [ ] Readiness is derived from executed gates, never inferred from generated files.

## Completion Report

Return machine-readable and human-readable completion reports containing run/snapshot IDs, route, dialect/runtime versions, transformed modules, commands and exit codes, tests/gates, semantic losses, approvals/waivers, performance/security results, checkpoints/rollback location, artifacts and hashes.

Final status must be one of `completed`, `completed-with-approved-exceptions`, `blocked`, or `failed`. Never emit `completed` while any required gate is `not-run`.
