---
name: elmos-interprocedural-callgraph-resolver
description: "Resolve direct, virtual, interface, reflection-assisted and callback call edges with confidence for repository-scale semantic obligations."
version: 1.0.0
skill_id: ELMOS-POLY-203
layer: call-semantics
risk: critical
readiness: not-run
dependencies:
  - "elmos-overload-dispatch-resolver"
  - "elmos-annotation-attribute-reflection-modeler"
triggers:
  - "Use when implementing or executing `elmos-interprocedural-callgraph-resolver`."
  - "Use when a migration/certification DAG requires `call-semantics` capability."
outputs:
  - "semantic-assurance/elmos-interprocedural-callgraph-resolver/model.json"
  - "semantic-assurance/elmos-interprocedural-callgraph-resolver/evidence.json"
  - "semantic-assurance/elmos-interprocedural-callgraph-resolver/diagnostics.json"
---

# Interprocedural Call Graph Resolver

## Objective

Resolve direct, virtual, interface, reflection-assisted and callback call edges with confidence for repository-scale semantic obligations.

This Skill is an **implementation, execution, and evidence contract**. It must be implemented behind stable code/tooling boundaries. A generated file, prompt response, static package check, or green target build is never by itself evidence of semantic equivalence.

## When to use

- Use when implementing or executing `elmos-interprocedural-callgraph-resolver`.
- Use for repository-scale conversion, modernization, generation, validation, or certification whenever the listed semantic focus can affect observable behavior.
- Invoke it from the route DAG only for the immutable snapshot, dialect/runtime profile, and authorization scope bound to the current run.

## Preconditions

- Immutable source snapshot, source provenance and target profile are bound to the run.
- Source dialect/compiler/runtime identity is known or explicitly `unknown` with a blocker/limitation.
- Relevant upstream IR/evidence artifacts are schema-valid and fresh.
- Source-native baseline exists when executable; unavailable runtimes remain `not-run`, never inferred as pass.
- Readiness starts as `not-run`; waivers require scope, owner, rationale, expiry and compensating evidence.

### Hard dependencies

- `elmos-overload-dispatch-resolver`
- `elmos-annotation-attribute-reflection-modeler`

## Inputs

- `run_id`, `snapshot_id`, route ID, source/target technology and dialect/runtime versions.
- Versioned Project/Semantic/Framework/Behavior IR plus source-span provenance.
- Route semantic-obligation graph and applicable policy/threshold profile.
- Fixture/corpus references and native-runtime evidence relevant to this capability.
- Explicit semantic-loss budget, nondeterminism policy, proof/test budget and approved waivers.

## Outputs

- `semantic-assurance/elmos-interprocedural-callgraph-resolver/model.json`
- `semantic-assurance/elmos-interprocedural-callgraph-resolver/evidence.json`
- `semantic-assurance/elmos-interprocedural-callgraph-resolver/diagnostics.json`

Every output must include snapshot, toolchain/runtime, rule/schema version, evidence timestamp, producer identity and content hash.

## Guardrails

- Never substitute syntax similarity, compilation success, unit-test count or model confidence for semantic evidence.
- Never silently strengthen, weaken or invent source behavior. Unsupported/undefined/implementation-defined behavior must be typed explicitly.
- Never delete failing tests, suppress sanitizer/proof/compiler findings, relax assertions, broaden privileges or normalize away contractual differences.
- Preserve exact source spans and provenance from parser/CST/AST through IR, transform, target code, test and verdict.
- Critical obligations involving money, data integrity, security, concurrency, ABI, numeric precision, encoding, transactions, irreversible effects or safety cannot be waived implicitly.
- Separate **unknown**, **unsupported**, **undefined**, **implementation-defined**, **nondeterministic**, **counterexample**, **failed**, and **waived** states.

## Workflow

