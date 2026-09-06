# Concurrency round 2 execution ledger

Baseline: `9dd3567e7bcd9cfaa11cf9786cb4fbf92f486bce` (main, includes PR 87).
Scope: repository-owned remediation of the follow-up concurrency audit. No
production/provider operation, deployment, certification, push or merge is
authorized by this ledger. Existing shared-checkout changes are not inputs.

## Invariants

- Preserve API/format compatibility, tenant/resource authority, fencing,
  cancellation, immutable identities, GC/retirement exclusion and rollback.
- Authenticate and bound resources before expensive work; errors and unknown
  external outcomes must not become success or blind retry.
- Do not remove verification, disable encryption, weaken tests, or replace
  compiler-backed semantics merely to improve a benchmark.
- Independent worktrees own disjoint changes. Integrate commits serially;
  qualify the integrated tree and record failures/skips without hiding them.

## Gap list

| ID | Priority | Repository change | State |
| --- | --- | --- | --- |
| Q1 | P0 | Translation routes use the canonical hosted execution authority | LOCAL_VERIFIED; ACTIVATION_BLOCKED |
| Q2 | P0 | CAS durable I/O outside database transactions with lifecycle protection | LOCAL_VERIFIED |
| Q3 | P0 | Bounded Python compiler/analyzer subprocess output and lifetime | LOCAL_VERIFIED |
| Q4 | P0 | Generation request limit enforced while reading | LOCAL_VERIFIED |
| Q5 | P1 | Multimodal fallback admission held until process/reconciliation completion | LOCAL_VERIFIED |
| Q6 | P1 | ZIP generation/download verification with bounded memory/work | LOCAL_VERIFIED |
| Q7 | P1 | Backward-compatible authenticated streaming encrypted CAS | LOCAL_VERIFIED |
| Q8 | P1 | Bounded batch execution and trusted toolchain identity reuse | LOCAL_VERIFIED |
| Q9 | P1 | Bounded PostgreSQL claim scanning and scheduled reconciliation | LOCAL_VERIFIED |
| Q10 | P1 | Git admission separated from recursive expired-workspace cleanup | LOCAL_VERIFIED |
| Q11 | P1 | Local generation log persistence coalescing/backpressure | LOCAL_VERIFIED |
| Q12 | P2 | Indexed graph association and measured CAS bytes/file/stream selection | LOCAL_VERIFIED |
| Q13 | P2 | Integrated concurrency/correctness and resource-profile qualification | LOCAL_VERIFIED; EXTERNAL_NOT_RUN |
| Q14 | P1 | Review follow-up: bounded host GC with explicit tenant context under ordinary database ownership | METADATA_LOCAL_VERIFIED; PHYSICAL_GC_BLOCKED |
| Q15 | P0 | Review follow-up: Runner container/workspace identity bound to lease and phase | LOCAL_VERIFIED; REAL_CONTAINER_NOT_RUN |

## Evidence boundary

Local replay is engineering evidence only. Production throughput, p95/p99 SLO,
representative multi-host execution and independent verification remain
`NOT_RUN`; certification remains `NOT_CERTIFIED`. Each implementation row needs
actual code plus negative/concurrency regression evidence before closure.

## Local checkpoints

- Q10: short admission transition to an owner-only retirement directory, bounded
  JVM cleanup queue (32 outstanding), restart/rejection replay tickets and
  no-follow confined deletion. Discovery is single-flight outside admission;
  expired reads also retire without recursive deletion on the request thread.
  Targeted Java 21 tests: 17 passed, 0 failed/skipped (Git workspace 13,
  cleanup 3, lock reclamation 1). Replay:
  `JAVA_HOME=/opt/homebrew/opt/openjdk@21 mvn -q -o -f tools/performance/pom.xml -Dtest=GitRepositoryWorkspaceServiceTest,WorkspaceLocksTest,WorkspaceCleanupTest -Dsurefire.failIfNoSpecifiedTests=false test`.
  Coordination remains JVM-local, as before; this is not a shared-filesystem
  multi-host scheduler. Retirement tickets cover process restart/retry, not a
  claim of filesystem power-loss durability on every platform.
  Persistent retirement backlog is separately capped at 128 entries; unknown
  entries consume that budget and are not automatically deleted. A full or
  failed cleanup backlog cannot bypass active workspace capacity indefinitely.

- Q4/Q5/Q11: integration replay of request/process/log checkpoints:
  15/15 Node tests passed, including tiny-chunk and async abort edge cases.
  The process bulkhead is Node-instance local
  (not a distributed capacity guarantee), and retains slots
  until actual child close, including after HTTP timeout.
- Q6 Web: `npm run test:translation-report` passed 29/29 tests on the integrated
  tree, including the real Python report producer, corrupt/duplicate/reordered
  artifacts, asynchronous zlib termination and callback-failure lifecycles.
