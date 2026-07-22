# Batch 18 evidence boundary

Use this boundary for every authoritative Skill 669–745 in the Group Integration Factory.

## Model and final gate

- Model: `GITM`.
- Final gate: `M18-H`.
- Authority text status: `group-integration-completed` only after complete external evidence.
- Repository artifacts, generated plans, schemas, simulations, unit tests, and local database tests never close a field gate by themselves.

## Mandatory operating boundary

1. Bind every decision to tenant/company, legal entity, region, jurisdiction, fiscal or program period, version, owner, authority, confidentiality, and evidence window.
2. Preserve `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, and `BLOCKED` without translating absence into success.
3. Require immutable evidence references, source authority, freshness, approvals, conflicts, costs, risks, stop conditions, and responsible human owners.
4. Keep every gate sequential and non-compensating. Revenue, speed, automation, partner demand, transaction close, or local tests cannot offset a failed safety, legal, financial, privacy, security, human-accountability, or evidence gate.
5. Do not access clean-team data, merge identities or data, switch production systems, exit a TSA, retire assets, or recognize financial synergy.
6. Record `external_operation_executed=false` for control-plane-only work. If a required external authority is unavailable, return `NOT_RUN` or `BLOCKED`.

## Required result

Return a version-bound decision containing the highest satisfied gate, blockers, non-blocking items, negative results, evidence references, approval state, open risks, restrictions, and `external_operation_executed=false`.
