# Implementation Guide — Risk Acceptance and Residual-Risk Governor

## Purpose

Govern explicit risk ownership, rationale, compensating controls, customer disclosure, expiry and certificate impact without converting acceptance into proof.

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

1. record risk claim, likelihood, impact and evidence
2. require authorized owner and independent review
3. bind compensating controls and monitoring
4. set expiry and renewal criteria
5. display residual risk in certificate and customer dossier

## Native acceptance corpus

- `ELMOS_RISK_ACCEPTANCE_RESIDUAL_RISK_GOVERNOR-01` — native scenario: record risk claim, likelihood, impact and evidence
- `ELMOS_RISK_ACCEPTANCE_RESIDUAL_RISK_GOVERNOR-02` — native scenario: require authorized owner and independent review
- `ELMOS_RISK_ACCEPTANCE_RESIDUAL_RISK_GOVERNOR-03` — native scenario: bind compensating controls and monitoring
- `ELMOS_RISK_ACCEPTANCE_RESIDUAL_RISK_GOVERNOR-04` — native scenario: set expiry and renewal criteria
- `ELMOS_RISK_ACCEPTANCE_RESIDUAL_RISK_GOVERNOR-05` — native scenario: display residual risk in certificate and customer dossier

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
