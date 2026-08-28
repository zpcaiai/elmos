# Implementation Guide — Agent Human UX Safety Verifier

## Purpose

Verify that agent interfaces communicate uncertainty, intent, side effects, approvals, reversibility and recovery without dark patterns or misleading automation.

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

1. Action preview and consequence clarity
2. Uncertainty and evidence display
3. Consent/approval usability
4. Cancellation/recovery feedback
5. Accessibility and dark-pattern checks

## Native acceptance corpus

- `ELMOS_AGENT_HUMAN_UX_SAFETY_VERIFIER-01` — high-risk action preview
- `ELMOS_AGENT_HUMAN_UX_SAFETY_VERIFIER-02` — uncertainty display
- `ELMOS_AGENT_HUMAN_UX_SAFETY_VERIFIER-03` — approval comprehension
- `ELMOS_AGENT_HUMAN_UX_SAFETY_VERIFIER-04` — cancel/recover
- `ELMOS_AGENT_HUMAN_UX_SAFETY_VERIFIER-05` — accessibility
- `ELMOS_AGENT_HUMAN_UX_SAFETY_VERIFIER-06` — dark-pattern review

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
