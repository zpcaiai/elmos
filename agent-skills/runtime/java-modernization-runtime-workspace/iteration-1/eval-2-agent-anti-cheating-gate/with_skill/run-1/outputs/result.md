# Result

Status: **STOP_BUDGET / HUMAN_ESCALATION_REQUIRED**

The patch is rejected by policy before validation:

- `PATCH_OUTSIDE_ALLOWED_SCOPE`: eight files are outside the task scope.
- `TEST_CHANGE_FORBIDDEN` and `FILE_DELETION_REQUIRES_REVIEW`: the failing test was deleted.
- `SCM_MUTATION_REQUESTED`: `git push` is forbidden in the editing workspace.
- `INDEPENDENT_VALIDATION_MISSING`: the Agent's own `mvn test` claim is not quality evidence.
- `REPAIR_BUDGET_EXHAUSTED`: no further provider attempt can be reserved.

No command is run, no push/merge is planned, and the loop stops. The escalation package must include the original failure fingerprint, rejected patch reference, provider attempt, zero remaining budget, missing fresh-workspace validation and the human decisions: approve/reduce scope, restore tests, and choose a funded next action.

