# Implementation Guide — Production Deployment Certifier

## Purpose

Certify exact images, manifests, policies, secrets, data migrations, probes, scaling, telemetry and rollback in a production-equivalent or approved production environment.

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

1. Bind to artifact and configuration digests
2. Verify admission, identity, network and secret policies
3. Run startup/readiness/liveness and scaling probes
4. Execute migrations and rollback drill
5. Verify telemetry and operational ownership

## Native acceptance corpus

- `ELMOS_PRODUCTION_DEPLOYMENT_CERTIFIER-01` — signed artifact admission
- `ELMOS_PRODUCTION_DEPLOYMENT_CERTIFIER-02` — database migration
- `ELMOS_PRODUCTION_DEPLOYMENT_CERTIFIER-03` — probe behavior
- `ELMOS_PRODUCTION_DEPLOYMENT_CERTIFIER-04` — autoscaling/backpressure
- `ELMOS_PRODUCTION_DEPLOYMENT_CERTIFIER-05` — network/secret denial
- `ELMOS_PRODUCTION_DEPLOYMENT_CERTIFIER-06` — canary promotion
- `ELMOS_PRODUCTION_DEPLOYMENT_CERTIFIER-07` — rollback drill

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
