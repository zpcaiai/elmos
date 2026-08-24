# Security, Secrets & Governance

- **Skill ID:** `14-security-governance`
- **Version:** `1.0.0`
- **Category:** core/security
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Preserve principals/roles/privileges and security semantics while enforcing least privilege, secret hygiene, auditability, masking of sensitive fixtures and safe execution boundaries.

## Inputs

- Source grants/roles/users
- Target security capabilities
- Enterprise identity policy
- Secret manager references
- Masking/classification policy

## Required outputs

- Security mapping plan
- Least-privilege migration accounts
- Grant conversion
- Masked fixture set
- Audit trail
- Security gate evidence

## Implementation modules / repository contract

- security/inventory.py
- security/grants.py
- security/secrets.py
- security/masking.py
- security/audit.py
- security/policy.py

## Workflow

1. Inventory users/roles/grants/object privileges and ownership.
2. Map security semantics instead of copying privileged accounts blindly.
3. Create temporary migration identities with minimal rights and expiry.
4. Mask production-derived test data deterministically while preserving relational constraints.
5. Audit tool actions and privileged target changes.
6. Verify TLS/crypto/audit/backup access policy as required by deployment.

## Mandatory tests

- Role inheritance differences
- PUBLIC grants
- Definer/invoker rights
- Synonym/ownership changes
- Masked uniqueness/FK preservation
- Secret leakage scans

## Required evidence

- Security mapping report
- Privilege diff
- Secret scan result
- Masked-data proof
- Audit evidence

## Fail-closed / escalation rules

- Never place live credentials in generated skills, source code, evidence or logs.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
