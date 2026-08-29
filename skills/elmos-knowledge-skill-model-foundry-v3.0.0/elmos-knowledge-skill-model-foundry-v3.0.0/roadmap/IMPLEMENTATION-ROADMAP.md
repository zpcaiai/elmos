# Elmos Foundry v3 Implementation Roadmap

## Gate A — Cross-kernel contracts and authority

- typed Task/Skill/Evidence/Release contracts;
- tenant, repository, environment, attachment and workspace identity;
- environment-owned authority, lease/fencing, idempotency and compensation;
- immutable audit, data-use consent and training prohibition by default.

**Exit:** live PostgreSQL/RLS, policy engine, secrets broker and replayable audit tests pass.

## Gate B — Repository Execution OS

- repository intake, build detection, hermetic environment, worktree/patch stack;
- semantic sharding, parallel agents, conflict prediction and semantic merge;
- pause/resume/cancel, executor failover, offline continuation and Wall-clock ETA.

**Exit:** three large-repository fixtures complete without double execution, lost state or unverifiable patches.

## Gate C — Semantic IR and adapter foundation

- language/build, database, framework and cloud adapter SDKs;
- AST, symbol, call, data, transaction, security, UI, dataflow and deployment IR;
- support matrix with version-pinned conformance suites.

**Exit:** each claimed adapter passes parser, build, runtime and round-trip tests for explicitly supported versions.

## Gate D — Autonomous QA and Evidence

- characterization, contract, differential, property, mutation, fuzz, concurrency, performance, security and chaos tests;
- independent verifier, Evidence Bundle, test adequacy and no-test-weakening controls.

**Exit:** E0–E3 repeatable in clean environments; deliberately faulty transformations are rejected.

## Gate E — First commercial Golden Routes

1. SQL dialect/Routine + data migration;
2. Spring/Java enterprise modernization;
3. automated QA and certification;
4. repository execution and recovery.

**Exit:** at least three disjoint real repositories per route, including large-repository coverage, pass shadow/cutover/rollback rehearsals.

## Gate F — Expanded business lines

- cross-language repository conversion;
- full project generation;
- frontend/mobile/four mini-app targets;
- refactoring, API/event, data/lakehouse, cloud, AI Agent/RAG, legacy and industrial packs.

**Exit:** each enabled line has a version support matrix, customer acceptance contract, pricing model and E3+ evidence.

## Gate G — Commercial platform and private deployment

- entitlements, prepaid wallet, subscriptions/project pricing, metering and reconciliation;
- dedicated tenant, private cloud and air-gapped bundles;
- customer portal, evidence room, SLA, support and offboarding.

**Exit:** end-to-end accounting, tenant isolation, backup/restore, update and license tests pass.

## Gate H — E4/E5 production certification

- shadow, canary, long soak, chaos, disaster recovery, security red team and model/data/knowledge drift;
- whole-release rollback and recertification triggers;
- Golden Route repeatability, supportability and customer acceptance.

**Exit:** only explicitly certified technology/version/business-line combinations are exposed as production-supported.

## Non-negotiable status rule

A Skill is not production-ready merely because its YAML and evaluation fixtures validate. `specification-ready → implemented → E1/E2 validated → E3 shadow-ready → E4 canary-ready → E5 Golden Route` is mandatory.
