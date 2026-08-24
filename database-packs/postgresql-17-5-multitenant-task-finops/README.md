# PostgreSQL 17.5 multi-tenant task and FinOps runtime

This experimental Batch 31 pack describes the repository-owned, forward-only
V73 schema modernization over the authoritative ELMOS identity, task, runner,
object, usage, and billing aggregates.

The source archive's V100-V102 SQL is not applied. Local PostgreSQL migration
and behavior tests are engineering evidence only. External provider,
representative workload, production migration, cutover, rollback, and
independent certification evidence remain `NOT_RUN`; production status remains
`NOT_CERTIFIED`.
