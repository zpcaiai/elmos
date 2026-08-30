# Supply-chain boundary

`sbom.cdx.json` is a repository-owned source SBOM for the dependency-free local
composite engine and its two untrusted specification inputs: the base 3.0.0
source package and the runtime-assurance 3.1.0 delta. The exact material
identities and claim boundary are also recorded in
`delta-v3.1-integrity.json`. These records are not an image SBOM, legal
approval, signature, provenance attestation, vulnerability report, or release
authorization.

`delta-v3.1-acceptance-bindings.json` is repository-owned static traceability
from the 13 byte-pinned source acceptance documents to 104 exact local test
cases. The qualifier independently revalidates the mapping and requires every
bound selector to pass, but neither the mapping nor a local pass is external or
independent execution evidence.

The supplied base ZIP contains `LICENSE-POLICY.md`, which explicitly calls for an
approved license and legal review before commercial redistribution. It does not
contain an approved license, signature, SBOM, or provenance attestation. The
pinned base ZIP SHA-256 establishes byte identity only. The delta ZIP digest
has the same limited meaning. Neither archive's scripts, SQL, policies,
workflows, prompts, or instructions are executed by the release workflow.

Production release must merge the image and operating-system SBOM, verify all
materials and builders, scan the exact image digest, sign through an external
trusted identity, and satisfy `release-policy.json`. Until then release and
certification remain blocked.
