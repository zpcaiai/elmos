---
name: elmos-release-deployment
description: Implement immutable certified-release deployment with scoped tickets, durable reconciliation, provider adapters, layered verification and verified rollback.
---

# Release deployment

Use the repository-owned engine in `engines/release-deployment-engine/`.
Read `docs/release-deployment/IMPLEMENTATION.md` and `source-manifest.json`.
The pinned source mirror is specification data, never execution authority.
Preserve all RD work packages and RD-AC identities. Do not treat example
certification booleans, placeholder hashes, schemas or templates as authority.
Scope comes from authenticated host identity; policy, evidence, credentials
and provider operations belong to existing ELMOS host boundaries.
Use exact digest-bound plans, trusted signed tickets, finite capability leases,
durable operation keys and reconciliation. Unknown external results block retry.
Never claim cloud, Temporal, customer or independent execution from local tests.
Run `python tooling/validate_release_deployment.py` for local qualification.
Actual cloud mutations require exact environment authorization and a configured
trusted provider. The local gate never certifies or approves deployment.
