-- Development-only read workload. Requires transaction-local authenticated context.
SELECT organization_id, account_id, root_task_limit, active_root_tasks,
       waiting_root_tasks, available_root_slots, reconciliation_status
  FROM mtf_account_concurrency_status;
