# Batch 11 progressive production cutover and migration closure

`modules/production-cutover` implements the evidence-bound Batch 11 Production Cutover Control
Model (PCCM). It consumes the same immutable source and target identities used by earlier batches and
admits a target only when Batch 10 reached P-E or P-F with progressive-delivery eligibility.

This repository supplies a control plane, state machine, policy evaluator, evidence model and
append-only acceptance-pack writer. Production routing, schema application, backfill, CDC, write
authority publication, credential revocation and infrastructure destruction are privileged external
operations. They remain `NOT_RUN` in local verification and must be performed by separately authorized
Runners or operators that return attributable evidence.

## PCCM lifecycle

| Phase | Meaning | Required routing shape |
| --- | --- | --- |
| P0 | Prepared | source reads and writes |
| P1 | Schema Expanded | source reads and writes; compatible schema only |
| P2 | Backfill Running | source reads and writes; resumable historical load |
| P3 | Incremental Sync Healthy | source reads and writes; CDC positions healthy |
| P4 | Shadow Read | source serves traffic; target side effects isolated |
| P5 | Read Canary | stable cohorts progressively read target; writes remain source |
| P6 | Target Read Primary | target reads 100%; writes remain source |
| P7 | Write Canary | target reads 100%; stable cohorts progressively write target |
| P8 | Target Write Primary | target reads and writes 100% |
| P9 | Source Read-only | target is system of record; source writes are zero |
| P10 | Hypercare | target remains system of record under continuous observation |
| P11 | Retirement Candidate | traffic, jobs, consumers and dependencies are drained |
| P12 | Decommissioned | an external authority has retired the approved legacy scope |

The state machine permits only the next phase. It evaluates whether a transition is authorized but
always reports `productionChangeExecuted=false`; it cannot apply the transition. Rollback requires a
verified point, source capacity and healthy reverse synchronization. After the recorded irreversibility
frontier, only an approved forward fix may proceed. P12 cannot roll back.

## Non-compensating gates

| Gate | Required evidence |
| --- | --- |
| C-A | complete topology and ownership, safe Expand–Migrate–Contract, complete authoritative inventory/mapping, approved resumable/idempotent backfill and healthy full-operation CDC |
| C-B | verified backfill, bounded CDC lag, reconciled authoritative assets, isolated shadow reads and zero critical read differences |
| C-C | target reads at 100%, stable cohorts, one atomic write-authority registry, no dual primary, all entry points compliant, validated traffic/data rollback and stop triggers |
| C-D | stable write canary, no transaction/security regression, final freeze/drain/delta closure, equal final positions, reconciliation and integration fidelity |
| C-E | target writes at 100% and is system of record, source writes at zero, healthy reverse sync, verified rollback point/capacity and approved irreversibility crossing |
| C-F | completed Hypercare, continuous SLO/data/business acceptance, five-dimension approval, operational handoff, full legacy drain and verified archive/restore/legal hold |
| C-G | P12 observation, target system of record, all five acceptances, credential/DNS/infrastructure/license closure, external decommission evidence, complete audit traceability and zero critical risk |

One failed critical dimension cannot be offset by another. C-G is the sole gate that can set
`migrationCompleted=true`, and only when the target is the system of record and the legacy system is
externally evidenced as decommissioned.

## Implemented boundaries

- `ProductionCutoverAuthorities` defines seven injected evidence ports for topology/schema, data
  migration, traffic, integrations, rollback/incidents, Hypercare/acceptance and retirement.
- `ProductionCutoverService` validates admission and external envelopes, evaluates C-A through C-G,
  and preserves blockers separately from restrictions on the next gate.
- `ProductionCutoverStateMachine` prevents phase skipping and separates transition authorization from
  execution.
- `ProductionCutoverArtifactWriter` writes the specified `cutover`, `waves`, `topology`, `schema`,
  `data-migration`, `traffic`, `dual-run`, `integrations`, `rollback`, `hypercare`, `acceptance`,
  `retirement`, `handoff`, `evidence` and `reports` tree outside both repositories. Writes are atomic,
  append-only and symbolic-link safe; large ledgers use Zstandard.
- The acceptance pack includes executive scope/provenance, data and traffic closure, five acceptance
  dimensions, retirement closure and a final closure report.
- The 14 required reports are wave, backfill, CDC, dual-write, dual-read, traffic-cutover,
  final-reconciliation, rollback-readiness, Hypercare, acceptance, retirement, cost-realization,
  final-closure and Batch 11 conformance.

## Contracts and Skills

The 14 Draft 2020-12 schemas under `contracts/production-cutover-schema` cover the run manifest,
state machine, wave/segment, write authority, data asset/mapping, checkpoint, CDC position, rollback
point, acceptance, retirement, acceptance pack and conformance report. They encode the immutable
artifact, single-primary-writer, no-client-override, durable-checkpoint, no-control-plane-execution and
C-G-only completion invariants.

Skills 240–280 are under `agent-skills/production-cutover`. Their shared protocol requires an approved
production authority for every privileged action and routes each capability to the same module,
contracts and evidence boundary.

## Verification

```bash
mvn -pl modules/production-cutover -am test
python3 /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py agent-skills/production-cutover/<skill>
jq empty contracts/production-cutover-schema/*.json
mvn test
```

The local suite covers admission, all gate blockers, phase/routing consistency, dual-primary and data
loss prevention, rollback/irreversibility, five-dimension acceptance, decommission authority,
append-only output and symbolic-link rejection. It does not change customer data, publish routes,
execute schema changes, revoke credentials, destroy infrastructure, end licenses or decommission a
legacy system.

## Required field evidence before a real C-G claim

1. Immutable Batch 10 target identity, signed provenance and the exact production release identity.
2. Time-bound production topology, owners, callers, direct connections and external partner closure.
3. Applied schema compatibility, committed backfill checkpoints, raw CDC positions and per-asset reconciliation.
4. Cohort routing, read/write percentages, atomic write-authority versions and rollback/forward-fix drills.
5. Message offsets, jobs, sessions, long connections, file hashes, cache isolation and rebuilt index evidence.
6. Hypercare duration, SLO/data/business evidence, incidents, runbooks, on-call and named acceptance records.
7. Drain observations, archive integrity and restore, legal holds, dual retirement approval, credential/DNS/
   infrastructure/license closure and externally executed decommission evidence.

Without these field artifacts, the strongest truthful statement is that the Batch 11 control plane is
implemented and fails closed; a production migration remains `NOT_RUN`.
