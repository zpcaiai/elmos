# Result

Status: **BLOCKED / STALE / NOT_RUN**

The Delivery Snapshot is incomplete because `VALIDATION_DECISION_MISSING` and `EVIDENCE_PACK_MISSING_OR_UNSIGNED` are blocking. The report remains a projection of those facts and cannot turn them green.

The report and any check were bound to the pre-squash HEAD. After the squash, both become `STALE`; a new Batch 7 decision, Delivery Snapshot, report and check are required for the new SHA.

GitHub publication is `NOT_RUN` because no authorized GitHub App installation exists. ELMOS may produce an offline plan with `draft=true`, `forcePush=false` and `autoMerge=false`, but it must not claim a PR URL or Check Run. The lifecycle remains separate: no evidence supports Accepted, Merged, Released or Closed.

