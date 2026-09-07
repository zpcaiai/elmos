# AGENTS.md — Elmos Multi-Tenant Task Control & FinOps

## Mission

Implement this package in the target Elmos repository without weakening the hard account-wide limit of three active root tasks, tenant isolation, recovery correctness, or append-only financial ledgers.

## Start here

1. Read `README.md`, `docs/PRODUCT-REQUIREMENTS.md`, and `docs/REFERENCE-ARCHITECTURE.md`.
2. Run `./verify.sh` to validate this specification package.
3. Invoke `$elmos-multitenant-task-finops-orchestrator` against the target repository.
4. Produce `IMPLEMENTATION_PLAN.md` and a repository gap analysis before editing code.
5. Implement Skills in manifest dependency order.
6. Run repository-specific tests and bind every completion claim to executable evidence.

## Hard invariants

- Maximum active root tasks per authenticated account is exactly 3 across all tenant memberships.
- A fourth task is durably accepted as `WAITING_FOR_SLOT`; it is not dropped or started.
- PostgreSQL is authoritative for slot admission; Redis cannot be the sole lock.
- Tenant authorization comes from verified identity and membership, never a trusted client header.
- Normal runtime database roles are non-superuser, non-owner, and do not have `BYPASSRLS`.
- Critical task, checkpoint, side-effect, usage, and revenue events are persisted before acknowledgement.
- Retries and recovery use lease generation/fencing and idempotency receipts.
- Cost, billed value, recognized revenue, and collected cash remain separate.
- Historical financial records are corrected by compensating entries, not destructive updates.
- System machine wall-clock runtime is reported separately from human effort and human waiting time.

## Repository workflow

- Freeze API, event, schema, state-machine, identity, pricing, and retention contracts first.
- Prefer a thin vertical slice: submit → queue/admit → Temporal start → node progress → checkpoint → finish → usage → revenue → analytics.
- Add abnormal paths before scaling feature breadth.
- Keep schema migrations backward-compatible and include rollback/forward-fix strategy.
- Do not remove existing functionality or overwrite unrelated user changes.

## Required evidence

For each stable task ID in `docs/TASK-MATRIX.csv`, capture:

- repository commit SHA;
- changed files and migration versions;
- commands executed and exit status;
- machine wall-clock duration;
- tests, traces, task/run IDs, event sequences, and ledger IDs;
- assumptions, known limitations, residual risks, waiver owner, and waiver expiry.

## Release rule

Do not state that production readiness is achieved until `$elmos-concurrency-recovery-finops-certification` has produced repository-specific evidence and all hard gates in `docs/ACCEPTANCE-GATES.md` pass.
