---
name: license-security-and-supply-chain-gate
description: Enforce license, vulnerability, provenance, integrity, registry, maintainer, and transitive supply-chain policy for exact candidates. Use before D-C.
---
# License Security And Supply Chain Gate
Read `../references/dependency-migration-v1.md`. Check exact artifact and transitives for SPDX/license obligations, vulnerabilities with timestamped databases, hashes/signatures/provenance, approved registry, namespace risks, maintainer/support state, install scripts, binaries and typosquatting. Emit `PASSED`, `BLOCKED`, or `INCONCLUSIVE` with evidence and exceptions requiring named approval. Unknown is never pass; a compatibility score cannot override policy. Never download, execute install scripts, suppress transitives or fabricate SBOM/attestation evidence.
