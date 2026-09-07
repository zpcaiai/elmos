# Implementation Guide — Customer VPC Runner Attestation Certifier

## Purpose

Certify customer-hosted runners for identity, isolation, data residency, network, secrets, toolchain, evidence delivery and recovery without requiring source exfiltration.

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

1. Enroll workload identity and trust domain
2. Attest software/configuration and sandbox controls
3. Verify source/data residency and egress policy
4. Stream signed evidence without raw sensitive content
5. Rotate, suspend and revoke runner certificates

## Native acceptance corpus

- `ELMOS_CUSTOMER_VPC_RUNNER_ATTESTATION_CERTIFIER-01` — runner enrollment
- `ELMOS_CUSTOMER_VPC_RUNNER_ATTESTATION_CERTIFIER-02` — network deny
- `ELMOS_CUSTOMER_VPC_RUNNER_ATTESTATION_CERTIFIER-03` — secret broker
- `ELMOS_CUSTOMER_VPC_RUNNER_ATTESTATION_CERTIFIER-04` — source remains in VPC
- `ELMOS_CUSTOMER_VPC_RUNNER_ATTESTATION_CERTIFIER-05` — signed evidence upload
- `ELMOS_CUSTOMER_VPC_RUNNER_ATTESTATION_CERTIFIER-06` — runner drift suspension
- `ELMOS_CUSTOMER_VPC_RUNNER_ATTESTATION_CERTIFIER-07` — disconnected recovery

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
