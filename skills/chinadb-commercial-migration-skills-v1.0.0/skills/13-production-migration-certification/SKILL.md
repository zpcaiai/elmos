# E1-E5 Production Migration Certification

- **Skill ID:** `13-production-migration-certification`
- **Version:** `1.0.0`
- **Category:** core/certification
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Issue a reproducible, evidence-backed migration decision across static conversion, data integrity, behavior, performance and operational readiness. Certification is release-candidate and route-fingerprint specific.

## Inputs

- All evidence index
- Default/route-specific gate policy
- Waivers and approvals
- Release candidate hash
- Route fingerprint

## Required outputs

- Certification JSON
- Human-readable certificate
- Blocking findings
- Expiry/recertification triggers

## Implementation modules / repository contract

- certify/gates.py
- certify/policy.py
- certify/waivers.py
- certify/report.py
- certify/fingerprint.py

## Interfaces and contracts

- Gate defaults in config/default-gates.yaml
- Any route-affecting change invalidates affected gates

## Workflow

1. Verify evidence authenticity/fingerprints and freshness.
2. Evaluate E1 static/compile conversion.
3. Evaluate E2 data integrity and CDC reconciliation.
4. Evaluate E3 behavior and transaction equivalence.
5. Evaluate E4 performance/SLO equivalence.
6. Evaluate E5 security/operations/rehearsal/rollback readiness.
7. Apply only explicit non-expired waivers with owner and compensating controls.
8. Issue certified/rejected/conditional decision tied to exact RC.

## Mandatory tests

- Missing evidence
- Stale benchmark after schema change
- Waiver expiry
- Changed target version/config
- Changed app build after E3
- Tampered evidence hash

## Required evidence

- `schemas/certification.schema.json` instance
- Certificate markdown
- Gate calculation trace
- Waiver ledger

## Fail-closed / escalation rules

- No certification based on vendor migration-tool success alone.
- P0/P1 behavior mismatch cannot be waived by an automated agent.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
