# Result Intercept / Fence / Reconcile Protocol

`RAW_RESULT -> RESULT_INTERCEPT -> CANDIDATE_CHECKPOINT -> RESULT_FENCE -> TRUTH_VERIFY -> CERTIFY -> RECONCILE_TRANSACTION -> PUBLISH`

Builder runtimes never own publication authority. Exactly-once result commit is keyed by `(execution_id, result_generation, candidate_checkpoint_digest)`.
