---
name: b37-marketplace-certification-gate
description: Run the conservative Batch 37 core marketplace certification gate before the mandatory closure gate and emit certified limited experimental or blocked status from exact ABI SDK sandbox publisher signing release lifecycle commercial holdout and evidence facts.
---

# Skill 1324: b37-marketplace-certification-gate

## Use this skill when

- A Marketplace Pack or release is requesting certification.
- A release, SDK, publisher, or lifecycle change could invalidate prior certification.

## Domain-specific risks and invariants

- Self-declared certified status is not evidence.
- A single missing revocation, sandbox, signature, or tenant-isolation fact can invalidate the whole marketplace path.

## Workflow

1. Validate pack, manifest, sandbox, publisher, compatibility, release, commercial, and certification records.
2. Resolve every evidence reference and verify immutable digests.
3. Evaluate quantitative thresholds and zero-tolerance findings.
4. Run negative, holdout, representative extension, install, upgrade, rollback, and revoke workflows.
5. Emit gate result and report without upgrading status beyond actual evidence.

## Required repository outputs

- `certification/gate-result.json`
- `certification/gate-report.md`
- evidence-supported marketplace status

## Verification

- Run all Batch 37 validators and test suites.
- Verify signatures, SBOM, provenance, publisher identity, sandbox, permissions, installation, rollback, revocation, and entitlement evidence.
- Reject fake certification, stale evidence, mutable release, or unresolved P0 unknown.

## Stop and escalate when

- Any exact artifact, product version, publisher, permission, policy, or evidence reference is missing.
- A critical security, privacy, tenant, supply-chain, financial, or revocation finding remains.

## Definition of done

- Gate status is reproducible from immutable evidence.
- Certified packs meet all thresholds and zero-tolerance conditions.
- Limited, experimental, or blocked status accurately describes residual capability.

## Closure requirement

- After this core gate passes, invoke `$b37-marketplace-closure-certification-gate`; a core-certified pack is not ecosystem-closure-certified until that gate also passes.
