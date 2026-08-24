# `elmos-cas` — Content-Addressed Storage and Action Cache

Implements the code-level part of the `elmos-content-addressed-cache` skill
(`ELMOS-CAS-001` … `ELMOS-CAS-042`).

Java 21, no Spring, and no third-party dependencies: the one Maven dependency is
`elmos-object-storage`, which is itself JDK-only and holds the repository's single SigV4
implementation. Content identities and canonical encodings are deterministic and unit-testable;
encrypted envelopes deliberately use fresh random nonces.

## What this replaces

`modules/portfolio-scale/…/TenantContentAddressedCache.java` was an in-heap `HashMap` with a
separator-joined cache key. It now delegates immutable bytes to this module without changing its
public caller shape. Its key-to-digest index remains process-local and is therefore not evidence
of cross-instance portfolio-cache hits.

## Layout

| Type | Responsibility |
|---|---|
| `CasDigest`, `CasHasher` | sha256 / lowercase hex / size identity; incremental hashing for chunked transfer |
| `MerkleTree` | canonical directory serialisation: byte-ordered names, mode bits, symlink targets, no content rewriting |
| `CasManifest` | immutable, addressable manifests; length-prefixed canonical encoding shared with the action key |
| `CasObjectModel` | sensitivity, retention class, residency, provenance — metadata kept *outside* the content |
| `CasStore` | storage port |
| `LocalDiskCasStore` | L1 on real files: atomic writes, verify-on-read, quarantine on poisoning |
| `InMemoryCasStore` | heap tier / test double, with fault injection |
| `TieredCasStore` | read-through, best-effort vs durable writes, LRU eviction that never drops a not-yet-durable object |
| `ResumableUploadService` | direct + multipart upload, per-chunk digests, resume offset, conflict detection, quarantine |
| `TransferPolicy` | compression decision, deflate codec, token-bucket bandwidth limiter |
| `TenantEncryption`, `DirectoryTenantEncryption`, `TenantEncryptedLocalCasStore` | versioned per-tenant AES-GCM envelopes, operator-mounted keyring rotation and tenant-namespaced ciphertext on local disk |
| `ActionKeyBuilder`, `ActionKey` | exact action key + component diffing for miss explanation |
| `ActionResultRecord` | `action-result.schema.json` shape, with the failure taxonomy |
| `LogRedaction` | secret removal before a log is cached and replayed |
| `CasAccessPolicy` | tenant / residency / clearance / permission-scope decision on every read |
| `ActionCache`, `ActionCacheIndex`, `JdbcActionCacheIndex` | outcomes, failure-cache policy, sampled recompute, tenant-scoped quarantine and a durable reconstructable PostgreSQL index |
| `CasGarbageCollector` | reachability marking, generation-safe roots, retention/legal hold and a reason-bound deletion manifest; any unresolved graph blocks the whole sweep |
| `CasReconciler` | missing blobs, orphans, dangling manifests, incomplete uploads |
| `CasMetrics` | per-layer outcome counters, savings, miss explanation |
| `CasBatch`, `CasStore.putAll/getAll` | batch transfer with one existence probe and per-item failure isolation |
| `RegionalPlacement` | residency to region mapping, placement admission, replication backlog |
| `WorkloadIdentity` | PKIX chain validation, SPIFFE URI SAN, trust domain, clientAuth EKU, serial denylist |
| `ResultSignature` | Ed25519 detached signatures over a versioned complete result/authorization/risk/writer subject; receipts bind the exact envelope digest |
| `S3CasStore` | S3/MinIO shared tier over the REST API, signed by `modules/object-storage`'s `SigV4Presigner` |
| `CasTelemetry`, `OtlpExporter` | OTel-shaped spans and instruments, OTLP/HTTP JSON export |
| `CasAlerting` | six rules, per-rule-and-key throttling, webhook delivery |
| `CasCatalog`, `InMemoryCasCatalog`, `JdbcCasCatalog` | the transactional record behind the V65 schema |
| `ActionCacheBenchmark` | the ELMOS-CAS-041 harness, runnable as a `main` |

## Design decisions worth knowing before changing this code

1. **Length-prefixed canonical encoding.** Every canonical form writes `<byteLength>:<value>\n`.
   Joining fields with a separator lets an attacker-controlled field spell that separator and
   collapse two different actions onto one key. `ActionKeyTest.separatorInjectionCannot…` locks
   this.
2. **Undeclared environment variables are a build error.** An environment variable that can
   change the output but is absent from the key makes the cache serve a wrong result forever.
   `ActionKeyBuilder` refuses rather than silently narrowing.
