# Implementation Guide — Accessibility Conformance Certifier

## Purpose

Generate and independently verify WCAG 2.2 AA-oriented accessibility evidence for web, generated UI, operator consoles and agent-created interactive components.

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

1. Run automated semantic, contrast, focus and name/role/value tests
2. Exercise keyboard, screen reader, zoom, timing and error flows
3. Test dynamic and streamed agent UI updates
4. Require qualified manual review for criteria not automatable
5. Bind exceptions to user impact, remediation and expiry

## Native acceptance corpus

- `ELMOS_ACCESSIBILITY_CONFORMANCE_CERTIFIER-01` — keyboard-only journey
- `ELMOS_ACCESSIBILITY_CONFORMANCE_CERTIFIER-02` — screen reader labels
- `ELMOS_ACCESSIBILITY_CONFORMANCE_CERTIFIER-03` — focus after streaming update
- `ELMOS_ACCESSIBILITY_CONFORMANCE_CERTIFIER-04` — contrast and zoom
- `ELMOS_ACCESSIBILITY_CONFORMANCE_CERTIFIER-05` — timeout and reauthentication
- `ELMOS_ACCESSIBILITY_CONFORMANCE_CERTIFIER-06` — manual review evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
