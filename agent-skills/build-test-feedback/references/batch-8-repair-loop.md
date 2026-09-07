# Batch 8 bounded repair-loop protocol

## Contents

1. Admission and evidence boundary
2. Controlled execution workflow
3. Diagnostic, cluster and attribution rules
4. Repair planning and patch safety
5. Test migration and regression rules
6. Progress, budget and stop decisions
7. Gates, artifacts and completion claims

## 1. Admission and evidence boundary

Require a frozen source baseline, Batch 7 F-D admission, target Snapshot, target module map,
open Semantic Obligations, approved target dependencies and an explicit repair policy. Keep the
migration artifact workspace outside the target repository. Reject a symlinked target root,
missing source evidence, incomparable baselines and blocking obligations without a strategy.

Treat build, compiler, static-analysis and test claims as external evidence. Use the
`RepairLoopModels.ExecutionAuthority` port only with an approved isolated runner. Use
`DeterministicRepairAuthority`, `AgentRepairAuthority` and `TransactionalPatchAuthority` only as
capability boundaries. The core does not execute host commands, install packages, contact a
registry, start an application or edit the target repository itself.

Never convert `NOT_RUN`, `BLOCKED` or `INCONCLUSIVE` into success. Never infer a successful test
run from an exit code without discovery and report evidence. Never count source-existing failures
as migration regressions, and never assume an unexecuted source test passed.

## 2. Controlled execution workflow

Use this order:

1. Validate source/target Snapshots, Batch 7 admission and open obligations.
2. Build a minimum sufficient matrix for every declared deployment platform.
3. Resolve project wrappers, lock-preserving commands, tool versions and report paths.
4. Restore dependencies in a restricted sandbox with approved registries only.
5. Load the build graph, compile, run static analysis and discover tests.
6. Run layered tests and normalize every failure.
7. Cluster by root cause and compare with the source baseline.
8. Select one root-cause cluster and one primary repair plan.
9. Try a tested deterministic recipe before a bounded Agent patch when policy permits.
10. Apply the patch atomically to an isolated candidate Snapshot.
11. Parse, compile and test the affected scope, then run dependent and full regression.
12. Evaluate improvement, roll back unsafe/regressive work and update progress history.
13. Stop on convergence, risk, environment, budget, oscillation, no progress or human decision.
14. Require the configured number of matching clean-environment full runs before R-D.

Do not run a Cartesian product by default. Cover every target deployment platform and every
declared target framework/runtime combination, then document why other dimensions were omitted.
High-risk security modules cannot be removed to reduce cost.

## 3. Diagnostic, cluster and attribution rules

Preserve the native tool, native code, redacted original message, phase, module, location,
symbol/dependency/declaration association and raw evidence reference. Normalize volatile host
paths, timestamps, IDs and line numbers for fingerprinting without erasing the original location.
Redact secret values before persistence.

Classify failures into environment, dependency, build configuration, syntax, symbol, type,
generic, nullability, API mapping, framework, static analysis, test discovery/compilation/fixture/
assertion, runtime, database, messaging, security, performance, flaky, source baseline or unknown.
Keep unknown when evidence is insufficient. Security is P0 by default; build and critical
contract blockers are P1.

Cluster on causal evidence such as the missing package/symbol, upstream project, declaration,
first failing phase, mapping rule or source test. Do not merge on message similarity alone. Keep
security findings separate from style findings. Preserve cluster history when membership changes.

Assign one of: `SOURCE_EXISTING`, `MIGRATION_INTRODUCED`, `TARGET_ENVIRONMENT`,
`DEPENDENCY_INFRASTRUCTURE`, `TEST_MIGRATION`, `TEST_FLAKY`, `UNKNOWN` or `MIXED`. Record evidence
and confidence. Critical unknown failures block automation.

## 4. Repair planning and patch safety

Use this preference order: environment correction, deterministic configuration recipe,
deterministic code recipe, mapping-rule correction, adapter/helper, regeneration, bounded Agent
patch, human decision. Bind every plan to one cluster, allowed files/declarations, invariants,
local/full validations and a rollback Snapshot.

