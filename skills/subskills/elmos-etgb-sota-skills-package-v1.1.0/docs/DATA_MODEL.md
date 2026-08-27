# ETGB v1.1 result and evidence data model

The canonical production schema is `integrations/postgres/001_etgb_schema.sql` with RLS in `002_etgb_rls.sql`.

## Identity and immutability

Every run binds tenant/account/project/task, frozen candidate digest, immutable plan digest, suite/case versions, corpus snapshots, Environment authority, owner and fencing token. Results from different candidate/plan digests cannot be aggregated as one run.

## Lifecycle

`benchmark_run` and `run_shard` hold current state, revision, lease and fence. `run_transition` is append-only audit. `run_checkpoint` links phase, artifacts, side effects and resume payload through digest chain.

## Case execution

`benchmark_case_run` records seed, attempt, status, failure class, SSER/manual flags, source/target/environment digests, duration and usage. `oracle_result` stores Oracle/normalization versions, criticality, first difference, tolerance and evidence references.

## Evidence

`evidence_artifact` stores logical name, SHA-256, object URI, producer Environment, redaction, encryption/access and retention. `evidence_seal` stores manifest digest, signature/attestation and verification state.

## Cost

`budget_reservation` holds maximum and consumed token/credit/wall-clock. `usage_ledger` is append-only and idempotent. Run totals must reconcile to ledger and provider statements.

## Release and learning

`release_gate_result` and `waiver` produce the exact decision. `failure_cluster` and `regression_link` connect repeated failures, incidents, hidden variants, mutants and fixed candidates.

## Failure taxonomy

- source baseline;
- environment/dependency/supply chain;
- authority/security/tenant;
- budget/quota;
- checkpoint/recovery;
- transform/generate planning;
- target build;
- behavior mismatch;
- state/transaction mismatch;
- security regression;
- performance regression;
- unsupported-undisclosed;
- Harness/Oracle/test defect.

A test/Oracle defect is possible and must be represented explicitly rather than blaming Elmos automatically.
