---
name: supply-chain-artifact-security
description: Safely ingest untrusted repositories and dependencies, verify lockfiles, SBOMs, build provenance, signatures and artifact quarantine before ETGB execution or release.
---

# Supply-Chain and Artifact Security

## Threat model

Public or customer repositories may contain malicious build scripts, dependency confusion, typosquats, binary payloads, credential harvesters, unsafe symlinks, submodule escapes, archive bombs or Prompt injections. Generated targets may introduce vulnerable or unpinned dependencies.

## Intake

1. Scan archive structure, paths, sizes, symlinks, submodules, Git LFS and binaries before extraction/build.
2. Detect secrets/PII and quarantine as policy requires.
3. Identify package managers, scripts and network behavior.
4. Pin source commit, dependency locks, registries and image digests.
5. Build with no secrets in an isolated low-privilege sandbox and deny network by default.
6. Record all fetched artifacts by digest.

## Target validation

Generate SBOM, dependency graph and build provenance. Verify the final artifact corresponds to the expected source/candidate/toolchain, contains no undeclared binary or package, and runs non-root where applicable. Compare dependency substitutions against source contracts.

## Policy

- no mutable image/package tags in release profiles;
- no unsigned binary unless explicitly approved and isolated;
- no dynamic install script with unrestricted network/secrets;
- no dependency lock deletion to make build pass;
- vulnerabilities are evaluated by severity, reachability and compensating control;
- license review remains independent of vulnerability review.

## Evidence

Retain scanner versions, policy, findings, SBOM digest, provenance, signature/attestation and quarantine decision. Do not expose customer source in external scanning services without authorization.

## Hard gates

Malicious execution, provenance mismatch, dependency confusion, unsigned prohibited artifact, secret exfiltration or critical reachable vulnerability blocks release.
