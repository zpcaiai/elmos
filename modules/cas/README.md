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
legacy caller shape. Its key-to-digest mapping is now a generation-bound `ACTION_CACHE` logical
root in `CasCatalog`; a second instance sharing the catalogue and object tier can resolve a result
from the complete input manifest without receiving the writer's reference. This is code-level
cross-instance support, not evidence of a production shared tier, workload authorization or
multi-host operation.

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
| `TenantEncryption`, `DirectoryTenantEncryption`, `KmsTenantEncryption`, `HttpKmsBrokerProvider`, `TenantEncryptedLocalCasStore` | versioned per-tenant AES-GCM envelopes, operator-mounted keyring or an HTTPS/mTLS KMS/HSM broker, workload identity plus opaque Secret References, rotation/revocation and tenant-namespaced ciphertext on local disk |
| `ActionKeyBuilder`, `ActionKey` | exact action key + component diffing for miss explanation |
| `ActionResultRecord` | `action-result.schema.json` shape, with the failure taxonomy |
| `LogRedaction` | secret removal before a log is cached and replayed |
| `CasAccessPolicy` | tenant / residency / clearance / permission-scope decision on every read |
| `ActionCache`, `ActionCacheIndex`, `JdbcActionCacheIndex`, `CachedActionExecutor` | outcomes, failure-cache policy, fresh read/execute authorization, sampled recompute, tenant-scoped quarantine and a durable reconstructable PostgreSQL index |
| `CasGarbageCollector` | reachability marking, generation-safe roots, retention/legal hold, atomic deletion-authority handoff and a reason-bound deletion manifest; any unresolved graph or missing/unavailable/unconfirmed authority retains bytes |
| `CasReconciler` | missing blobs, orphans, dangling manifests, incomplete uploads |
| `CasMetrics` | per-layer outcome counters, savings, miss explanation |
| `CasBatch`, `CasStore.putAll/getAll` | batch transfer with one existence probe and per-item failure isolation |
| `RegionalPlacement` | residency to region mapping, placement admission, replication backlog |
| `WorkloadIdentity` | PKIX chain validation, SPIFFE URI SAN, trust domain, clientAuth EKU, serial denylist |
| `ResultSignature` | Ed25519 detached signatures over a versioned complete result/authorization/risk/writer subject; V69 persists detached bytes and every hit can reverify current key validity/revocation and the exact envelope |
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
   legally held objects are also retained. An executing sweep additionally requires a
   deployment-owned `AtomicDeletionAuthority`. V76 commits a tenant/digest tombstone before bytes
   are touched; root, resource-binding, and legal-hold activation acquire the same lifecycle lock
   and fail while that tombstone exists. `PENDING` and `OUTCOME_UNKNOWN` remain non-repairable
   fences; only terminal `DELETED`, `MISSING`, or `FAILED` state permits durable publication to
   repair/verify bytes under the lock and then clear the tombstone. A boolean check followed by a separate delete is deliberately
   not accepted because it has a live-root publication race. Global-digest stores additionally
   require a privileged cross-tenant authority; the tenant-scoped catalogue fails closed instead.
   Missing, denied, unconfirmed, or unavailable authority retains the object.
   The addressable deletion record binds collected and retained reasons plus every unresolved
   reference, rather than only the object digests.
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
  `HashMap`; it uses a length-prefixed key, exact durable logical-root lookup, verify-on-read and
  generation-bound invalidation so a delayed release cannot remove a rebuilt result.
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
- **A tenant-API binding and trusted completion write-back for asynchronous execution.**
  `ActionCacheExecutionJobDispatcher` now composes fresh `CACHE_READ`/`EXECUTE` authorization with
  the durable `ExecutionJobPort`: a trusted hit avoids the queue, while an authorized miss is
  enqueued with a canonical tenant/action/payload digest and an uncertain enqueue remains
  reconciliation-required. The opt-in bean is still not invoked by a tenant API, and runner
  completion carries no signed `ActionResultRecord`, output manifest or attested writer, so it
  cannot be written back honestly. Actuator reports
  `ASYNC_DISPATCHER_AVAILABLE_NOT_BOUND_TO_TENANT_API` and
  `NOT_BOUND_RUNNER_COMPLETION_LACKS_SIGNED_ACTION_RESULT`.
- **ActionKey v1-to-v2 rollout is fail-closed, not transparent.** The v2 builder fixes composite
  collisions and component order under the explicit `elmos-action-key/2` domain; the cache,
  in-memory/JDBC indexes and dispatcher reject v1 before lookup or mutation, and the dispatcher
  binds that schema into every queued envelope. There is no collision-prone v1
  fallback and no automatic key migration. Operators must quiesce mixed-version writers/readers,
  invalidate or allow old ActionCache rows to expire under the controlled tenant lifecycle, and
  then roll out v2 atomically. Until that procedure is executed, old rows are cold data rather
  than compatible hits.
- **An externally operated current-trust service.** V69 persists the detached signature bytes;
  JDBC readback recomputes the complete-subject envelope, and `ResultSignature.Verifier` can
  cryptographically reverify every hit against current key validity and revocation. The
  control-plane default is deliberately `FAIL_CLOSED_CURRENT_TRUST_NOT_CONFIGURED`; an operator
  must supply and validate the non-local trust/revocation provider before hits are enabled.
- **A continuously operated snapshot lifecycle reconciler.** V72 now adds durable tenant work,
  fenced `SKIP LOCKED` leases, bounded cross-tenant scheduling, and materialization leases that
  serialize artifact reads with archive/GC. Production wiring is disabled until an operator sets
  a stable worker identity. A real multi-replica soak, crash/recovery drill, operational ownership,
  and authorization for destructive snapshot policy remain external `NOT_RUN` evidence.
- **An operated global-digest deletion authority.** V76 closes the in-database publication/delete
  race with durable tombstones and shared tenant/digest locking, and the Java catalogue can execute
  that protocol for a physically tenant-isolated store. It deliberately refuses `GLOBAL_SHARED`
  deletion because tenant RLS cannot prove the absence of another tenant's root. A privileged,
  independently reviewed cross-tenant authority plus crash/reconciliation and object-store lease
  evidence remain external `NOT_RUN`; production execution is therefore still unsupported.
- **A deployed production KMS/HSM and custody ceremony.** `KmsTenantEncryption` implements data-key
  envelopes, context binding, rotation/revocation, outage fail-closed behavior and exact plaintext
  key zeroization. `HttpKmsBrokerProvider` adds a dependency-free HTTPS/mTLS production boundary
  with a SPIFFE workload identity, opaque Secret References, version binding, bounded timeouts,
  redirect refusal and zeroizable binary DEK responses. It accepts no bearer token, PIN or private
  key value. No real broker/HSM endpoint, production identity material, operator ceremony,
  recovery drill or independent custody evidence is bundled or executed; those remain `NOT_RUN`.
- **Production PostgreSQL evidence.** Real PostgreSQL/Testcontainers harnesses cover migrations,
  forced RLS and JDBC readback when Docker is available. Their exact run status belongs in
  `.ai/TEST_RESULTS.md`; a local disposable database is not production availability, backup,
  recovery, scale or independent evidence.
- **A background exporter thread.** `OtlpExporter.export` is called by whoever owns the schedule.
  A hidden thread makes "did this reach the collector" untestable.
