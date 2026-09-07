-- Execute inside the same transaction as task admission.
SELECT *
FROM elmos.claim_account_task_slot(
  :account_id::uuid,
  :tenant_id::uuid,
  :task_id::uuid,
  :lease_seconds::integer
);
