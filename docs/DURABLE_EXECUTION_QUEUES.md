# Durable execution queues

Project Generation, Language Translation, and Spring Modernization use their
existing tenant-bound job/run state as the authoritative queue record. A
separate filesystem control directory grants bounded execution authority:

```text
<runner-root>/.durable-queue/
  control/<business-line>.lock
  leases/<business-line>/<sha256(tenant)>/<job-id>.json|properties
  receipts/<business-line>/<sha256(tenant)>/<job-id>.json|properties
  dead-letter/<business-line>/expired-*|corrupt-*
```

The tenant identifier is never used as a path segment. Every lease binds the
business line, tenant digest, stable job/run UUID, immutable input digest,
unique worker owner, acquisition time, heartbeat, and expiry. Capacity
admission and lease creation occur under an OS-backed exclusive control lock.
Workers heartbeat at one third of the lease TTL. A lost lease terminates the
owned child process and blocks publication.

## Failure taxonomy

| Code | Class | Retry behavior |
|---|---|---|
| `QUEUE_GLOBAL_CAPACITY_REACHED` | capacity | queued with bounded jitter |
| `QUEUE_TENANT_CAPACITY_REACHED` | fairness | queued with bounded jitter |
| `QUEUE_JOB_ALREADY_LEASED` | duplicate worker | queued; no second execution |
| `QUEUE_CONTROL_LOCK_UNAVAILABLE` | environment | queued in Web runners |
| `QUEUE_ITEM_EXPIRED` | policy / TTL | terminal `BLOCKED` |
| `QUEUE_LEASE_LOST` | ownership / liveness | child terminated, terminal `BLOCKED` |
| corrupt lease | integrity | moved to dead letter and never trusted |
| expired lease | worker loss | moved to dead letter; capacity may be reclaimed |

Queue admission retry does not repeat an external effect. Generation and
translation are local artifact pipelines. Spring resumes by creating a new
traceable retry after an interrupted execution; previously completed artifacts
remain digest checked. Repository Push and PR use their own exact commit and
idempotency receipts and are not executed by these queues.

## Checkpoint and recovery contract

- Generation persists `job.json`, the approved analysis, synthesis request,
  logs, verification, artifacts, and archive atomically below the tenant/job
  root. Its lease input digest is the synthesis request SHA-256.
- Translation persists `job.json`, logs, route/case identity, pipeline report,
  build result, and archive atomically. Its lease input digest covers repository
  ref, case bundle, and exact source/target route.
- Spring persists `state.json`, input fingerprint, stage/events, promoted FCM,
  independent decision, and artifact digests. On worker restart, a running
  attempt becomes `BLOCKED` and requires an idempotent, traceable retry.
- Successful receipts are immutable progress evidence. Expired/corrupt leases
  remain visible in dead letter rather than disappearing from metrics.
- Queue records older than the configured TTL fail closed. Active leases never
  exceed the global or per-tenant capacity.

## Configuration

Web runner variables use the business-line prefix:

```text
ELMOS_GENERATION_GLOBAL_CAPACITY=2
ELMOS_GENERATION_TENANT_CAPACITY=1
ELMOS_GENERATION_QUEUE_TTL_SECONDS=3600
ELMOS_GENERATION_LEASE_TTL_SECONDS=120

ELMOS_TRANSLATION_GLOBAL_CAPACITY=2
ELMOS_TRANSLATION_TENANT_CAPACITY=1
ELMOS_TRANSLATION_QUEUE_TTL_SECONDS=3600
ELMOS_TRANSLATION_LEASE_TTL_SECONDS=120
```

Spring worker variables:

```text
ELMOS_SPRING_UPGRADE_GLOBAL_CAPACITY=2
ELMOS_SPRING_UPGRADE_TENANT_CAPACITY=1
ELMOS_SPRING_UPGRADE_QUEUE_TTL_SECONDS=3600
ELMOS_SPRING_UPGRADE_LEASE_TTL_SECONDS=120
```

TTL must be 60 seconds to 30 days. Lease TTL must be 30 seconds to one hour.
Tenant capacity cannot exceed global capacity. The runner root must be durable,
tenant-isolated storage; local disk is not a multi-region coordination claim.

## Evidence boundary

Unit tests inject tenant/global saturation, missed heartbeats, stale items, and
lease replacement. TypeScript compilation and Java tests are local engineering
evidence. Worker-kill, shared-volume multi-replica, disaster restore, real
provider outage, and independent representative-portfolio exercises remain
`NOT_RUN` until executed in an authorized environment.
