-- Holdout negative workload. A different bound account must return zero rows.
SELECT task_id, task_state, progress_percent
  FROM mtf_task_progress
 WHERE account_id <> current_setting('app.account_id');
