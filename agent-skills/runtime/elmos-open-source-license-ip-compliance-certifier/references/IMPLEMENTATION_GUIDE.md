# Implementation Guide — Open Source, Model, Data and IP Compliance Certifier

## Purpose

Certify software, model, dataset, prompt, generated asset and documentation licensing, attribution, redistribution and policy compatibility.

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

1. Inventory software/model/data/content licenses
2. Evaluate inbound/outbound compatibility
3. Generate notices and source obligations
4. Track generated-code provenance and customer restrictions
5. Block unknown or prohibited licensing

## Native acceptance corpus

- `ELMOS_OPEN_SOURCE_LICENSE_IP_COMPLIANCE_CERTIFIER-01` — permissive dependency
- `ELMOS_OPEN_SOURCE_LICENSE_IP_COMPLIANCE_CERTIFIER-02` — copyleft distribution path
- `ELMOS_OPEN_SOURCE_LICENSE_IP_COMPLIANCE_CERTIFIER-03` — model usage restriction
- `ELMOS_OPEN_SOURCE_LICENSE_IP_COMPLIANCE_CERTIFIER-04` — dataset redistribution restriction
- `ELMOS_OPEN_SOURCE_LICENSE_IP_COMPLIANCE_CERTIFIER-05` — generated asset attribution
- `ELMOS_OPEN_SOURCE_LICENSE_IP_COMPLIANCE_CERTIFIER-06` — unknown license block

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
