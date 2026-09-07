# Implementation Guide — Environment Parity and Configuration Drift Certifier

## Purpose

Compare development, test, certification and production environments across images, flags, policies, dependencies, data features and managed-service parameters.

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

1. Collect immutable environment snapshots
2. Classify material and non-material differences
3. Verify feature flag and secret references
4. Compare managed service parameters and extensions
5. Invalidate certification for material drift

## Native acceptance corpus

- `ELMOS_ENVIRONMENT_PARITY_CONFIG_DRIFT_CERTIFIER-01` — test/prod image parity
- `ELMOS_ENVIRONMENT_PARITY_CONFIG_DRIFT_CERTIFIER-02` — database parameter parity
- `ELMOS_ENVIRONMENT_PARITY_CONFIG_DRIFT_CERTIFIER-03` — feature flag parity
- `ELMOS_ENVIRONMENT_PARITY_CONFIG_DRIFT_CERTIFIER-04` — network policy parity
- `ELMOS_ENVIRONMENT_PARITY_CONFIG_DRIFT_CERTIFIER-05` — approved exception
- `ELMOS_ENVIRONMENT_PARITY_CONFIG_DRIFT_CERTIFIER-06` — material drift blocks promotion

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
