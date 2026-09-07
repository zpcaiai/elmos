---
name: elmos-verification-fabric
description: Build a unified verification plane that distinguishes baseline defects
  from migration regressions and proves target behavior, contracts, performance, security,
  and resilience.
version: 1.0.0
priority: P0
phase: G7
dependencies:
- elmos-reproducible-toolchain
- elmos-semantic-ir-compiler-platform
- elmos-secure-sandbox-runtime
- elmos-model-gateway-agent-runtime
---

# Verification Fabric: Build, Test, Differential Behavior, Performance, and E1-E5 Certification

## Objective

Make every generated or transformed project earn its certification through machine-verifiable evidence rather than completion claims.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Verification Fabric: Build, Test, Differential Behavior, Performance, and E1-E5 Certification** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-reproducible-toolchain`
- `elmos-semantic-ir-compiler-platform`
- `elmos-secure-sandbox-runtime`
- `elmos-model-gateway-agent-runtime`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- A failing or incomplete baseline is reported, never hidden.
- Tests may not be deleted, skipped, weakened, or rewritten merely to manufacture success.
- Behavioral tolerances must be explicit, versioned, and approved.
- Certification is conservative when evidence is missing or ambiguous.

## Required inputs

- Source and target snapshots/toolchains.
- Build/test/contract/runtime scenarios and tolerances.
- Symbol/IR mappings and known gaps.
- Security, performance, resilience, and approval policies.

## Required outputs

- `Unified baseline and validation results.`
- `Contract/behavior/performance/security diffs.`
- `Selected/full test evidence and repair feedback.`
- `Known deviations, risk decisions, and E1-E5 status.`

## Repository discovery

Before editing:

1. Locate `AGENTS.md`, `CLAUDE.md`, repository-local Skills, architecture decision records, manifests, schemas, migrations, and build commands.
2. Identify actual control-plane, workflow, runner, engine, web, database, object-store, policy, telemetry, and test modules; do not assume the reference layout exists.
3. Search for existing contracts and implementations before creating duplicates.
4. Record current behavior, known gaps, security boundaries, external side effects, and the exact validation commands that are available.
5. Create or update a durable implementation plan from `templates/IMPLEMENTATION-PLAN.yaml`.

## Execution workflow

1. Select the smallest dependency-resolved vertical slice.
2. Freeze input snapshots, schema/toolchain/policy versions, and rollback boundaries.
3. Implement contract/schema changes before consumers, using backward-compatible transitions.
4. Implement production behavior, authorization, idempotency, telemetry, audit, failure handling, tests, documentation, and runbooks together.
5. Execute focused tests, integration tests, race/failure tests, security tests, and clean-environment reproduction as applicable.
6. Save large outputs by digest; record commands, results, durations, cost, evidence, and residual risk.
7. Report autonomous **system wall-clock runtime** separately from human-equivalent engineering/review effort.
8. Never claim production completion from generated files or static validation alone.

## Implementation checklist

### Baseline capture

- [ ] `ELMOS-VER-001` Reproduce source build in a sealed environment and classify environment, dependency, code, private-registry, infrastructure, and flaky failures.
- [ ] `ELMOS-VER-002` Record modules, build artifacts, discovered/executed/passed/failed/skipped tests, APIs, database/message schemas, side effects, performance, and resource profile.
- [ ] `ELMOS-VER-003` Freeze baseline snapshot/toolchain/scenario/tolerance digests.
- [ ] `ELMOS-VER-004` Separate pre-existing failures from migration regressions.
- [ ] `ELMOS-VER-005` Block unsupported claims when no trustworthy baseline can be captured.
### Compile and test normalization

- [ ] `ELMOS-VER-006` Run target compile, unit, integration, end-to-end, static analysis, lint, and package checks through language adapters.
- [ ] `ELMOS-VER-007` Normalize JUnit, pytest, dotnet, Go, Rust, JS, and other reports into versioned schemas.
- [ ] `ELMOS-VER-008` Track discovered test count and flag deletion/skip/selection changes.
- [ ] `ELMOS-VER-009` Classify failures before invoking agents.
- [ ] `ELMOS-VER-010` Use incremental test selection with conservative full-suite escalation.
### Contract verification

- [ ] `ELMOS-VER-011` Diff OpenAPI, GraphQL, Protobuf/gRPC, database schemas, events/messages, CLI, configuration, files, and public symbols.
- [ ] `ELMOS-VER-012` Classify compatible, potentially breaking, and breaking changes with affected consumers.
- [ ] `ELMOS-VER-013` Require approval and Known Deviation evidence for accepted breakage.
- [ ] `ELMOS-VER-014` Link every difference to source/target symbols and transformation provenance.
### Differential behavior

- [ ] `ELMOS-VER-015` Execute identical scenarios against baseline and target.
- [ ] `ELMOS-VER-016` Compare return values, errors, state/database changes, messages, files, logs/events, timing constraints, and external-effect intents.
- [ ] `ELMOS-VER-017` Normalize IDs, timestamps, ordering, randomness, locale, and nondeterministic fields only through explicit rules.
- [ ] `ELMOS-VER-018` Support exact, set/order-aware, absolute/relative numeric, temporal, and domain tolerances.
- [ ] `ELMOS-VER-019` Store minimized counterexamples and map them to symbols/IR/rules.
### Advanced validation

- [ ] `ELMOS-VER-020` Add golden snapshots, property-based tests, metamorphic tests, coverage-guided fuzzing, boundary/unicode/timezone/locale cases, serialization compatibility, transaction rollback, retry/idempotency, concurrency/race, and resource-leak tests.
- [ ] `ELMOS-VER-021` Use SMT/constraint checking for selected high-risk invariants.
- [ ] `ELMOS-VER-022` Model workflow/lease/recovery protocols with state-machine or formal specifications where valuable.
- [ ] `ELMOS-VER-023` Persist seeds and minimized cases for deterministic replay.
### Performance equivalence

- [ ] `ELMOS-VER-024` Define P50/P95/P99 latency, throughput, CPU, memory, disk, network, startup/cold-start, and cost thresholds.
- [ ] `ELMOS-VER-025` Run baseline and target with equivalent resources, warmup, dataset, load, and environment.
- [ ] `ELMOS-VER-026` Repeat runs, report uncertainty/noise, and distinguish statistical regression from fluctuation.
- [ ] `ELMOS-VER-027` Block promotion on unapproved regression and record approved tradeoffs.
- [ ] `ELMOS-VER-028` Link profiles and bottlenecks to commits/toolchains.
### Repair feedback

- [ ] `ELMOS-VER-029` Send only classified/minimized failures plus relevant context to an agent.
- [ ] `ELMOS-VER-030` Create isolated patch digest per iteration and rerun minimum valid checks.
- [ ] `ELMOS-VER-031` Escalate to full validation at risk thresholds and before certification.
- [ ] `ELMOS-VER-032` Reject repair attempts that delete tests, weaken assertions, disable security, or hide errors.
- [ ] `ELMOS-VER-033` Stop repeated/non-improving loops and create explicit human work.
### E1-E5 certification

- [ ] `ELMOS-VER-034` Define E1 buildable, E2 tests/contracts, E3 behavioral equivalence, E4 performance/security/resilience, and E5 shadow/canary/production migration evidence.
- [ ] `ELMOS-VER-035` Define mandatory evidence, tolerance, sample, approval, and expiry for each level.
- [ ] `ELMOS-VER-036` Emit CERTIFIED, LIMITED, EXPERIMENTAL, or BLOCKED with exact reasons.
- [ ] `ELMOS-VER-037` Never promote to a level with missing mandatory evidence.
- [ ] `ELMOS-VER-038` Support recertification after source, target, toolchain, rule, model, policy, or environment changes.

## Required artifacts

At minimum, produce or update:

- Versioned contracts and schemas.
- Database migrations and compatibility/rollback notes where state changes.
- Production implementation with explicit authorization, idempotency, retries, cancellation, and failure classification as applicable.
- Unit, integration, end-to-end, race/failure, and security tests appropriate to risk.
- OpenTelemetry instrumentation, operational metrics, alerts, and runbooks for production components.
- Audit/evidence records with immutable input and output digests.
- Updated architecture and operational documentation.
- Task report based on `templates/TASK-REPORT.md`.

## Validation

- [ ] Run target with deleted/skipped tests and require failure.
- [ ] Inject baseline defects and prove they are not migration regressions.
- [ ] Exercise contract breakage, normalized nondeterminism, numeric tolerance, concurrency, and idempotency.
- [ ] Introduce performance regression and require gate failure.
- [ ] Remove mandatory evidence and require BLOCKED/LIMITED rather than CERTIFIED.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Baseline and migration regressions are separated.
- [ ] Behavior and contract differences are explainable and replayable.
- [ ] Repair cannot game quality gates.
- [ ] Certification status is derived from complete machine evidence.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
