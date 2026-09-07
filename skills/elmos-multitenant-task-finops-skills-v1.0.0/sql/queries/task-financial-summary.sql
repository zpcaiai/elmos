SELECT *
FROM elmos.task_profitability_v
WHERE tenant_id = :tenant_id::uuid
  AND (:task_id::uuid IS NULL OR task_id = :task_id::uuid)
ORDER BY as_of DESC NULLS LAST;
