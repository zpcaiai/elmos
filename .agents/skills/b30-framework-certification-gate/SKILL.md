---
name: b30-framework-certification-gate
description: Run the Batch 30 certification gate for a version-specific framework migration, upgrade, modernization, or coexistence pack and emit certified, limited, experimental, or blocked status from machine-readable build, startup, contract, holdout, security, data, and lifecycle evidence.
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


## Skill 1180: Batch 30 framework certification gate

Apply a conservative reproducible release decision so framework support claims cannot exceed executable evidence.

## Use this skill when

- A framework pack or exact version tuple is ready for release review.
- A support status is being raised, lowered, deprecated, or revoked.
- A customer or release process requests independent certification evidence.

## Framework-specific risks and invariants

- A green build can hide startup, route, security, transaction, data, message, job, or lifecycle regressions.
- Development corpus success is not independent evidence.
- Average pass rates can hide P0 security/data failures.
- Manual status editing can create unsupported customer claims.

## Workflow

1. Run `validate_framework_pack.py` and reject structure, ownership, exact-version, profile, or support-matrix errors.
2. Verify immutable source/target/framework/provider/toolchain and evidence digests.
3. Verify source fingerprint and FCM coverage for declared capabilities.
4. Verify real target build/startup and required P0 web/DI/config/validation/security/data/transaction/integration/lifecycle suites.
5. Verify source maps, test integrity, compatibility budget, supply-chain evidence, and target code ownership protection.
6. Verify separate holdout and representative-repository cases were not used to author rules.
7. Calculate outcomes only from machine-readable evidence; missing metrics fail or lower status.
8. Write certification, reasons, residual risks, maintenance owner, review date, and downgrade/revocation actions.

## Required repository outputs

- `framework-packs/<pack>/certification/certification.json`
- `framework-packs/<pack>/certification/gate-report.md`
- Evidence-backed support-matrix updates
- Residual-risk, maintenance-owner, and next-review records

## Verification

- Run `python3 scripts/batch30/run_framework_gate.py framework-packs/<pack>`.
- Independently inspect holdout and representative evidence.
- Verify P0 security/data/transaction regressions, duplicate effects, test-integrity violations, and critical unknowns are zero for certified scope.
- Verify build/startup/contracts refer to identical artifact/profile digests.

## Stop and escalate when

- Evidence is missing, stale, mutable, or for another tuple.
- Only development corpus or generated demo evidence exists.
- Any critical drop, security/data/transaction regression, duplicate effect, test-integrity violation, or unknown remains.
- Requested status conflicts with gate results.

## Definition of done

The gate emits the strongest defensible status from immutable evidence, records residual risk and ownership, and prevents unsupported framework claims.
