---
name: b35-model-based-testing
description: "Implement model-based testing from abstract state command and observation models with transition coverage generation shrinking and source-target conformance."
---

## Operating mode

Work directly in the repository. Inspect existing Batch 21-34 manifests, semantic and framework contracts, tests, behavioral observations, source maps, repair histories, production risks, security policies, and evidence before editing. Implement the smallest production-shaped verification slice that satisfies this skill; do not stop at prose when executable specifications, generators, harnesses, replay, and evidence can be added.

Read these shared contracts first:

- `../../../docs/batch35/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch35/QUALITY_GATES.md`
- `../../../docs/batch35/REPOSITORY_LAYOUT.md`
- `../../../docs/batch35/VERIFICATION_MODEL.md`
- `../../../docs/batch35/ORACLE_GOVERNANCE.md`
- `../../../docs/batch35/SOLVER_AND_SYMBOLIC_POLICY.md`
- `../../../docs/batch35/FUZZING_AND_MUTATION_POLICY.md`
- `../../../docs/batch35/CONCURRENCY_VERIFICATION.md`
- `../../../docs/batch35/ASSURANCE_CASE.md`
- `../../../docs/batch35/SECURITY_AND_DATA_BOUNDARIES.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch35/scaffold_verification_pack.py ...`
- `python3 scripts/batch35/validate_verification_pack.py ...`
- `python3 scripts/batch35/validate_oracle_registry.py ...`
- `python3 scripts/batch35/validate_model_spec.py ...`
- `python3 scripts/batch35/run_verification_gate.py ...`

## Global constraints

- Treat the verification pack as one exact source artifact, target artifact, migration manifest, workload scope, environment, toolchain, solver, corpus, oracle, and policy tuple. Materially different tuples require a new version or pack.
- Use typed specifications and immutable manifests. Do not implement verification as unversioned ad hoc scripts, prose-only checklists, or model-generated assertions without deterministic review.
- Critical claims require independent evidence. An LLM judgment, source implementation behavior, existing test, or single solver result is never automatically the final oracle.
- Preserve development, negative, holdout, representative-workload, and production-regression corpora as separate evidence sets. Never tune generators, thresholds, relations, mutation operators, models, or solver assumptions from holdout results.
- Persist seeds, schedules, models, assumptions, environment digests, tool versions, budgets, timeouts, raw results, minimized counterexamples, and replay commands.
- Treat timeout, unsupported, incomplete, solver unknown, flaky, inconclusive, and missing observation as unknown or blocked, never passed.
- Protect source code, production data, secrets, tenant boundaries, licensed artifacts, and model context under the existing Batch 26 policies.
- Never weaken assertions, delete tests, widen tolerances, change golden masters, suppress critical findings, or exclude failing inputs merely to increase a verification score.
- Bound all fuzzing, symbolic execution, schedule exploration, mutation, and model generation by explicit resource, time, state, and safety budgets.
- Fix systemic defects in contracts, UIR, recipes, generators, comparators, or harnesses rather than patching each generated counterexample independently.
- Run narrow deterministic checks first, then advanced methods, negative tests, holdout, representative workloads, replay, assurance review, and the conservative Batch 35 gate.

## Skill 1272: b35-model-based-testing

## Use this skill when

- Complex workflows are better expressed as commands and abstract state.

## Domain-specific risks and invariants

- A model that mirrors implementation bugs is not independent.

## Workflow

1. Define implementation-independent abstract state, commands, guards, effects, observations, and invariants.
2. Implement adapters for source and target systems.
3. Generate command sequences including invalid and recovery paths.
4. Compare model-predicted and observed states.
5. Shrink failing traces and preserve exact checkpoints.
6. Measure state and transition coverage on holdout traces.

## Required repository outputs

- `verification-packs/<pack-key>/pack.json`, `support-matrix.json`, `validation-profile.json`, and `oracle-registry.json`
- Technique-specific typed specifications, campaigns, raw results, minimized counterexamples, replay manifests, and coverage artifacts
- Independent development, negative, holdout, and representative-workload corpora
- `assurance/assurance-case.json` and `certification/{evidence.json,certification.json,gate-result.json,gate-report.md}`

## Verification

- Run all Batch 35 JSON Schema, pack, oracle, model, and gate validators.
- Execute real source and target artifacts where the technique claims runtime behavior.
- Run negative tests proving the harness detects intentionally injected defects.
- Run untouched holdout and representative workloads without tuning from their results.
- Replay every critical counterexample from its immutable manifest and compare the observed failure fingerprint.
- Verify evidence, coverage, and assurance links resolve to immutable files or approved external references.

## Stop and escalate when

- The exact workload, claim owner, environment, artifact, oracle, or risk profile is missing.
- A technique requires unsafe production mutation, unrestricted customer-data generation, unbounded search, or unapproved external service calls.
- A critical oracle conflict, solver unknown, flaky failure, unreplayed counterexample, or unsupported P0 property remains.
- Verification would require weakening tests, widening tolerances after failure, changing golden behavior, or suppressing critical findings.
- Resource, time, state-space, or data-policy budgets are exceeded.
- Certification evidence is synthetic-only where real runtime, holdout, or representative evidence is required.

## Definition of done

- Model business workflows, resources, sessions, transactions, messages, and lifecycle behavior independently of implementation.
- Repository outputs exist, validate against the Batch 35 contracts, and include exact versioned evidence.
- Negative tests demonstrate that at least one seeded defect is detected by the implemented technique.
- Critical failures have minimized replayable counterexamples and owners.
- Holdout and representative evidence meet the approved validation profile without unresolved P0 unknowns.
- Executable models, command generators, transition traces, conformance results, counterexamples, and model coverage.
- The conservative gate emits only the strongest status supported by actual evidence.
