# Database Roles

Recommended roles:

- elmos_identity_rw
- elmos_project_rw
- elmos_scheduler_rw
- elmos_runtime_worker_limited
- elmos_billing_rw
- elmos_projector_limited
- elmos_readonly_analytics
- elmos_migration_admin

Worker role must not write billing tables.
Scheduler role must not mutate wallet/ledger directly.
Projector role must not mutate authoritative orchestration or billing truth.
