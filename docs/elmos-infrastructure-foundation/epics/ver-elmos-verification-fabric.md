# Verification Fabric: Build, Test, Differential Behavior, Performance, and E1-E5 Certification

- Skill: `elmos-verification-fabric`
- Priority: `P0`
- Phase: `G7`
- Dependencies: `elmos-reproducible-toolchain`, `elmos-semantic-ir-compiler-platform`, `elmos-secure-sandbox-runtime`, `elmos-model-gateway-agent-runtime`

## Objective

Make every generated or transformed project earn its certification through machine-verifiable evidence rather than completion claims.

## Task groups

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

## Validation

- [ ] Run target with deleted/skipped tests and require failure.
- [ ] Inject baseline defects and prove they are not migration regressions.
- [ ] Exercise contract breakage, normalized nondeterminism, numeric tolerance, concurrency, and idempotency.
- [ ] Introduce performance regression and require gate failure.
- [ ] Remove mandatory evidence and require BLOCKED/LIMITED rather than CERTIFIED.

## Exit gate

- [ ] Baseline and migration regressions are separated.
- [ ] Behavior and contract differences are explainable and replayable.
- [ ] Repair cannot game quality gates.
- [ ] Certification status is derived from complete machine evidence.
