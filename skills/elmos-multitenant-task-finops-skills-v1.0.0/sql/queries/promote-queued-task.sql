-- Candidate selection only; caller must still atomically claim an account slot
-- and reserve tenant/resource capacity before changing state to ADMITTED.
SELECT t.id, t.tenant_id, t.account_id, t.priority, t.queue_entered_at,
       t.estimated_concurrency_units
FROM elmos.task t
WHERE t.state = 'WAITING_FOR_SLOT'
ORDER BY t.priority DESC,
         t.queue_entered_at ASC NULLS LAST,
         t.created_at ASC
FOR UPDATE SKIP LOCKED
LIMIT :batch_size;
