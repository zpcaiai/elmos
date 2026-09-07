# Batch 16 evidence boundary

Use this boundary for every authoritative Skill 526–592 in the AI-native company and Agent Workforce.

## Model and final gate

- Model: `AI-native operating system`.
- Final gate: `AI16-G`.
- Authority text status: `bounded-autonomous-company-ready` only after complete external evidence.
- Repository artifacts, generated plans, schemas, simulations, unit tests, and local database tests never close a field gate by themselves.

## Mandatory operating boundary

1. Bind every decision to tenant/company, legal entity, region, jurisdiction, fiscal or program period, version, owner, authority, confidentiality, and evidence window.
2. Preserve `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, and `BLOCKED` without translating absence into success.
3. Require immutable evidence references, source authority, freshness, approvals, conflicts, costs, risks, stop conditions, and responsible human owners.
4. Keep every gate sequential and non-compensating. Revenue, speed, automation, partner demand, transaction close, or local tests cannot offset a failed safety, legal, financial, privacy, security, human-accountability, or evidence gate.
5. Do not invoke live tools, provision credentials, modify Agent authority, promote autonomy, make high-impact human decisions, or claim unbounded autonomy.
6. Record `external_operation_executed=false` for control-plane-only work. If a required external authority is unavailable, return `NOT_RUN` or `BLOCKED`.

## Required result

Return a version-bound decision containing the highest satisfied gate, blockers, non-blocking items, negative results, evidence references, approval state, open risks, restrictions, and `external_operation_executed=false`.
