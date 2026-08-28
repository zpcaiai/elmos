# Runbook — Content-Addressed Store and Action Cache

Component: `modules/cas` (`io.elmos.cas`)
Schemas: `V65_1__content_addressed_store_and_action_cache.sql`,
`V66__cas_resource_bindings_and_complete_metadata.sql`, and
`V67__durable_action_cache_index.sql`
Alert rules: `io.elmos.cas.CasAlerting.defaultRules()`
Telemetry scope: `io.elmos.cas` (OTLP), metrics `cas.*`

## Before anything else

Two facts decide almost every response below.

1. **Content is immutable and self-verifying.** If a digest and its bytes disagree, the bytes are
   wrong — never the digest. Never "fix" an object by re-recording its digest.
2. **The local tier is disposable, the shared tier is not.** Anything in `pendingDurability()`
   exists in exactly one place. Do not restart, drain, or scale down a runner with a non-empty
   durability backlog until it has flushed.

Quick health read:

```java
CasAlerting.HealthSnapshot.from(tieredStore, actionCache, metrics, reconciliationReport,
        corruptionEventsInWindow, oldestPendingDurabilityAgeMillis,
        outstandingReplications, telemetryExportFailures);
```

---

## 1. `CAS_POISONING_DETECTED` (PAGE)

**Means:** an object's stored bytes did not hash to its digest. The store has already moved it to
`quarantine/` (local tier) or dropped it from the heap tier and recorded a
`cas_quarantine_events` row.

**Blast radius question first:** was the object *read* before it was caught? Search traces for
`cas.store.get` spans with `cas.digest` equal to the quarantined digest and a status of OK before
the incident. If any exist, treat every action result produced by those consumers as suspect.

1. Identify the tier: `cas.tier` on the failing span, or the store name in the exception message.
2. If the object is durable in L2, delete the local copy and let read-through repopulate.
   `TieredCasStore.get` already does this automatically for L1; a repeat means L2 is the poisoned
   copy.
3. If L2 is poisoned, the object must be **rebuilt, not repaired**. Find its producing action:
   `SELECT * FROM cas_action_cache_entries WHERE output_manifest_hex = '<hex>'`. Invalidate those
   entries (`ActionCache.invalidate`), then rerun.
4. Quarantine the producing node if more than one object from it failed. Always bind the
   authenticated tenant: `ActionCache.quarantineNode(tenantId, nodeId, reason)`. The unscoped
   compatibility overload is not a production operation.
5. Preserve the quarantined file. It is the only evidence of what the corruption looked like.

**Do not** clear the quarantine directory to free space during the incident.

---

## 2. `CAS_NODE_QUARANTINED` (CRITICAL)

**Means:** a sampled recomputation produced a different output manifest than the cached one. Either
the cache was poisoned or the action is nondeterministic.

1. `ActionCache.nondeterminismIncidents()` gives the affected key and node.
2. Decide which it is: rerun the same action on a *different* node. Same output as the cached one →
   the quarantined node is bad. Different output on both → the action is nondeterministic and the
   node is innocent.
3. Nondeterministic action: find the uncaptured input. The usual causes, in order of frequency —
   a timestamp baked into an artifact, a map iteration order, a parallel build writing in
   completion order, an environment variable declared `ignored` in the
   `ActionKeyBuilder.EnvironmentContract` that turned out not to be.
4. Bad node: keep it quarantined, take it out of the pool, and check its disk.
5. Re-admitting a node is deliberate and manual. There is no timeout that does it for you.

---

## 3. `CAS_DURABILITY_BACKLOG` (WARNING, or PAGE when stale)

**Means:** objects exist only in the local tier. PAGE severity means the oldest has been waiting
past the age threshold, which is the shape of a stuck backlog rather than a busy one.

1. `TieredCasStore.pendingDurability()` — how many, and how large.
2. Try `flushWriteBack()` directly. If it throws, the shared tier is the problem: go to §4.
3. **Do not** drain or terminate the runner. Eviction already refuses to touch these objects, but
   terminating the process discards them regardless.
4. If the shared tier will be down for a while, mirror the local CAS root
   (`LocalDiskCasStore.root()/blobs`) somewhere durable before doing anything else. The layout is
   `sha256/aa/bb/<hex>` and is portable — `promote()` will accept the files back.

---

## 4. Shared tier (S3/MinIO) unavailable

**Symptoms:** `IllegalStateException: ... failed with 5xx`, or
`CasAccessDeniedException: OBJECT_STORE_REJECTED_CREDENTIALS`.

- **5xx / timeouts:** `S3CasStore` already retries `maximumAttempts` times on 5xx and transport
  failures. Sustained failure is an outage: the platform continues to serve L1 hits and new work
  accumulates durability backlog (§3). Reads that miss L1 will fail — that is correct, a miss is
  better than a wrong answer.