1. Determine applicability from source/target dialects, constructs, runtime profile and semantic-obligation registry.
2. Characterize source semantics before transforming; attach source-native evidence where available.
3. Produce deterministic machine-readable semantic artifacts with source spans and confidence.
4. Map source behavior to a target relation: exact equivalence, observational equivalence, permitted refinement, explicit adapter, or blocker.
5. Generate/modify target code only after critical obligations have a verification strategy.
6. Execute route-native static, dynamic, differential, fuzzing and/or formal checks appropriate to risk.
7. On mismatch, emit a reproducible counterexample and minimize it where possible; do not patch blindly.
8. Re-run affected obligations after every patch and invalidate stale downstream evidence.

### Semantic focus

- **static/virtual calls.**
- **callbacks/events.**
- **reflection edges.**
- **external calls.**

## Implementation Contract

- Implement deterministic parser/analyzer/prover/test adapters where native APIs exist; LLM reasoning may orchestrate or explain but is not the semantic source of truth.
- Maintain a versioned `source span → CST/AST/native symbol → semantic IR → obligation → rule/patch → evidence` chain.
- Expose stable CLI/service contracts and machine-readable exit/status semantics.
- Make runs checkpointed, idempotent, resumable and independently reproducible in a trusted runner.
- Use route-specific comparison relations and tolerances; tolerances must never conceal discrete contract changes.
- Cache only against full semantic identity including source/IR/toolchain/solver/runtime/assumption versions.
- Store large/proprietary source outside prompts and logs; evidence references content-addressed artifacts.
- Emit counters/denominators for coverage claims. "100%" is forbidden without an explicit complete denominator.

## Required Tests

- [ ] framework callback fixture.
- [ ] reflection call fixture.
- [ ] unresolved call coverage.
- [ ] same-snapshot deterministic artifact serialization.
- [ ] stale evidence/toolchain/assumption invalidation.
- [ ] at least one positive, one negative, and one boundary/adversarial fixture.
- [ ] missing required evidence remains `not-run` or `blocked`.
- [ ] interrupted execution resumes idempotently from checkpoint.
- [ ] unauthorized filesystem/network/secret/tool access is rejected.

## Verification

1. Validate outputs against versioned schemas and the route semantic-obligation graph.
2. Run source-native characterization and target-native checks in matched, attested environments where required.
3. Execute independent oracles where feasible; correlate rather than collapse contradictory evidence.
4. Reproduce every critical mismatch/counterexample from a clean checkpoint.
5. Verify evidence freshness against snapshot, rule, IR, runtime, compiler, solver and corpus identities.
6. Record precise scope and limitations; passing this Skill never certifies unrelated modules/routes.

## Stop and Escalate

Stop safely when a critical semantic obligation is unknown, source behavior cannot be characterized, required native runtime is unavailable, proof returns an unresolved critical counterexample, nondeterminism prevents a stable oracle, or route budgets are exhausted.

Return a structured blocker containing affected symbols/modules, source spans, semantic category, counterexample/evidence, severity, owner, safe alternatives and the exact implementation/approval needed.

## Definition of Done

- [ ] Stable implementation interface and versioned configuration exist.
- [ ] Applicable semantic obligations are enumerated with explicit statuses.
- [ ] Representative and adversarial fixtures execute in required native environments.
- [ ] Static/dynamic/differential/formal evidence required by route policy is fresh.
- [ ] Critical counterexamples are fixed or explicitly blocked; no unresolved critical mismatch is hidden by tolerance.
- [ ] Coverage includes denominators for syntax/semantic/runtime/corpus dimensions.
- [ ] Residual semantic loss and waivers are explicit, scoped and reviewable.
- [ ] Evidence is bound to the same snapshot/route/toolchain/runtime/assumptions.
- [ ] Readiness is derived from executed gates and cannot be inferred from artifact presence.

## Completion Report

Return machine-readable plus human-readable results with run/snapshot/route IDs, source and target dialect/runtime identities, applicable obligations, commands and exit codes, fixture/corpus IDs, source-target observables, proof/fuzz/mutation results, counterexamples, coverage numerators/denominators, waivers, residual risks, artifact hashes and next executable actions.

Final execution status must be one of `completed`, `completed-with-approved-exceptions`, `blocked`, or `failed`. Never emit `completed` while any required gate is `not-run`.
