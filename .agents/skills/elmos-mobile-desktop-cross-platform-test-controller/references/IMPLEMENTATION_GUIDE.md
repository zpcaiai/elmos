# Implementation Guide — Mobile and Desktop Cross-Platform Test Controller

## Purpose

Test generated iOS, Android, Flutter, macOS, Windows and web clients across device, OS, network, permission and lifecycle matrices.

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

1. select representative device/OS matrix
2. exercise install, upgrade and deep links
3. test permissions, backgrounding and offline mode
4. verify accessibility and localization
5. capture crash, performance and battery evidence

## Native acceptance corpus

- `ELMOS_MOBILE_DESKTOP_CROSS_PLATFORM_TEST_CONTROLLER-01` — native scenario: select representative device/OS matrix
- `ELMOS_MOBILE_DESKTOP_CROSS_PLATFORM_TEST_CONTROLLER-02` — native scenario: exercise install, upgrade and deep links
- `ELMOS_MOBILE_DESKTOP_CROSS_PLATFORM_TEST_CONTROLLER-03` — native scenario: test permissions, backgrounding and offline mode
- `ELMOS_MOBILE_DESKTOP_CROSS_PLATFORM_TEST_CONTROLLER-04` — native scenario: verify accessibility and localization
- `ELMOS_MOBILE_DESKTOP_CROSS_PLATFORM_TEST_CONTROLLER-05` — native scenario: capture crash, performance and battery evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
