# Supply-chain boundary

`sbom.cdx.json` is a repository-owned source SBOM for the dependency-free local
engine and its untrusted specification input. It is not an image SBOM, legal
approval, signature, provenance attestation, vulnerability report, or release
authorization.

The supplied ZIP contains `LICENSE-POLICY.md`, which explicitly calls for an
approved license and legal review before commercial redistribution. It does not
contain an approved license, signature, SBOM, or provenance attestation. The
pinned ZIP SHA-256 establishes byte identity only.

Production release must merge the image and operating-system SBOM, verify all
materials and builders, scan the exact image digest, sign through an external
trusted identity, and satisfy `release-policy.json`. Until then release and
certification remain blocked.
