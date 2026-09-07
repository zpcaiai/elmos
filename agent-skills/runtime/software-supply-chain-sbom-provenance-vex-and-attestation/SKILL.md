---
name: software-supply-chain-sbom-provenance-vex-and-attestation
description: Govern source, dependency, builder, artifact, registry, SBOM, provenance, signature, VEX, and release evidence. Use for SPDX or CycloneDX inventories and SLSA-aligned supply-chain assurance.
---

# Software Supply Chain Evidence

1. Inventory source, commit, build definition, builder identity, dependencies, build secrets, artifact digest, registry, deployment, and signatures.
2. Generate and distinguish source, build, artifact, and deployed SBOMs; mark completeness as explicit and never infer it from tool success.
3. Bind provenance and attestations to subject digest, builder, invocation, source, inputs, environment, time, and parameters.
4. Treat SLSA as an evidence-backed source/build target, not a claim implied by a provenance file.
5. Require VEX product, component, vulnerability, analysis, justification, evidence, author, expiry, and reassessment trigger; unsupported `NOT_AFFECTED` becomes `UNDER_INVESTIGATION`.
6. Verify digest, signature, provenance, builder, source, SBOM, vulnerability, VEX, policy, and target environment before release.

## Acceptance

Fail closed for incomplete SBOMs, missing provenance, untrusted builders, digest mismatch, unsigned artifacts, or insufficient VEX evidence.
