# Implementation Guide — GitOps Argo CD and Flux Release Controller

## Purpose

Generate signed declarative release, environment promotion, health, rollback and drift reconciliation workflows.

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

1. publish signed immutable manifests
2. enforce promotion by evidence gate
3. configure health and sync waves
4. detect and classify drift
5. rollback Git, image, schema and model coherently

## Native acceptance corpus

- `ELMOS_GITOPS_ARGOCD_FLUX_RELEASE_CONTROLLER-01` — native scenario: publish signed immutable manifests
- `ELMOS_GITOPS_ARGOCD_FLUX_RELEASE_CONTROLLER-02` — native scenario: enforce promotion by evidence gate
- `ELMOS_GITOPS_ARGOCD_FLUX_RELEASE_CONTROLLER-03` — native scenario: configure health and sync waves
- `ELMOS_GITOPS_ARGOCD_FLUX_RELEASE_CONTROLLER-04` — native scenario: detect and classify drift
- `ELMOS_GITOPS_ARGOCD_FLUX_RELEASE_CONTROLLER-05` — native scenario: rollback Git, image, schema and model coherently

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
