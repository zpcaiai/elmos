# Implementation Guide — Browser and Computer-Use Safety Certifier

## Purpose

Certify perception, action bounding, confirmation, domain allowlists, sensitive-field handling, rollback and visual evidence for browser/computer-use agents.

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

1. classify read, write, destructive and open-world actions
2. bind action coordinates/selectors to fresh observations
3. require confirmation for high-risk effects
4. test prompt injection and UI deception
5. record replayable screenshots/action traces with redaction

## Native acceptance corpus

- `ELMOS_BROWSER_COMPUTER_USE_SAFETY_CERTIFIER-01` — native scenario: classify read, write, destructive and open-world actions
- `ELMOS_BROWSER_COMPUTER_USE_SAFETY_CERTIFIER-02` — native scenario: bind action coordinates/selectors to fresh observations
- `ELMOS_BROWSER_COMPUTER_USE_SAFETY_CERTIFIER-03` — native scenario: require confirmation for high-risk effects
- `ELMOS_BROWSER_COMPUTER_USE_SAFETY_CERTIFIER-04` — native scenario: test prompt injection and UI deception
- `ELMOS_BROWSER_COMPUTER_USE_SAFETY_CERTIFIER-05` — native scenario: record replayable screenshots/action traces with redaction

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
