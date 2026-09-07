# Formal Assurance Kernel integration

The pinned source archive is imported as untrusted declarative material:

- archive SHA-256: `sha256:7d397f9379e15023208d3fb49b3928af07b7b6134e6a91fe70ebaf7048f9e73e`
- exact source Skills: 60
- exact source acceptance criteria: 481
- repository-owned exact local bindings: 60
- installed Skill interfaces: 60 exact names under both `.agents/skills/` and
  `agent-skills/runtime/` (120 digest-identical wrappers)
- repository-owned executable acceptance controls: 481
- repository-owned engine/API version: `1.0.0`
- implementation state: 60 `PRODUCTION_CODE_COMPLETE`
- capability states: 20 local-runtime, 38 native-evidence-required, 2 external-evidence-required
- production paths: 17 native verifier definitions, disposable SQL differential execution,
  OCI-isolated Spring/Maven/Gradle verification, reflection/FFI inventory and bounded
  observability export
- durable local aggregates: scope-bound, immutable, digest-addressed
- governed lifecycle aggregates: assumptions, trusted components, waivers,
  dependency drift, revalidation queues and append-only security audit
- delivery boundaries: transactional outbox plus injected idempotent event publisher,
  injected tenant-scoped object-store adapter and authorized PostgreSQL 17 migration
- evidence bundles: content-addressed files, deterministic manifests, strict redaction,
  offline integrity replay and optional local self-attested HMAC signing
- external evidence: `NOT_RUN`
- certification: `NOT_CERTIFIED`

`tooling/integrate_formal_assurance_kernel.py` independently verifies archive
byte identity, internal file checksums, path safety, schemas, Skill contracts,
DAGs, workflows and profiles. It never executes package scripts, installers,
reference-kernel code, SQL, workflows or deployment assets. The immutable
source mirror is retained under
`skills/elmos-formal-assurance-kernel-v1.0.0/` for traceability only.

`acceptance-traceability.json` maps every one of the 481 source acceptance IDs
to an exact repository handler and an executable positive, bounded-honesty,
counterexample, dependency-drift or tenant-fencing control. Those controls are
local self-attested engineering checks. The source package's external and
independent acceptance evidence remains `NOT_RUN`.

The installed Skill wrappers are repository-owned authority boundaries. They
retain each exact source identity, source digest, runtime handler, dependency
list and evidence state, while treating the source package's imperative prose
as inert declarative requirements. Broad work starts with
`$elmos-formal-assurance-orchestrator`; focused work uses the narrowest exact
installed Skill. The importer rejects collisions, symlinks and dual-root drift.

Native execution is fail closed. A deployment must provide a complete
digest-pinned toolchain registry, a private permit key and a separate private
artifact-encryption key whenever durable artifact storage is enabled. The CLI
refuses a registry without its SHA-256, follows neither registry nor key
symlinks, and rejects secret keys readable by group or others. Example operator
wiring:

```sh
elmos-formal-assurance \
  --state /var/lib/elmos/formal-assurance.sqlite3 \
  --artifact-root /var/lib/elmos/formal-artifacts \
  --artifact-encryption-key-file /run/secrets/elmos-formal-artifact-encryption-key \
  --artifact-encryption-key-id local-artifact-kek-v1 \
  --execution-root /var/lib/elmos/formal-executions \
  --permit-key-file /run/secrets/elmos-formal-permit-key \
  --bundle-signing-key-file /run/secrets/elmos-formal-bundle-key \
  --bundle-signing-key-id local-qualification \
  --toolchain-registry /etc/elmos/formal-toolchains.json \
  --toolchain-registry-sha256 sha256:<exact-registry-digest> \
  skills
```

The registry format is `elmos-formal-toolchain-registry/v1`. Each entry binds
an exact adapter ID, executable path and executable SHA-256; OCI adapters also
bind an immutable image digest and in-container executable. Project/runtime
code cannot fall back from OCI isolation to a local process.

The optional native HMAC/Merkle bridge is a separate local acceleration path.
It has no directory scan or implicit fallback: the host must supply one
absolute library path and its exact SHA-256 together. Returned payload digests,
HMAC values and Merkle roots are recomputed independently before acceptance.
Missing configuration stays `NOT_RUN`; even a successful call remains local
self-attested engineering evidence and is not an external signature.

The WSGI API exposes scope-bound assumption and trusted-component registration,
four-eyes waiver proposal/approval/revocation, explicit dependency-drift
invalidation, evidence-bundle build/verification and latest-gate retrieval.
Request bodies cannot override trusted tenant/project/account scope. Denials are
recorded in the tenant-local append-only audit stream when a trusted identity is
available.

`Postgres17MigrationManager` plans and applies the repository-owned V005 SQL
extension only with a trusted schema-admin identity and authorization reference,
inside one transaction, against an exact PostgreSQL 17 server. The local fake
DB-API tests prove adapter behavior only; no PostgreSQL cluster was contacted.
`ArtifactStore` and `EventPublisher` are least-privileged provider contracts:
an operator must inject real S3/GCS/MinIO and Kafka/NATS/Redpanda adapters and
retain their independent receipts before claiming those integrations ran.

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
