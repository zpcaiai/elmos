# Production Gates

A deployment is not production-certified until these pass in its target environment.

## Correctness
- negative prepaid balance = 0
- duplicate customer charge = 0
- duplicate provider call on idempotent replay = 0
- stale worker successful terminal commit = 0
- unexplained reconciliation delta = 0
- unbalanced journal = 0
- cross-tenant unauthorized read/write = 0

## Recovery
- scheduler restart at RESERVING / RESERVED / DISPATCHING converges
- worker kill resumes from latest durable checkpoint
- Redis flush loses no durable state
- orphan reservations reconcile
- top-up resumes waiting work

## Performance
Initial target gates:
- scheduler claim P95 < 100 ms at declared load
- billing reserve/settle P95 < 150 ms
- progress/meter projection freshness P95 < 2 s

## Operations
- migration rollback/forward plan
- backup + PITR restore drill
- chaos matrix
- billing reconciliation runbook
- SBOM/image provenance
- observability and alerting
