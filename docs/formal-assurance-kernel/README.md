# Formal Assurance Kernel integration

The pinned source archive is imported as untrusted declarative material:

- archive SHA-256: `sha256:7d397f9379e15023208d3fb49b3928af07b7b6134e6a91fe70ebaf7048f9e73e`
- exact source Skills: 60
- repository-owned exact local bindings: 60
- external evidence: `NOT_RUN`
- certification: `NOT_CERTIFIED`

`tooling/integrate_formal_assurance_kernel.py` independently verifies archive
byte identity, internal file checksums, path safety, schemas, Skill contracts,
DAGs, workflows and profiles. It never executes package scripts, installers,
reference-kernel code, SQL, workflows or deployment assets. The immutable
source mirror is retained under
`skills/elmos-formal-assurance-kernel-v1.0.0/` for traceability only.

Run `make formal-assurance-kernel` for repository integration checks and local
unit/integration tests. This target is not a production certification gate and
does not authorize provider calls, database writes, deployment, external
verification or customer data access.
