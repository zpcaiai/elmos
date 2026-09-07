# Production Release and Recertification Runbook

## Release preconditions

- freeze exact RevisionSet and customer acceptance contract;
- resolve all release-time image, compiler, verifier, adapter, model/provider and policy digests;
- execute database migrations and RLS negative tests;
- run native conformance for every selected target/protocol;
- execute security, supply-chain, tenant-isolation, retention/deletion, recovery and rollback campaigns;
- seal Evidence Bundle and request an independent K8 decision.

## Drift and incident triggers

Revoke or suspend affected certificates when an upstream protocol/API/schema changes, a model fingerprint crosses its threshold, a signer or dependency is revoked, a policy/residency requirement changes, tenant isolation fails, a side effect remains unsettled, or a holdout regression exceeds the certified envelope.

## Safe restart

A killed or quarantined capability may restart only after the root cause is fixed, credentials and authority are rotated, affected memory/cache/evidence are quarantined, side effects are reconciled, negative regressions pass, and K8 issues a new decision for the exact post-incident RevisionSet.
