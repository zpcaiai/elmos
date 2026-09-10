# Skill 03 — Policy, Data Governance & Security

## Goal
Fail closed on security/compliance before cost/quality optimization.

## Data classifications
At minimum:
- PUBLIC
- INTERNAL
- CONFIDENTIAL
- SOURCE_CODE
- SECRET_BEARING
- PII

Classification may be composite.

## Hard filters
Evaluate before ranking:
1. tenant allow/deny
2. model allow/deny
3. provider allow/deny
4. region/residency
5. retention/ZDR requirement
6. training/use-of-data requirement
7. capability requirement
8. context length
9. tool support
10. structured output support
11. secret-bearing restrictions
12. budget hard ceiling
13. provider legal/compliance restrictions
14. capability lease
15. execution authority

## Security context
Integrate with Elmos `VerifiedSecurityContext` and invocation-scoped `CapabilityLease`:
- route request stores references/hashes, not raw privileged material;
- executor re-validates lease before invocation;
- replay may not mint broader authority;
- fallback inherits all constraints.

## Prompt/logging
- raw prompt/response logging OFF by default;
- redact secret/PII fields before optional debug capture;
- debug capture must be tenant-policy gated, encrypted, TTL-bound, auditable;
- traces contain hashes/size/token metadata by default.

## OpenRouter-specific requirement
Treat provider retention/training metadata as policy inputs. Do not assume all OpenRouter providers have identical retention behavior.

## Acceptance
- A denied provider cannot re-enter via fallback.
- Missing classification on protected task causes denial or conservative route.
- Security policy has deterministic unit tests.
- Secrets are absent from structured logs and traces.