3. **The GC never deletes on uncertainty.** A missing/unreadable root, unknown manifest decode,
   resolver substitution or malformed tree blocks the entire sweep. Uncatalogued, young and
   legally held objects are also retained. The addressable deletion record binds collected and
   retained reasons plus every unresolved reference, rather than only the object digests.
4. **Eviction never removes a not-yet-durable object.** `TieredCasStore.put` registers the
   durability debt *before* admitting the object locally; doing it afterwards opened a window
   where reclamation discarded the only copy (caught by test, fixed).
5. **SigV4 is not implemented here.** An earlier revision of this module shipped its own
   `AwsV4Signer`; it was deleted in favour of `io.elmos.storage.SigV4Presigner`, which was already
   pinned to the published AWS test vector. Two RFC 3986 encoders in one repository drift, and the
   failure mode is a signature that verifies locally and 403s in production.
6. **AES-GCM nonces are random, while deduplication stays content-addressed.** A fresh nonce is
   stored with each encrypted envelope. The tenant store publishes only one immutable winner at
   the plaintext digest path and verifies a concurrent winner, so random ciphertext does not
   weaken deduplication and a 96-bit digest prefix is never treated as a nonce-uniqueness proof.

## Wired into

- `io.elmos.integrations.CasBackedArtifactStore` implements `SnapshotPorts.ArtifactStore` and
  `SnapshotPorts.ArtifactReader`, so snapshot archives land in the CAS with tenant, sensitivity,
  residency and retention attached instead of in a bare directory.
- `io.elmos.portfolio.TenantContentAddressedCache` delegates here instead of holding its own
  `HashMap`, which is what gave it a length-prefixed key and verify-on-read.
- `modules/persistence` owns `V65__content_addressed_store_and_action_cache.sql` and the
  V66/V67 metadata, resource-binding and durable ActionCache migrations.

## Explicitly not implemented here

These are real boundaries, not oversights. Do not read a green test run as covering them:

- **A production hit-rate number.** `ActionCacheBenchmark` runs a synthetic workload with simulated
  execution. It proves the key and invalidation behaviour at scale; it does not measure build times
  on a real repository. A production figure needs real repositories and should be compared against
  this harness, not substituted for it.
- **Certificate issuance and rotation.** `WorkloadIdentity` verifies a presented chain. Issuing,
  rotating and distributing those certificates is SPIRE's job, or whatever stands in for it.
- **Signing key custody.** `ResultSignature` verifies signatures and holds public keys. Private
  keys never enter this module; `sign` exists so the two halves cannot drift, and production
  signing belongs in a KMS.
- **Online certificate revocation.** The serial denylist is authoritative and checked first; OCSP
  and CRL fetching are not implemented.
- **Production certification.** The checked-in control-plane modes are single-host and explicitly
  `NOT_CERTIFIED`. Local tests do not prove multi-host object sharing, operator key custody,
  production PostgreSQL/RLS, recovery, scale, or independent verification.
- **An execution-path ActionCache caller.** The durable Java index and control-plane bean exist,
  but the typed runner/execution path does not yet call them; actuator status reports
  `executionCaller=NOT_WIRED`.
- **Cryptographic trust re-verification on a persisted ActionCache hit.** V67 stores the actual
  writer-attested/result-attestation decisions and the versioned complete-subject envelope digest;
  JDBC readback recomputes that digest and fails closed on drift. It deliberately does not persist
  the detached signature bytes, verifier trust policy/key generation or workload attestation, and
  it does not consult current revocation state on every hit. Actuator therefore still reports
  `PERSISTED_DECISION_NOT_CRYPTOGRAPHICALLY_REVERIFIED`.
- **Snapshot delete/archive lifecycle.** Capture registers atomic roots and handles known winner
  replacement safely. No production snapshot deletion API currently invokes root release, and an
  unknown database commit outcome deliberately retains the provisional root for reconciliation.
- **An atomic production legal-hold/deletion coordinator.** Catalogue loads now preserve the
  authoritative hold bit and the collector always checks it before tenant deletion. A hold applied
  after that load can still race the later object-store delete because no production GC epoch/row
  lock spans both systems. Executing collection remains unsupported until that handoff is atomic.
- **Live PostgreSQL execution without an authorized database.** `JdbcCasCatalog` and
  `JdbcActionCacheIndex` compile anywhere but their RLS/migration behavior requires a real
  PostgreSQL run. In-memory contracts and SQL-shape tests are engineering evidence only.
- **A background exporter thread.** `OtlpExporter.export` is called by whoever owns the schedule.
  A hidden thread makes "did this reach the collector" untestable.
