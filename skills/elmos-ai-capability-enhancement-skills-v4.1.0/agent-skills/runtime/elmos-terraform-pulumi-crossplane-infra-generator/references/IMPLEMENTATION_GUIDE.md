# Implementation Guide — Terraform, Pulumi and Crossplane Infrastructure Generator

## Purpose

Generate portable infrastructure definitions from Deployment IR with state, policy, drift, secret and rollback controls.

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

1. lower Deployment IR to selected IaC target
2. separate state and tenant boundaries
3. generate policy and cost checks
4. plan/import existing resources safely
5. test drift, destroy and rollback behavior

## Native acceptance corpus

- `ELMOS_TERRAFORM_PULUMI_CROSSPLANE_INFRA_GENERATOR-01` — native scenario: lower Deployment IR to selected IaC target
- `ELMOS_TERRAFORM_PULUMI_CROSSPLANE_INFRA_GENERATOR-02` — native scenario: separate state and tenant boundaries
- `ELMOS_TERRAFORM_PULUMI_CROSSPLANE_INFRA_GENERATOR-03` — native scenario: generate policy and cost checks
- `ELMOS_TERRAFORM_PULUMI_CROSSPLANE_INFRA_GENERATOR-04` — native scenario: plan/import existing resources safely
- `ELMOS_TERRAFORM_PULUMI_CROSSPLANE_INFRA_GENERATOR-05` — native scenario: test drift, destroy and rollback behavior

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
