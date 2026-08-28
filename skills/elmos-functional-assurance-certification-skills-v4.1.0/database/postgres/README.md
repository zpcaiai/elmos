# PostgreSQL 17 persistence contract

The migrations model solution revisions, target portfolios, generated repositories, unsupported features, normalized traces, proof obligations/results, evidence, certificates, durable runs, fenced steps, side effects and FinOps.

## Mandatory deployment checks

1. Run on PostgreSQL 17 in a disposable database and then an upgrade fixture.
2. Verify RLS with at least two tenants and a missing `app.tenant_id`.
3. Test stale fencing writes, duplicate idempotency keys and transactional outbox/reconciliation integration.
4. Back up and restore a paused run, evidence bundle and certificate.
5. Record migration image digest, SQL hash, command, exit code and database version.

The package does not claim these migrations have executed in the target Elmos environment.
