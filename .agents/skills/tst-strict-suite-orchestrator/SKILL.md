---
name: tst-strict-suite-orchestrator
description: "Orchestrate a conservative end-to-end test program for every Batch 1–37 capability, environment, holdout, evidence, waiver and release gate."
---

# Test Skill T001: Batch 1–37严格测试总编排

## Use this skill when

- Codex must implement, expand, execute, or review strict tests for Batch 1–37全部能力.
- A release claim for Batch 1–37 needs executable evidence rather than prose, screenshots, mocked success, or manually edited status.

## Read first

- `../../../docs/test-suite/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/test-suite/STRICTNESS_PROFILE.md`
- `../../../docs/test-suite/COVERAGE_POLICY.md`
- `../../../docs/test-suite/EVIDENCE_ANTI_CHEAT.md`
- `../../../test-suites/batch1-37-strict/suite.json`
- `../../../test-suites/batch1-37-strict/strict-profile.json`

## Mandatory invariants

- 任何Release都可追溯到原始Evidence
- P0/P1覆盖完整
- 未执行不等于通过

## Forbidden shortcuts

- 只运行Smoke Test
- 用汇总状态替代原始证据
- 跳过Holdout


## Mandatory case set

This skill owns or validates the following seed cases. Expand them with repository-specific fixtures without weakening their assertions:

- `TS-GOV-01-001`
- `TS-GOV-01-002`
- `TS-GOV-01-003`
- `TS-GOV-01-004`
- `TS-GOV-01-005`
- `TS-GOV-01-006`


## Workflow

1. Inspect the real implementation, contracts, migrations, workflows, permissions, runtime dependencies, existing tests, and evidence paths before editing.
2. Resolve every test to exact Batch capabilities, requirements, source/target artifacts, versions, owners, and risk tiers in the coverage matrix.
3. Materialize deterministic fixtures and an approved isolated environment. Use real compilers, runtimes, databases, browsers, providers, runners, or approved emulators where the case requires them.
4. Implement success, boundary, malformed/unsupported, dependency-failure, authorization, replay/idempotency, version-drift, and evidence-tamper variants.
5. Run the narrowest deterministic tests first, then negative cases, independent holdout cases, representative workloads, and the strict release gate.
6. Store immutable raw evidence before summaries. Bind every result to case ID, source commit, target commit, artifact digest, toolchain, environment, seed, policy and executor identity.
7. Fix product defects at the correct contract, engine, workflow, policy, generator or runtime layer. Do not weaken tests, baselines, masks, tolerances, permissions or evidence rules.
8. Update the coverage matrix, residual-risk register and customer-readable report. Unimplemented or unexecutable cases remain explicit blockers or approved time-bounded waivers.
9. Keep local engineering qualification separate from case certification. A local build report never edits the 408 result placeholders.
10. For certification, require the independent verifier to sign one request binding all result and evidence-manifest digests, and verify it against a separate non-revoked trust store.

## Required repository outputs

- Executable tests or harness code for this scope
- Fixtures and environment manifests
- Machine-readable results conforming to `test-result.schema.json`
- Raw immutable evidence and replay instructions
- Coverage links for Batches 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37
- Gap and residual-risk records for unsupported cases

## Verification

```bash
python3 scripts/test-suite/validate_test_catalog.py test-suites/batch1-37-strict/cases/catalog.json
python3 scripts/test-suite/validate_coverage_matrix.py test-suites/batch1-37-strict/coverage-matrix.json
python3 scripts/test-suite/run_strict_test_gate.py test-suites/batch1-37-strict
```

Run `make test-suite-check` before the gate. The gate requires `--certification-request`, `--signature`, and `--trust-store` together before it can return `CERTIFIED`.

Also execute the actual repository build, unit, integration, contract, security, behavior, performance, recovery, holdout and representative commands required by each case. A schema-valid JSON file is not execution evidence.

## Stop and escalate when

- A P0/P1 case cannot run against a real or approved equivalent environment.
- Required source, target, policy, ownership, data, security, performance or rollback facts are unknown.
- Passing requires deleting tests, widening masks/tolerances, auto-updating Golden data, broadening permissions, hiding failed assets, or editing certification status directly.
- A critical failure cannot be deterministically replayed or its evidence chain is incomplete.

## Definition of done

- All owned P0/P1 cases pass under the strict profile, with zero critical unknowns, zero integrity violations and complete immutable evidence.
- Independent holdout and representative cases pass without authoring product fixes from holdout data.
- The strict gate derives the result from raw evidence and cannot be bypassed by editing summary status.