- **403:** almost always one of three things, in this order —
  1. **clock skew.** SigV4 signs `x-amz-date`; more than ~15 minutes of drift is rejected. Check
     the host clock first, it is the cheapest to rule out.
  2. **credential rotation** that reached the object store before it reached the runner.
  3. **path-style vs virtual-host addressing.** MinIO needs `pathStyleAccess = true`; the host
     header is part of the signature, so getting this wrong signs the wrong string.
- A 403 is never retried on purpose. Retrying an auth failure turns a config problem into a rate
  limit problem.

---

## 5. `CAS_HIT_RATE_COLLAPSE` (WARNING)

**Means:** the action cache is below target over a meaningful sample. Nothing is lost; money and
time are.

1. `CasMetrics.explain()` — reasons ranked by count. `ACTION/MISS/NO_ENTRY` dominating means keys
   are changing; `DENIED` dominating is an authorisation problem wearing a performance costume.
2. For a changing key, take one action that should have hit and diff it:
   `previousKey.explainDifference(currentKey)` names the component that moved.
3. The usual culprits: a rebuilt toolchain image with a new digest, a rule pack version bump, a
   `SOURCE_DATE_EPOCH` that is not pinned, a working directory containing a run id.
4. Confirm the fix with the benchmark rather than by watching the dashboard:
   `java io.elmos.cas.ActionCacheBenchmark 200 25 report.md`.

**Never** "fix" a low hit rate by removing inputs from the action key. Every removal is a
correctness risk, and the failure mode is silent wrong output rather than a slow build.

---

## 6. `CAS_RECONCILIATION_DRIFT`

Four separate findings, three severities.

| Key | Severity | Meaning | Action |
|---|---|---|---|
| `missing-objects` | CRITICAL | Something references bytes that are not in any tier | Data loss or a premature collection. Check the most recent `cas_deletion_manifests` for the digest. If it was collected, the reference table was incomplete when the collector ran — find out why before running it again. |
| `orphans` | INFO | Unreferenced bytes accumulating | Cost, not risk. Let the collector handle it. |
| `incomplete-uploads` | WARNING | Sessions passing their deadline | Usually a client crash-looping. Check `cas_upload_sessions` for a common tenant or session-id pattern. |
| `replication` | WARNING | Regional replicas falling behind | `RegionalPlacement.Router.replicate()`. If the backlog is for a residency with `requiresReplication`, writes are already blocking on it. |

---

## 7. The collector deleted something it should not have

This is the failure this component is built to prevent, so start by disbelieving it.

1. Find the batch: `SELECT * FROM cas_deletion_manifests WHERE organization_id = ...` — the table
   is append-only, so what it says is what happened.
2. `DeletionManifest.collected()` lists every digest with the reason it was collected
   (`UNREACHABLE` or `TENANT_DELETION`), and `retained()` lists everything kept, with its reason.
3. Check `unresolvedReferences()` first. A non-empty list blocks the whole sweep and retains every
   object not already covered by a more precise reason as `UNRESOLVED_ROOT_GRAPH`; fix the root
   store/resolver/catalog fault before rerunning. It is never safe to bypass this guard to recover
   space.
4. If the digest appears with `UNREACHABLE`, the reference genuinely did not exist at mark time.
   The bug is upstream, in whatever failed to register the root — not in the collector.
5. **Before rerunning any collection**, switch the policy to `dryRun` and compare `collected()`
   against expectations. The dry run writes a manifest too.

The current single-host engineering collector does not hold an authoritative catalogue lock from
mark through object-store deletion. A legal hold created after the catalogue view was loaded can
race an executing sweep. Until a production GC coordinator supplies an atomic hold recheck/lock,
use this path only for dry-run engineering evidence; `SINGLE_HOST / NOT_CERTIFIED` is not approval
to execute production deletion.

Recovery is rebuild, not undelete. Content-addressed objects have no tombstone.

---

## 8. Restoring a cold cache

There is no such thing as a corrupt cache that needs repair — an empty cache is always safe.

1. Stop writers.
2. Invalidate entries through the tenant-scoped `ActionCache`/`ActionCacheIndex` API. The active
   index is durable in `cas_action_cache_entries`; direct SQL must first establish the same
   transaction-local `app.organization_id` RLS scope and must preserve invalidation evidence.
3. Objects themselves need not be dropped. They are content-addressed: a wrong object cannot be
   confused with a right one.
4. Restart writers. Expect one cold round: the benchmark's `unchanged-rerun` scenario is what the
   second round should look like.

---

## Escalation

| Situation | Escalate to |
|---|---|
| Poisoning with evidence of a read before detection | Security, immediately. Treat as a supply-chain incident. |
| Cross-tenant read that was allowed | Security, immediately. `CasAccessPolicy` denies by default, so an allow is either a config error or a bug. |
| Data loss confirmed via §7 | Platform lead + the owning tenant's account team. |
| Backlog that cannot flush and cannot be mirrored | Platform lead before any node is recycled. |
