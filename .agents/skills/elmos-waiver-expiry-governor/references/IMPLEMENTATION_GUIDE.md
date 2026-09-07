# Implementation Guide — Waiver and Expiry Governor

## Purpose

Control exceptional waivers with explicit claim scope, rationale, compensating controls, owner, approvals, expiry and automatic certificate impact.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. Require bounded claim and evidence-backed rationale
2. Enforce role/dual approval by risk
3. Bind compensating monitoring and remediation
4. Set non-optional expiry and owner
5. Revoke or narrow certificate on expiry

## Native acceptance corpus

- `ELMOS_WAIVER_EXPIRY_GOVERNOR-01` — low-risk waiver
- `ELMOS_WAIVER_EXPIRY_GOVERNOR-02` — critical waiver dual approval
- `ELMOS_WAIVER_EXPIRY_GOVERNOR-03` — missing expiry rejected
- `ELMOS_WAIVER_EXPIRY_GOVERNOR-04` — compensating control failure
- `ELMOS_WAIVER_EXPIRY_GOVERNOR-05` — expiry revokes claim
- `ELMOS_WAIVER_EXPIRY_GOVERNOR-06` — waiver transfer denied

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
