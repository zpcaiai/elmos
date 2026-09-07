# Implementation Guide — Audit Duration, Sampling and Risk Planner

## Purpose

Implement and independently certify audit duration, sampling and risk planner, including estimate effort from scope, complexity, sites, shifts, providers, change rate and risk, design representative sample of repositories, deployments, evidence and personnel and document reductions, additions and residual sampling risk.

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

1. estimate effort from scope, complexity, sites, shifts, providers, change rate and risk
2. design representative sample of repositories, deployments, evidence and personnel
3. document reductions, additions and residual sampling risk
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AUDIT_DURATION_SAMPLING_RISK_PLANNER-01` — native scenario: estimate effort from scope, complexity, sites, shifts, providers, change rate and risk
- `ELMOS_AUDIT_DURATION_SAMPLING_RISK_PLANNER-02` — native scenario: design representative sample of repositories, deployments, evidence and personnel
- `ELMOS_AUDIT_DURATION_SAMPLING_RISK_PLANNER-03` — native scenario: document reductions, additions and residual sampling risk
- `ELMOS_AUDIT_DURATION_SAMPLING_RISK_PLANNER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AUDIT_DURATION_SAMPLING_RISK_PLANNER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
