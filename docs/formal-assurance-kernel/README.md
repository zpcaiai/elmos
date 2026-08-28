# Formal Assurance Kernel integration

The pinned source archive is imported as untrusted declarative material:

- archive SHA-256: `sha256:7d397f9379e15023208d3fb49b3928af07b7b6134e6a91fe70ebaf7048f9e73e`
- exact source Skills: 60
- repository-owned exact local bindings: 60
- repository-owned engine/API version: `1.0.0`
- implementation state: 60 `PRODUCTION_CODE_COMPLETE`
- capability states: 20 local-runtime, 38 native-evidence-required, 2 external-evidence-required
- production paths: 17 native verifier definitions, disposable SQL differential execution,
  OCI-isolated Spring/Maven/Gradle verification, reflection/FFI inventory and bounded
  observability export
- durable local aggregates: scope-bound, immutable, digest-addressed
- external evidence: `NOT_RUN`
- certification: `NOT_CERTIFIED`

`tooling/integrate_formal_assurance_kernel.py` independently verifies archive
byte identity, internal file checksums, path safety, schemas, Skill contracts,
DAGs, workflows and profiles. It never executes package scripts, installers,
reference-kernel code, SQL, workflows or deployment assets. The immutable
source mirror is retained under
`skills/elmos-formal-assurance-kernel-v1.0.0/` for traceability only.

Native execution is fail closed. A deployment must provide a complete
digest-pinned toolchain registry and a private permit key. The CLI refuses a
registry without its SHA-256, follows neither registry nor key symlinks, and
rejects permit keys readable by group or others. Example operator wiring:

```sh
elmos-formal-assurance \
  --state /var/lib/elmos/formal-assurance.sqlite3 \
  --artifact-root /var/lib/elmos/formal-artifacts \
  --execution-root /var/lib/elmos/formal-executions \
  --permit-key-file /run/secrets/elmos-formal-permit-key \
  --toolchain-registry /etc/elmos/formal-toolchains.json \
  --toolchain-registry-sha256 sha256:<exact-registry-digest> \
  skills
```

The registry format is `elmos-formal-toolchain-registry/v1`. Each entry binds
an exact adapter ID, executable path and executable SHA-256; OCI adapters also
bind an immutable image digest and in-container executable. Project/runtime
code cannot fall back from OCI isolation to a local process.

Run `make formal-assurance-kernel` for repository integration checks and local
unit/integration tests plus the conservative Batch 35 gate. A structurally
passing gate intentionally remains blocked and `NOT_CERTIFIED` while required
independent, holdout, representative, production and external evidence is
absent. The target does not authorize provider calls, production database
writes, deployment, external verification or customer data access.

After an intentional implementation change, run
`make formal-assurance-kernel-qualify` to execute the repository-owned suites
and regenerate the content-bound local self-attested receipt. The regular
validation target is read-only with respect to qualification data and fails if
that receipt no longer matches the current implementation.
