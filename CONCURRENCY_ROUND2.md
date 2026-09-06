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
| Q1 | P0 | Translation routes use the canonical hosted execution authority | IN_PROGRESS |
| Q2 | P0 | CAS durable I/O outside database transactions with lifecycle protection | IN_PROGRESS |
| Q3 | P0 | Bounded Python compiler/analyzer subprocess output and lifetime | IN_PROGRESS |
| Q4 | P0 | Generation request limit enforced while reading | LOCAL_VERIFIED |
| Q5 | P1 | Multimodal fallback admission held until process/reconciliation completion | LOCAL_VERIFIED |
| Q6 | P1 | ZIP generation/download verification with bounded memory/work | IN_PROGRESS |
| Q7 | P1 | Backward-compatible authenticated streaming encrypted CAS | IN_PROGRESS |
| Q8 | P1 | Bounded batch execution and trusted toolchain identity reuse | IN_PROGRESS |
| Q9 | P1 | Bounded PostgreSQL claim scanning and scheduled reconciliation | LOCAL_VERIFIED |
| Q10 | P1 | Git admission separated from recursive expired-workspace cleanup | LOCAL_VERIFIED |
| Q11 | P1 | Local generation log persistence coalescing/backpressure | LOCAL_VERIFIED |
| Q12 | P2 | Indexed graph association and measured CAS bytes/file/stream selection | IN_PROGRESS |
| Q13 | P2 | Integrated concurrency/correctness and resource-profile qualification | NOT_RUN |

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

- Q4/Q5/Q11: integration replay of the first request/process/log checkpoint:
  13/13 Node tests passed; subsequent tiny-chunk and async abort edge cases are
  included in the final replay list. The process bulkhead is Node-instance local
  (not a distributed capacity guarantee), and retains slots
  until actual child close, including after HTTP timeout.
- Q6 Web: `npm run test:translation-report` passed 29/29 tests on the integrated
  tree, including the real Python report producer, corrupt/duplicate/reordered
  artifacts, asynchronous zlib termination and callback-failure lifecycles.
- Q9: a fresh local PostgreSQL 17.5 database applied migrations 1-82 and V84.
  Nine of ten live cases initially passed; the rotation fixture was corrected
  to put the healthy tenant in a later scheduling round (least-loaded selection
  within the current round was correctly choosing it immediately). The repaired
  rotation case and new V85 fenced metering case then both passed. A clean
  integrated full-suite replay is still required. Scheduling locks/work rows
  are bounded to 32 tenant probes and 128 job candidates per claim, 128 lease
  expiry probes, 64 runner probes and 32 counter reconciliations per scheduled
  reaper transaction. Existing explicit full counter repair remains available.
  Active-state partial indexes avoid counting completed dispatch history;
  bounds on selected/locked work do not imply constant physical query I/O.
- Translation billing compatibility decision remains open: legacy commercial
  usage charges runner minutes even on failed work and releases only the fixed
  conversion credits. The canonical wallet is a different pricing authority.
  V85 supplies a host-fenced pipeline timestamp for the new exact job kind; it
  does not authorize a tariff change, wallet/credits conversion or double charge.
  Existing wallet settlement policies and earlier job kinds remain unchanged.