Reject a patch that:

- is not bound to the plan, cluster and current Snapshot;
- crosses an allowed file/declaration or generated/manual boundary;
- silently changes a public API, security, transaction or serialization contract;
- deletes a test, weakens an assertion or turns a source skip into a permanent skip;
- adds global suppression, `any`, `dynamic`, unsafe casts or exception swallowing;
- adds an unapproved dependency or fabricates a lockfile;
- exceeds file, line, Agent-call, token, cost or time limits;
- lacks before/after hashes, atomic application, rollback or evidence;
- is an unreviewed high-risk Agent change.

Require an independent parser/compiler and test authority. An Agent cannot validate its own patch.
Roll back Level 3 contract regressions and Level 4 security/transaction/data regressions. Preserve
evidence for failed and rolled-back patches.

## 5. Test migration and regression rules

Map every source test to an explicit target state: translated-and-passed, translated-and-failed,
translated-and-flaky, translated-and-skipped-with-reason, replaced-by-equivalent-test,
covered-by-contract-test, source-existing-failure, not-applicable-with-proof, manual-required or
unmapped. Do not use vague `done`, `ignored` or `probably-covered` states.

Preserve setup/teardown, parameters, assertions, exception type/message/cause, async behavior,
timeouts, mock calls/order, snapshots, random seed, fake clock and fixture lifecycle. Keep database
fixtures isolated and production credentials prohibited. A zero-test discovery result is blocking,
not a green run.

Run affected tests first, then same-type, module, dependent modules, contracts/integration and the
full regression. Cache only against Snapshot, tool version, configuration, dependency lock,
environment and selection hashes. Never cache a flaky result as stable or use incremental results
instead of the final full gate.

Quarantine flaky tests only with owner, cause, expiry and continued reporting. Do not count a retry
that eventually passes as stable. Do not quarantine critical security or transaction tests to pass
a gate.

## 6. Progress, budget and stop decisions

Record each round's blocking errors, migration regressions, required-test pass/fail counts,
diagnostic-set hash, Snapshot and patch outcome. Mark a patch effective only when it removes the
root cause without introducing contract/risk regression. Treat error hiding as unsafe.

Detect repeated patch IDs/content, Snapshot cycles, diagnostic-set cycles and three consecutive
rounds without blocking-error or required-test improvement. Stop the repeated strategy, restore
the last stable Snapshot and build a human escalation packet.

Reserve budgets per repository, module, cluster and Agent call. Attribute calls, tokens, cost,
wall time, patch attempts and rollbacks. Exhausting one cluster budget must not consume the whole
repository budget. Budget exhaustion never permits a completion claim.

Use only the declared terminal outcomes. Partial convergence must name every remaining failure,
owner, fallback and restriction. Preserve the last stable Snapshot for every outcome.

## 7. Gates, artifacts and completion claims

- R-A: reproducible dependency restore/build-model load, compile rate at least 0.95 and no blocking
  build-configuration error.
- R-B: R-A plus symbol rate at least 0.98, type rate at least 0.97, no critical static finding and
  no public-API regression.
- R-C: R-B plus complete discovery, required-test migration/execution thresholds, unit pass rate at
  least 0.95, critical contract pass rate 1.0 and no unclassified failed test.
- R-D: full compile, no blocking static or required migration regression, no critical security
  finding, no open blocking obligation, no unreviewed high-risk Agent patch, full regression and
  the configured matching clean-environment runs.
- R-E: optional high-automation candidate thresholds; never weaken R-D to reach it.

Evaluate each module independently. Repository averages cannot hide a critical module. R-D admits
the module to Batch 9 behavioral/differential validation; it does not prove production safety,
deployment readiness or behavioral equivalence.

Write the manifest, matrix, commands, diagnostics, clusters, attribution, plans, progress, stop
decision, patches, test evidence, escalation packets and reports outside the target repository.
Use compressed JSONL for high-volume streams, atomic writes, symlink rejection and secret-redacted
evidence. Use `modules/repair-orchestration` as the authoritative Batch 8 control-plane contract.
