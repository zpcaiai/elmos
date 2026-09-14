# Human-readable deployment plan

A production preview should show, before approval:

- Release: `rel_...`, commit, certification level
- Exact OCI digest(s)
- Target account/region/instance(s)
- Current stable version -> desired version
- Config diff excluding secret values
- Secret references to be consumed
- Ports/ingress/domain changes
- DB migration risk and estimated lock/backfill concern
- Health and smoke cases
- Rollback candidate and rollback limitations
- Expected machine wall-clock phases (observed/estimated ranges, not human effort)
- Cloud mutations that will occur

The plan is hashed. The approved ticket binds to that plan hash so the executor cannot silently broaden the deployment after approval.
