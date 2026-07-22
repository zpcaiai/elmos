---
name: workload-identity-and-service-authentication
description: Govern short-lived workload identity, mTLS or JWT service authentication, audience, rotation, federation, and revocation. Use for Control Plane, Runner, Artifact, model, signing, or offline node trust.
---

# Workload Identity and Service Authentication

Read `../references/batch-12-enterprise-platform.md`. Bind identity to trust domain, tenant, Runner pool/job and allowed service audiences; automate rotation and stop new work safely on expiry. Keep development identities out of production.

Shared long-term API keys, copyable Runner identity or implicit trust-domain federation blocks T-C.
