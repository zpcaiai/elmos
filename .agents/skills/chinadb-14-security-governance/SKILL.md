---
name: chinadb-14-security-governance
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Security, Secrets & Governance. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "14-security-governance"
  source_path: "skills/14-security-governance/SKILL.md"
  source_sha256: "sha256:73d738d6f680c909ba12ea2ffc8b9a0cdc686a8bda04d89ec4e7547f269b9dc4"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
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

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `14-security-governance`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