- Q9: a fresh local PostgreSQL 17.5 database applied migrations 1-82 and V84.
  Nine of ten live cases initially passed; the rotation fixture was corrected
  to put the healthy tenant in a later scheduling round (least-loaded selection
  within the current round was correctly choosing it immediately). The repaired
  rotation case and new V85 fenced metering case then both passed. The first
  integrated full-suite replay
  passed 10/11 queue cases and all 10 CAS publication-pin cases. Its reaper
  fixture shared a database with other short leases that expired during the
  heavily loaded run; these consumed the real global batch. This required
  fixture isolation and a fresh replay, not weaker 128/2 assertions.
  Independent review also identified implicit cursor prefetch in the candidate
  bound and a heartbeat lock-wait/expiry window. Both are now fixed; a fresh
  PostgreSQL database passed the complete 13-case queue class with zero skips,
  including actual lock-count observation and node/job lock-wait expiry cases.
  The reaper isolation retains the original exact assertions. Scheduling bounds are
  32 tenant probes and 128 job candidates per claim, 128 lease
  expiry probes, 64 runner probes and 32 counter reconciliations per scheduled
  reaper transaction. Existing explicit full counter repair remains available.
  Active-state partial indexes avoid counting completed dispatch history;
  bounds on selected/locked work do not imply constant physical query I/O.
- Q2/Q7: V83 publication pins fence retirement/GC while durable storage I/O runs
  without a JDBC connection. Unknown or crashed outcomes remain retained and
  budgeted until trusted reconciliation; elapsed time alone cannot prove a
  remote writer stopped. The integrated 10-case real PostgreSQL pin suite passed.
  The CAS worktree also passed 23 encrypted cases, 20 artifact cases and one
  actual snapshot round-trip. A 128 MiB authenticated encrypted write/read ran
  under a 64 MiB JVM heap. This is a heap-bound check, not RSS or throughput SLO.
  Version 3 streams are fully verified before plaintext is exposed. Legacy v2
  reads retain an explicit bounded whole-object budget and rollback guidance;
  an older binary cannot read v3, and no production format cutover is implied.
- Q3/Q8/Q12: native worktree evidence and raw profiles are recorded in
  `engines/polyglot-route-engine/CONCURRENCY_R2.md`. The original 98-case
  native/cache/Swift/detached selection passed after the cleanup fixture first
  establishes its moved process group; its original 1/2-second transport timeout
  and all cleanup/error assertions remain unchanged. The five fixture variants
  also passed independently on the integrated tree. Official TypeScript batch
  differential tests passed 5/5. Python remains the default CAS backend; the
  8 MiB x 3 shared-host samples do not show a native speed advantage.
- Q13 integrated replay checkpoints: graph/snapshot/resource-budget/ZIP 39 passed;
  final bounded process transport 32 passed. CAS/snapshot portability selection
  collected 51 cases and completed with 48 passes and three explicit platform
  skips (not native backend skips). The native CAS cases did execute with the
  digest-bound existing dylib. The Java backend replay passed 44 selected tests
  (artifact 20, snapshot round-trip 1, Git/cleanup/locks 17, control-plane
  configuration 6), plus 112 legacy Runner self-checks. Its real container
  round-trip remained explicitly skipped; this does not establish deployed
  container-runtime or representative environment evidence.
  Workspace service encryption configuration separately passed 9/9 tests.
  Both host services now pass the shared artifact-size configuration to the
  encrypted CAS constructor and expose the separate legacy decryption budget.
- Translation billing compatibility decision remains open: legacy commercial
  usage charges runner minutes even on failed work and releases only the fixed
  conversion credits. The canonical wallet is a different pricing authority.
  V85 supplies a host-fenced pipeline timestamp for the new exact job kind; it
  does not authorize a tariff change, wallet/credits conversion or double charge.
  Existing wallet settlement policies and earlier job kinds remain unchanged.
- Q1/Q14/Q15 integration review follow-ups: shared PREPARED upload roots cannot
  authorize concurrent or uncertain repeated PUTs; completed idempotent requests
  must not upload again. Global preparation budgets must use private counters,
  not tenant-filtered RLS aggregates. Ordinary database ownership requires an
  exact host-only, bounded tenant GC schedule without BYPASSRLS. Container and
  workspace cleanup must bind the exact lease/phase rather than a reusable job
  name. These are implementation gaps, not production performance measurements.
  The first real launcher attempt exposed a full-manifest/minimal-validator
  mismatch. That failed attempt is not counted as success. The strict full-schema
  and semantic validators were repaired without accepting arbitrary fields or
  materializing the complete ZIP. A retained, real one-unit Python-to-TypeScript
  launcher run then passed (1298 seconds on the heavily loaded shared host),
  including 22 tamper replays that were rejected. A separate read-only replay
  on this integrated branch also returned COMPLETE, repositoryComplete=true:
  artifact SHA-256 `38d9661ad769184e95d1160fc7eb4399fcef202cb0aee66b757e12a2e2676e42`,
  38002 bytes; manifest SHA-256
  `9b2d59c6e66e0e605c9401e6caa4fe51935d2b142efb40ea84066a77a474d4df`.
  The fixture is retained at
  `/private/var/folders/4h/yp1x6drd3y92s2w4pthqh89c0000gn/T/elmos-translation-launcher-ufZwIa`.
  Replay uses `apps/translation-runtime-runner/replay.mjs` and starts no provider
  or Python pipeline. This is one bounded local route fixture, not 156-route,
  real-container, production or independent-verifier qualification.
