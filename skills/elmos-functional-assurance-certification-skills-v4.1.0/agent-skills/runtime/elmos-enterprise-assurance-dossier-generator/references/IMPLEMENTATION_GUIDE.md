# Implementation Guide — Enterprise Assurance Dossier Generator

## Purpose

Generate an evidence-backed, redacted and versioned customer procurement dossier covering architecture, security, privacy, AI governance, quality, resilience, supply chain and certification status.

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

1. Generate audience- and tenant-authorized evidence views
2. Answer questionnaires from source evidence with confidence and freshness
3. Include architecture, data flow, subprocessor, incident, DR, accessibility and supply-chain sections
4. Expose certificate scope, waivers, limitations and expiry
5. Route legal, contractual and organizational assertions to authorized humans

## Native acceptance corpus

- `ELMOS_ENTERPRISE_ASSURANCE_DOSSIER_GENERATOR-01` — customer security questionnaire
- `ELMOS_ENTERPRISE_ASSURANCE_DOSSIER_GENERATOR-02` — privacy and subprocessor section
- `ELMOS_ENTERPRISE_ASSURANCE_DOSSIER_GENERATOR-03` — AI governance section
- `ELMOS_ENTERPRISE_ASSURANCE_DOSSIER_GENERATOR-04` — DR and support section
- `ELMOS_ENTERPRISE_ASSURANCE_DOSSIER_GENERATOR-05` — certificate verification
- `ELMOS_ENTERPRISE_ASSURANCE_DOSSIER_GENERATOR-06` — unknown answer escalation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
