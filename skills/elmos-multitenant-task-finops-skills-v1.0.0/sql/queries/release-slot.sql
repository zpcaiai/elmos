SELECT elmos.release_account_task_slot(
  :account_id::uuid,
  :slot_no::smallint,
  :task_id::uuid,
  :expected_generation::bigint
) AS released;
