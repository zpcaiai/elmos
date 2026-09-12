# Skill 05 — LiteLLM Gateway Integration

## Goal
Use LiteLLM as a replaceable infrastructure gateway, not as the source of Elmos semantic routing truth.

## Deployment
Run LiteLLM Proxy independently from the Elmos API process.

Recommended production topology:
- >=2 proxy replicas
- health/readiness probes
- PodDisruptionBudget
- resource limits
- TLS/mTLS or trusted service mesh
- secrets through secret manager
- persistent backing DB only for features that require it
- no master key embedded in application source

## Elmos responsibilities
Elmos sends a fully resolved deployment/model alias and request policy.

## LiteLLM responsibilities
Allowed:
- protocol normalization,
- auth proxying,
- provider-compatible retries where explicitly allowed,
- provider deployment load balancing inside an Elmos-approved deployment group,
- rate limiting as defense-in-depth,
- usage/cost telemetry,
- observability hooks.

Not allowed:
- selecting a different semantic model class without Elmos permission;
- weakening retention/security policy;
- replacing Elmos budget ledger;
- changing tool permissions.

## Failover ownership
Prefer:
- Elmos owns cross-model fallback.
- LiteLLM may own same-model/same-policy deployment failover.
This avoids hidden semantic changes.

## Configuration
Use stable Elmos model aliases and explicit deployment groups.

## Acceptance
- Gateway can be bypassed by native lane for a selected deployment.
- LiteLLM outage does not take down native-direct routes.
- Elmos can reconstruct exact physical deployment used.
