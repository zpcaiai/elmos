---
name: elmos-security-auth-gate
version: 1.0.0
description: Add threat-focused negative validation for security/auth/privacy-sensitive tasks.
---

# Security & Authorization Gate

Add threat-focused negative validation for security/auth/privacy-sensitive tasks.

## Trigger conditions
- risk.security high or auth touched

## Inputs
- `diff`
- `threat surface`
- `tests`

## Outputs
- `security evidence`
- `block/approve`

## Procedure
1. Check authn/authz boundaries.
2. Check input validation and injection surfaces.
3. Check secret exposure.
4. Add negative-path tests.
5. Require high-tier review for material changes.

## Guardrails
- Fail closed on missing critical evidence.

## Acceptance criteria
- security-required tests pass and reviewer signs off

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