- Q15: final integrated Java 21 strict compilation (`-Xlint:all -Werror`) and
  `AgentSelfTest` passed all 113 main checks, the 8-worker bounded-process test,
  `ResourceIdentitySelfTest` and 5 phase/input/fencing + 5 pinned-receipt cases.
  The tests include additional JVMs, retained unknown intents, zero subsequent
  claims after unknown cleanup, and cleanup-before-publication. Real container
  round-trip remains explicitly SKIPPED. Drain old runners and use a separately
  owned workRoot for rollout or rollback; legacy sweepers cannot share the new
  namespace. Unknown engine state requires trusted reconciliation, not expiry
  or deletion of the durable intent. See `apps/runner-agent/RESOURCE_IDENTITY.md`.
- Final Web replay: the seven-file selection completed 52 tests with 51 passes,
  zero failures and one explicitly conditional real-receipt skip. A subsequent
  six-case hosted-selection/client replay supplied the retained actual fixture:
  all six passed with zero skips, covering the omitted receipt and the additional
  production no-fallback test. These runs cover 53 distinct passing cases, not
  57 distinct cases. Full-schema report/ZIP validation accounts for 30 of them.
  The exact `npm run test:execution-concurrency` entry point was then replayed
  with that fixture and passed 23/23, zero skips. It is now included in the
  ordinary Web `check` chain already consumed by CI and Makefile targets.
  Final integrated TypeScript 5.9.2 `tsc --noEmit --incremental false` exited 0;
  no permissive type or test-setting change was used to obtain that result.
- Integrated PostgreSQL checkpoint through V88: publication pins 10/10, tenant
  retention metadata 10/10 and translation input protection 8/8 passed with zero
  skips. The final integrated Maven gate exited 0 through V89: queue 13/13,
  input/provisioning 10/10, V89 role hardening 1/1, control-plane translation
  boundary 7/7, physical-GC refusal/provider boundary 7/7 and CAS configuration
  6/6, all with zero skips. Combining distinct PostgreSQL classes across these
  checkpoints gives 44 passing live cases; the final control-plane selection
  supplies another 20 passing cases. Expected fail-closed Spring startup
  exceptions are negative-test outcomes, not suppressed gate failures.
- Physical S3 GC is deliberately **BLOCKED_UPLOAD_FENCING**, not complete:
  a previously issued bearer PUT URL may be replayed or still in flight after
  metadata tombstoning. New upload grants now reject tombstoned/quarantined
  identities and size/backend/key drift, but that cannot revoke old URLs.
  Enabling the host scheduler fails before any metadata/provider effect until
  a trusted backend protocol can prove writer quiescence. V87 supplies only the
  bounded tenant/transaction/retention path. Tests of DELETE 204/404/500 do not
  prove absence of a late writer. See `modules/persistence/OBJECT_GC_HOST.md`.

## Handoff and unresolved activation work

The compatibility, backpressure and transaction-locking Skills guided the
implementation boundaries: preserve existing contracts, bound actual resource
lifetimes, and keep provider I/O outside short fenced database transactions.
The plan is **not fully production-closed**. Remaining requirements are:

1. An approved host-owned translation billing contract. Existing credits and
   wallet pricing are not interchangeable. Commercial hosted mode remains
   refused until that decision and its integration are complete.
2. An exact object-storage provider protocol with trusted upload fencing or
   conservative retention exclusions, plus real runtime validation. Current
   S3 physical GC cannot be enabled safely and remains capability-blocked.
3. A verified, digest-pinned translation image with the exact native toolchains,
   real rootless-container/provider execution, approved database capability
   provisioning and a drained, separately owned Runner workRoot rollout.
4. Representative multi-host load, production p95/p99/RSS/storage budgets,
   browser/runtime journeys and independent evidence. All remain NOT_RUN;
   certification remains NOT_CERTIFIED.

Final local gates use Java 21.0.11, PostgreSQL 17.5, Node 26.0.0 and TypeScript
5.9.2. The isolated database fixture is `elmos_final_r2` on the task-owned
loopback PostgreSQL instance (port 56484); queue fixtures use fixed identities,
so rerun that class in a fresh disposable clone, not by resetting production
data. The local instance is stopped after validation, with its data retained at
`/tmp/elmos-concurrency-r2-pg.aNGXSs/data`. Raw JUnit reports remain in the
relevant module/app `target/surefire-reports` directories; the real translation
fixture and native resource-profile JSON are also retained. The shared original
checkout was not edited. This handoff performs no push, merge or deployment.
