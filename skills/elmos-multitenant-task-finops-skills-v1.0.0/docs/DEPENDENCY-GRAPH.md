# Dependency Graph

```mermaid
graph TD
    elmos_multitenant_task_finops_orchestrator["ELMOS-MTF-001<br/>elmos-multitenant-task-finops-orchestrator"]
    elmos_tenant_identity_rls["ELMOS-MTF-002<br/>elmos-tenant-identity-rls"]
    elmos_account_concurrency_admission["ELMOS-MTF-003<br/>elmos-account-concurrency-admission"]
    elmos_workload_aware_scheduler["ELMOS-MTF-004<br/>elmos-workload-aware-scheduler"]
    elmos_task_lifecycle_temporal["ELMOS-MTF-005<br/>elmos-task-lifecycle-temporal"]
    elmos_task_progress_journal["ELMOS-MTF-006<br/>elmos-task-progress-journal"]
    elmos_checkpoint_recovery["ELMOS-MTF-007<br/>elmos-checkpoint-recovery"]
    elmos_task_io_artifact_archive["ELMOS-MTF-008<br/>elmos-task-io-artifact-archive"]
    elmos_usage_metering_cost_ledger["ELMOS-MTF-009<br/>elmos-usage-metering-cost-ledger"]
    elmos_revenue_margin_ledger["ELMOS-MTF-010<br/>elmos-revenue-margin-ledger"]
    elmos_task_financial_analytics["ELMOS-MTF-011<br/>elmos-task-financial-analytics"]
    elmos_concurrency_recovery_finops_certification["ELMOS-MTF-012<br/>elmos-concurrency-recovery-finops-certification"]
    elmos_multitenant_task_finops_orchestrator --> elmos_tenant_identity_rls
    elmos_tenant_identity_rls --> elmos_account_concurrency_admission
    elmos_account_concurrency_admission --> elmos_workload_aware_scheduler
    elmos_workload_aware_scheduler --> elmos_task_lifecycle_temporal
    elmos_task_lifecycle_temporal --> elmos_task_progress_journal
    elmos_task_lifecycle_temporal --> elmos_checkpoint_recovery
    elmos_task_progress_journal --> elmos_checkpoint_recovery
    elmos_task_progress_journal --> elmos_task_io_artifact_archive
    elmos_checkpoint_recovery --> elmos_task_io_artifact_archive
    elmos_task_io_artifact_archive --> elmos_usage_metering_cost_ledger
    elmos_usage_metering_cost_ledger --> elmos_revenue_margin_ledger
    elmos_usage_metering_cost_ledger --> elmos_task_financial_analytics
    elmos_revenue_margin_ledger --> elmos_task_financial_analytics
    elmos_account_concurrency_admission --> elmos_concurrency_recovery_finops_certification
    elmos_workload_aware_scheduler --> elmos_concurrency_recovery_finops_certification
    elmos_task_lifecycle_temporal --> elmos_concurrency_recovery_finops_certification
    elmos_task_progress_journal --> elmos_concurrency_recovery_finops_certification
    elmos_checkpoint_recovery --> elmos_concurrency_recovery_finops_certification
    elmos_task_io_artifact_archive --> elmos_concurrency_recovery_finops_certification
    elmos_task_financial_analytics --> elmos_concurrency_recovery_finops_certification
```

## Existing Elmos dependencies

The orchestrator also integrates with existing infrastructure Skills including identity/tenant security, Temporal reliability, runner scheduling, caching, observability/FinOps, backup/recovery, scale certification, runtime cost estimation, and commercial packaging.
