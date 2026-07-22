---
name: b37-extension-signing-sbom-provenance
description: "Implement extension signing SBOM license vulnerability provenance transparency and trusted publisher release verification."
---

# Skill 1318: b37-extension-signing-sbom-provenance

## Use this skill when

- Extensions need trustworthy release artifacts.
- Marketplace packages currently lack verifiable origin or component inventory.

## Domain-specific risks and invariants

- A compromised publisher or build system can distribute malicious extensions.
- Unsigned updates and mutable dependencies break reproducibility.

## Workflow

1. Define trusted publisher identity, signing keys, key rotation, artifact digest, SBOM, license report, vulnerability status, build provenance, and transparency records.
2. Implement isolated reproducible builder and signing workflow.
3. Verify dependencies are pinned and allowed.
4. Implement signature and provenance verification at publish and install time.
5. Test key compromise, expired certificates, tampered artifacts, missing SBOM, and revoked releases.

## Required repository outputs

- signed extension bundle
- SBOM license vulnerability and provenance records
- trusted publisher and key lifecycle evidence

## Verification

- Rebuild and compare artifact digests.
- Tamper with artifact and metadata and confirm rejection.
- Verify revoked or expired signing identities cannot publish or install.

## Stop and escalate when

- Publisher identity or source rights cannot be verified.
- Critical vulnerability or prohibited license remains unresolved.

## Definition of done

- Every distributable release is signed and reproducible.
- Installers verify signature, provenance, SBOM, and revocation.
