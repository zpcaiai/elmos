# Batch 11 production cutover and closure protocol

This reference is normative for every Batch 11 Skill. The machine authority is
`modules/production-cutover`; schemas live in `contracts/production-cutover-schema`.

## Admission and authority

- Admit only a fixed source artifact and an immutable target artifact with Batch 10 P-E or P-F
  progressive-delivery eligibility. Bind every production observation and action to those artifacts,
  the cutover run, Wave, phase, segment and timestamp.
- Engineering, operations, security and business approvals must be current before production work.
  Irreversibility and decommission require their own named approvals. An Agent cannot approve or waive.
- The PCCM control plane evaluates evidence and authorizes transitions. Only approved external
  production Authorities may change routes, schemas, data, offsets, jobs, credentials or infrastructure.
  A control-plane or Skill must never directly perform those privileged actions.
- External Authority failure, missing evidence or mismatched production state is blocked. Preserve the
  exception class, not potentially secret-bearing exception messages.

## PCCM state machine

Use the ordered phases P0 Prepared, P1 Schema Expanded, P2 Backfill Running, P3 Incremental Sync
Healthy, P4 Shadow Read, P5 Read Canary, P6 Target Read Primary, P7 Write Canary, P8 Target Write
Primary, P9 Source Read-only, P10 Hypercare, P11 Retirement Candidate and P12 Decommissioned.

Every phase records actual read/write routing, source of truth, stable cohort key, synchronization
direction, positions and lag, stop triggers, rollback point, irreversibility state, owner and maximum
duration. Never skip a phase or call a phase complete when observed routing differs.

## Non-negotiable migration rules

- One aggregate and segment has exactly one authoritative writer at any instant. All HTTP, message,
  job, retry, admin and repair entry points consume the same versioned Authority Registry. Clients
  cannot select the writer. Prefer single writer plus CDC/outbox over independent dual writers.
- Separate read and write cutover. Use safe Shadow Read, bounded dual read, stable read canaries and
  target read primary before moving any write authority.
- Apply Expand–Migrate–Contract. Do not contract while an old application, consumer, rollback path,
  archive or external caller still needs the old schema.
- Backfill is partitioned, idempotent, throttled, checkpointed after target commit, resumable and
  side-effect-free. CDC records start/final/applied positions and handles insert, update, delete,
  duplicate, out-of-order and schema versions.
- Stop expansion on any critical data, authorization, tenant, transaction or message difference;
  data loss; uncontrolled duplicate; repeated job; excessive lag; failed reverse sync; or SLO burn.
- Never traffic-roll back beyond the irreversibility frontier. Use an approved, audited forward-fix or
  compensation path when source cannot safely accept target data or external effects have occurred.
- Decommission only after source business traffic, writes, consumers and jobs are zero; callers and
  direct database connections are closed; archives restore; Legal Holds remain; and the receiving
  team can operate the target independently. Destruction always occurs through an external Authority.

## Gate meanings

| Gate | Minimum production evidence |
| --- | --- |
| C-A | complete topology/data inventory and mapping, compatible schema expansion, approved resumable backfill and healthy CDC |
| C-B | verified backfill, bounded CDC lag, safe Shadow Read, zero critical read difference |
| C-C | stable target read primary, single write Authority, integration/session readiness and drilled rollback |
| C-D | stable write canary, final delta/positions/reconciliation, zero critical data/message/job/security regression |
| C-E | target receives 100% writes and is System of Record, source writes are zero, reverse sync and rollback point are healthy |
| C-F | Hypercare exits, source traffic/work is drained, hidden dependencies are zero, archive restores and retirement is approved |
| C-G | all five acceptances, externally executed decommission, credentials/routes/infrastructure/licenses closed, audit pack and benefit tracking complete |

Only C-G may set `migration_completed=true`. One hundred percent traffic, a stopped application or a
database archive alone is not completion.

## Evidence and handoff

- Distinguish `PASSED`, `FAILED`, `NOT_RUN`, `BLOCKED`, `INCONCLUSIVE` and `NOT_APPLICABLE`.
- Store append-only, redacted evidence outside both repositories. Include raw Authority references,
  configuration and tool versions, phase/route snapshots, approvals, positions, conflicts, incidents,
  manual actions, archive hashes and restore results.
- Never average away a failed asset, Wave, aggregate, acceptance dimension or retirement asset.
- Keep open risks, approved differences, conditional items, owners and expiry visible through closure.
- Schedule benefit reviews using measured pre-migration baselines and real post-cutover outcomes.
