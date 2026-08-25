# ELMOS Multimodal Intake Engine

This engine is the executable local reference runtime for the 50 Skills in
`elmos-multimodal-intake-skills-v1.0.0`. It turns immutable user assets into
tenant-scoped content IR, source anchors, project/package facts and bounded
task context. The ZIP is treated as untrusted specification input; none of its
scripts are imported or executed.

## What is implemented

- content-addressed local object storage plus a SQLite metadata/event store;
- tenant/project-bound, idempotent multipart upload and commit verification;
- magic/content validation, quarantine decisions and bounded parser adapters;
- Markdown/TXT/log, DOCX and PDF parsing with source anchors;
- explicit OCR, ASR, vision, antivirus and strong-sandbox provider ports;
- immutable, source-bound requirement/fusion/conflict projections with durable
  versions, review state and transactional outbox;
- a durable Skill 17 human-review workflow with a low-confidence queue,
  claim leases and fencing, immutable correction versions, optimistic locking,
  approve/reject/reopen/revert decisions, audit history, and four-channel
  propagation into the content index, requirements, project memory and
  downstream views;
- durable jobs, checkpoints and retention; migration-021 exact-decimal
  cost/ETA snapshots plus content-minimized immutable telemetry;
- a migration-018 Skill 27 deletion ledger with exact per-store/object/version
  commands, immutable execution and independent-verification receipts, legal
  holds, persisted backup deadlines, `UNKNOWN` reconciliation, separate audit
  digests, and transactional outbox events;
- SQLite-backed, actor-scoped versioned knowledge and project memory with
  lexical retrieval, provenance/ACL filtering, deletion propagation, outbox
  events and replayable index rebuilds; vector execution remains `NOT_RUN`;
- model capability, token budget, packing, pressure, compaction, recovery,
  rehydration, memory and integrity services;
- migration-019 production composition for Skills 29-36 and 39-40: immutable
  capability history/head rollback, explicitly separated current/cumulative
  token and cost ledgers, pressure forecast/action snapshots, tenant-CAS raw
  history, integrity-gated checkpoints, and idempotent restore attempts;
- migration-022 downstream Agent contexts, short-lived revocable single-use
  grants, a host-only Tool Gateway PEP and independently verified result links;
- safe folder/archive manifests plus a tenant-CAS archive publisher that
  scans the original before any complex parser, scans every extracted entry,
  and exposes the complete byte-bound object set by one atomic generation;
- project detection, classification, symbol candidates, repository maps and
  incremental package versions;
- an exact 50-entry Skill registry, a CLI/API facade, content-addressed
  OpenAPI/AsyncAPI contracts, Python/TypeScript/Java SDKs, and signed webhook
  helpers with a durable claim/reconcile queue whose transport, signer and
  public key epoch are host-injected;
- one `multimodal-operation-registry-v1` authority covering all 50 Skills and
  147 implemented operation pairs. The API and all three SDKs validate the
  pair before transport or dispatch; unregistered pairs are
  `REQUIRES_ADAPTER`. OpenAPI request/result envelopes share the same 50-way
  discriminator and every boundary error contains a bounded `trace_id`;
- authenticated, bounded one-shot SSE and read-only WebSocket progress routes
  for durable tasks and intake jobs, with content-bound cursors and resume;
- a Next.js workbench at `/intake` with explicit microphone permission and
  bounded local WAV capture, asset-role/model-read controls, explicit
  fail-closed cost/ETA refresh, deterministic package previews, a tenant-
  authenticated BFF SSE proxy that resumes bounded
  job batches with `Last-Event-ID`, and recoverable progress polling as the
  local/unavailable-stream fallback.
  Preview content digests are computed locally before upload; the BFF first
  establishes the caller-bound project scope and never accepts a browser-chosen
  engine project identity.

The local runtime is deliberately modular. The parser trust domain never
executes repository code, macros, install hooks, Dockerfiles or build tools.
Embedders can pass a trusted `runtime_factory` to the Python execute,
capabilities, or loopback HTTP composition APIs.  That factory—not request
JSON—owns sandbox executors, provisioned executable digests, password-handle
providers, and other external capabilities.  The standalone CLI intentionally
supplies none, so missing providers remain fail-closed and `NOT_RUN`.

## Evidence boundary

`CODE_IMPLEMENTED_LOCAL` means the handler and its local controls exist. It
does not mean an optional external provider is available. Until real,
authorized environments are exercised, results retain:

```text
external_evidence = NOT_RUN
certification = NOT_CERTIFIED
```

Missing antivirus keeps local TXT/Markdown/log parsing in `NEEDS_REVIEW`.
PDF, DOCX, image, audio, archive, and unknown/opaque content do not reach a
complex parser, OCR/ASR/vision provider, or archive publisher until a CLEAN
sandbox receipt is bound to the exact input bytes. Duplicate-key or otherwise
invalid scanner JSON cannot grant clearance. Missing OCR/ASR/vision after a
valid clearance marks the affected asset `NEEDS_REVIEW`, `NOT_RUN`, or
`BLOCKED` without inventing content. Unknown, expired, or stale model capacity
blocks a model call; the runtime never assumes an unlimited context window.

The composed dispatcher prefers the durable context bridge; direct pure
handlers remain available when no bridge is composed. Context usage keeps
current-window input and output reservation separate from cumulative provider
input, output and minor-unit cost. Missing host-verified provider usage stays
`UNKNOWN`. Restore/rollback requires a host-owned binding to the exact tenant,
project, checkpoint, restore request and operation. Integrity failures persist
with `side_effect_authorized=false`; request-authored authorization, policy,
capabilities or verification flags cannot change that gate.

Prompt-injection regexes are heuristic denial/review signals only. Tool access
and downstream Agent context require an authorized detector receipt bound to
the exact text or normalized block digest, detector/registry versions, policy,
tenant, and project. Package review likewise treats entry state and security
claims in request input as untrusted; readiness requires an authorized,
digest-bound host snapshot.

The public bridge exposes Skill 20 persistence operations (`upsert`, `query`,
`delete`, `repair`, `rebuild_status`), Skill 37 memory operations (`write`,
`query`, `delete`, `repair`, `rebuild_status`), and Skill 44 archive operations
(`extract`, `publish`, `expand_nested`) through the same versioned execution
envelope. `expand_nested` requires the persisted parent-lineage binding. Local
lexical query/repair remains `PARTIAL` while vector execution is `NOT_RUN`.
Archive publication remains `PARTIAL` until a runtime-owned scanner supplies
exact byte-bound CLEAN receipts; request content cannot select its scanner,
executable, CAS root, or resource limits. Outer formats are fixed-byte
identified at offset zero, ZIP methods and TAR modes are allowlisted, and
entry media/nested-archive state is derived from bytes rather than filenames.
The operation expands exactly one layer; detected nested containers are
scanned and preserved as opaque assets with deeper content explicitly
`NOT_INSPECTED`, so a later expansion must enter a new intake operation.
That later operation supplies the exact four-field `archive_parent` binding
(`parent_archive_digest`, `parent_entry_digest`,
`parent_entry_receipt_digest`, and `parent_generation_digest`). The runtime
resolves it only through a tenant/project-scoped published parent entry and
requires the submitted child bytes to equal the persisted entry digest.
Migration 017 persists an immutable root/node/entry lineage ledger. Every
layer shares the root policy and atomically charges declared entry count,
actual streamed uncompressed bytes, and absolute nested depth; a retry reuses
the same reservation and cannot reset or double-charge the global budget.
Missing lineage, policy drift, cross-tenant references, digest tampering,
depth exhaustion, aggregate quota exhaustion, and mismatched replay all fail
closed before a new readable CAS generation is published. Top-level calls
remain compatible; runtime-backed calls return `archive_root_digest`,
`archive_node_digest`, `archive_depth`, and a durable `archive_budget`
snapshot. Direct library calls without an `IntakeStore` may still publish one
top-level layer but report lineage persistence as `NOT_RUN` and cannot expand
nested children.
Skill 45's standalone declared-entry inspection remains explicitly
`DECLARED_LAYER_ONLY` with `global_budget_state=NOT_EVALUATED`; only the
store-backed publication/`expand_nested` path may report a durable global
budget snapshot.
Encrypted ZIP passwords may be resolved only after metadata confirms
encryption and only through an injected short-lived handle provider.  Its
`ArchivePasswordLease` must bind the handle digest, tenant, project, job,
purpose, expiry and revocation state; raw secrets are rejected and neither
handle nor secret is persisted.

The Web BFF may use a trusted host runtime by setting both
`ELMOS_MULTIMODAL_INTAKE_ENDPOINT` (an origin-only loopback HTTP URL) and
`ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN`. The execute path is fixed by code;
neither URL nor token is accepted from a browser request. If these server-only
settings are absent, the BFF keeps the local Python CLI path. Progress webhook
records contain only an opaque `endpoint-ref:*`; no delivery occurs until a
host injects a transport, `WebhookSigner`, producer/worker capabilities and an
ADMIN-authorized worker call. Browser/Skill requests cannot enqueue arbitrary
progress facts. A transport exception becomes `UNKNOWN`, never an automatic
retry; only an exact provider reconciliation receipt can make it retryable,
failed or delivered. The signer key ID must advance whenever key material
rotates, and execution receipts bind that public key epoch.

Both BFF transports treat a lost or late engine response as an unknown prior
outcome. The local subprocess is not killed at the response deadline; its
stdout/stderr remain drained so it can finish its durable receipt. The trusted
loopback request is aborted only to bound the HTTP waiter. In either case the
browser receives `MULTIMODAL_ENGINE_OUTCOME_RECONCILIATION_REQUIRED` with
automatic retry disabled, rather than being invited to create a second key and
repeat a provider or publication effect.

The loopback adapter exposes resumable read-only progress at fixed routes:

```text
GET /api/v1/multimodal-intake/progress/tasks/{task_id}/events
GET /api/v1/multimodal-intake/progress/jobs/{job_id}/events
GET /api/v1/multimodal-intake/progress/ws/tasks/{task_id}
GET /api/v1/multimodal-intake/progress/ws/jobs/{job_id}
```

SSE uses `Last-Event-ID` (or the exact `cursor` query parameter). WebSocket
accepts no client frames or subscription commands, sends one bounded durable
batch, then closes normally. Both surfaces inherit the server-bound
tenant/project/actor and Bearer token; request input cannot choose a database,
provider, path or alternate identity.

The browser consumes the job SSE surface through the same authenticated BFF;
native `EventSource` reconnect turns bounded batches into continuous state
sync without exposing the loopback bearer token. Each batch and event digest
is revalidated at the BFF and browser boundaries.
Direct registry dispatch for runtime-owned Skills 20, 21, 27, 37, and 44 requires
their bridges and returns `BRIDGE_UNAVAILABLE` when absent; it never
downgrades to an ephemeral retrieval, unpersisted durable transition, planned
memory write, or parser-like archive result.

Skill 27 `delete` is also bridge-only. A trusted inventory may create a durable
deletion job, but `deletion_state=DELETED_VERIFIED`, a digest-shaped host flag,
or a successful API response can never create a `DeletionProof`. Each command
binds tenant, project, store, object identity, object version, original byte
digest and byte count. A runtime-owned worker capability records the provider
evidence and the command becomes `UNKNOWN`; a distinct verifier identity and
capability must then record observed absence. The proof is assembled only when
every command is `VERIFIED`, no legal hold exists, and the persisted maximum
backup deletion deadline has passed. Until then the public `delete` and
`delete_status` operations return `BLOCKED` with deletion state not run. Audit
rows contain event digests rather than business content, while outbox payloads
remain separately replayable. Reopening the database preserves completed proof
identity; losing a worker response never makes the command automatically
retryable.

Skill 17 keeps the original asset immutable. Its `enqueue`, `enqueue_prepare`,
`enqueue_execute`, `list`, `get`, `current_correction`, `source_list`,
`source_get`, `claim`, `edit`, `approve`, `reject`, `reopen`, `revert`,
`propagation_status`, and `reservation_status` operations use the same
versioned execute envelope. Text, speaker, time-range,
bbox, table, requirement and conflict targets have exact typed locators. Every
mutation binds the actor, tenant, project, trusted review policy, canonical
request and idempotency key; concurrent edits require both the task version and
claim fence. Approval creates four durable propagation records. An effective
projection is materialized only after all four succeed, while any dispatched
but uncertain worker outcome becomes `UNKNOWN` and requires explicit
reconciliation. Worker credentials come only from host-owned trusted context;
browser input cannot register a worker or grant propagation authority.
`list` returns a fixed 19-field `human-review-task-summary-v1` document and
never includes the potentially large target, original value, or source
reference. `get` is the tenant-scoped REVIEW-authorized route for one complete
task. `current_correction` accepts exactly one `task_id` input and is the
tenant/project-scoped REVIEW-authorized recovery read for an `edit` whose
response was lost. It returns exactly one immutable 15-field correction only
after revalidating the task's current version/digest, exact target, and source
lineage. A task with correction version zero fails closed as
`HUMAN_REVIEW_CURRENT_CORRECTION_NOT_AVAILABLE`; the UI must not approve by
guessing from task state.

Approval now acquires a durable `human-review-target-head-reservation-v1`
before it inserts either the decision or any of the four propagation records.
The unique reservation key binds tenant, project, exact asset/content version,
target, snapshot, authoritative head version/value, task, correction digest,
decision, and a monotonic head-version fence. Two review tasks based on the
same head therefore have one winner: the loser receives
`HUMAN_REVIEW_TARGET_HEAD_RESERVED` before any propagation side effect exists.
Every internal propagation payload carries the reservation ID, fence, and
binding digest. `UNKNOWN` and `FAILED` reservations remain owned and cannot be
silently released; explicit reconciliation may return UNKNOWN to PROPAGATING,
and only an exact four-channel success may atomically advance the head and mark
the reservation APPLIED or REVERTED. Revert creates a child reservation for
the exact applied head and cannot bypass or reuse another decision's fence.
`reservation_status` is the bounded tenant/project REVIEW-authorized recovery
read for this immutable history. Approval response-loss recovery still replays
the original operation receipt and cannot allocate a second reservation.

`source_list` is a REVIEW-authorized, tenant/project/content-version-scoped
discovery read. It returns exact 13-field `human-review-source-summary-v1`
documents containing the real locator, confidence, head identity, public
original-value digest, and complete `human-review-source-ref-v2`, but never the
potentially large original value. Its opaque cursor binds the exact filters,
the complete validated summary collection, and a durable source-owned
generation. A collection contains at most 1,000 heads and a page at most 200.
The cursor is canonical, unpadded base64url over exactly `version`,
`filter_digest`, `collection_digest`, `collection_generation`, `target_kind`,
and `target_digest`; the SDKs recompute the tenant/project/content/version/kind
filter digest and bind continuation to the prior collection and last row.
`source_get` accepts the summary's exact target kind/digest and head version and
returns one exact 14-field `human-review-source-detail-v1` including the
authoritative original value. Both reads revalidate the asset,
snapshot/provenance/producer-at-snapshot-time trust, and current
decision/correction/four-channel propagation lineage.

`enqueue` is source-bound and no longer accepts browser-round-tripped target
JSON, original values, or confidence. Its exact source identity contains
`content_id`, `expected_asset_version`, `target_kind`, `target_digest`,
`expected_head_version`, `expected_snapshot_id`,
`expected_snapshot_digest`, and `expected_head_value_digest`; it also requires
the public `original_value_digest` and a reason. The service loads target,
authoritative value, and confidence in the same transaction, then performs all
four head/snapshot CAS checks before inserting the task. This rejects
same-asset-version A-to-B-to-A changes and avoids cross-language numeric
round-trip ambiguity such as BBOX `0.0` becoming `0`. The public digest contract
is `sha256:rfc8785-ijson-safeint-v1`, matching strict browser canonical JSON;
the digest verifies discovery continuity but is never treated as the source.

Browser response-loss recovery uses an opaque two-step protocol instead of
persisting the source input or private reason. `enqueue_prepare` accepts a
caller-created recovery handle and execute idempotency key plus the exact ten
source-bound enqueue fields. The database stores only SHA-256 digests of the
handle and execute key, while the immutable preparation binds the canonical
enqueue input by a `sha256:` request digest. `enqueue_execute` accepts only the
recovery handle; its outer receipt is replayed before expiry checks, then the
stored input is loaded and enqueued in the same transaction. Existing records
return exact `human-review-enqueue-preparation-v1` documents in `PREPARED`,
`EXECUTED`, or `EXPIRED`; an unknown handle returns exact
`human-review-enqueue-preparation-absence-v1` with `ABSENT`. Only `EXECUTED`,
`EXPIRED`, and `ABSENT` set `safe_to_clear=true`. Preparations expire after 24
hours, with at most 100 active and 10,000 retained records per
tenant/project/actor; rows are never silently deleted. The stable result codes
are `HUMAN_REVIEW_ENQUEUE_PREPARED`,
`HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION`,
`HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT`, and
`HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED`.

The trusted parser composition publishes source snapshots and initial heads in
the same SQLite transaction as final content blocks and the parse report.
Text, Markdown/log, PDF page text, OCR text and bbox regions, ASR transcript,
time range and speaker labels, and DOCX table cells map to exact TEXT, BBOX,
TIME_RANGE, SPEAKER, and TABLE locators. The producer uses a request-inaccessible
opaque host capability and a separate `CONTENT_BLOCK`/`SOURCE_ANCHOR` producer
identity; propagation-worker authority cannot publish sources. REQUIREMENT and
CONFLICT have no parser producer in this repository and fail with
`REQUIRES_SOURCE_PRODUCER` until a trusted domain producer registers their
immutable source facts. Browser echoes cannot fill that gap.

The legacy `workload:human-review-correction-store` path also calls
`_publish_human_review_correction_source` in the same correction transaction.
It publishes `human-review-correction-authoritative-source-v1` as an independent
`TRUSTED_DERIVATION` snapshot/head for the new asset version at
`human_review_corrections/<correction_id>/value`; it never inherits a parser
head and never treats a browser echo as a source. Its fixed confidence `1.0`
means only explicit human-authored source identity. `approval_state` and
`rebuild_state` remain `NOT_RUN`, the source is not approved or certified, and
enqueue still requires an independent review workflow.
Hosts that expose the browser workflow must explicitly allow the exact
`enqueue`, `enqueue_prepare`, `enqueue_execute`, `claim`, `edit`, `approve`,
`reject`, `reopen`, and `revert` actions under the caller-bound
`policy.human_review`; absence of that binding fails closed. The workbench
retains an unfinished claim's original idempotency key and opaque token only in
tab-scoped session storage, so response-loss recovery replays the same claim
instead of creating a second lease.

## Local invocation

The CLI reads one bounded JSON request from standard input, keeping document
text and credentials out of argv and process listings:

```bash
PYTHONPATH=engines/multimodal-intake-engine/src \
python3.12 -m elmos_multimodal_intake.cli execute \
  --data-root /absolute/private/elmos-multimodal-intake \
  --tenant-id tenant-a \
  --project-id project-a \
  --actor-id user:reviewer < request.json
```

The request schema is exact:

```json
{
  "schema_version": "1.0.0",
  "skill": "elmos-markdown-text-log-parser",
  "operation": "parse",
  "tenant_id": "tenant-a",
  "project_id": "project-a",
  "actor_id": "user:reviewer",
  "idempotency_key": "request-00000001",
  "trace_id": "trace-example",
  "input": {"asset_id": "asset-example"}
}
```

Mutating retries must reuse the same idempotency key and identical payload.
Reusing a key for different bytes or metadata fails closed.

Every result is stored as an actor/tenant/project/Skill-scoped execution
receipt. Exact retries survive process restart and replay the original HTTP
status and semantic result without repeating side effects. Because `trace_id`
is observability metadata rather than idempotent identity, a retry echoes its
current trace and receives a recomputed result digest. Key reuse with a
different canonical request digest returns a conflict.
Completed receipt bodies are stored as bounded canonical UTF-8 with their
SHA-256 digest and are revalidated before replay. Rows created before that
digest binding, non-canonical bytes, or an offline-modified body fail closed to
explicit reconciliation. Core outbox events use the same canonical-payload
binding; a duplicate key is accepted only when aggregate, event type, payload
and digest all match exactly. Legacy outbox rows without a payload digest are
never published or replayed automatically.
Receipts also bind a path/secret-free execution-environment digest covering
the runtime factory, sandbox/provider implementation, provisioned executable
digests, upload limits, password-provider identity, progress transport and
webhook signing-key epoch. Configuration drift therefore conflicts instead of
replaying a result produced under a different runtime.
The outer receipt lease is renewed before and during dispatch. A failure before
dispatch releases the side-effect-free claim. Immediately before invoking the
handler, the runtime commits a durable dispatch-start marker. That marker is
never eligible for lease-expiry takeover; the exact original owner can still
publish a late result, and completion response loss is retried only at that
fenced database write. A handler exception, malformed result, heartbeat
uncertainty, process crash, or unresolved completion failure therefore becomes
`EXECUTION_OUTCOME_RECONCILIATION_REQUIRED` with automatic retry disabled. The
same idempotency key never invokes the handler blindly again.

The CLI is an internal subprocess transport for the checked-in BFF. It adds a
bounded `_http_status` field after validating the public result/error document;
that private field is not part of the OpenAPI HTTP envelope and is removed by
the BFF runner before a response reaches the browser. `result_digest` covers
the public body only: validators remove `_http_status` before recomputing it.

Policy-sensitive domain Skills never accept consent, provider allowlists,
evidence registries, tool grants, or authoritative state from `input`. The host
may provision those facts in
`<data-root>/trusted-context-v1.json`. That file is limited to 1 MiB, must be a
regular file owned by the runtime user, and must not be group/world writable.
It uses exact actor scope:

```json
{
  "schema_version": "1.0",
  "bindings": [
    {
      "tenant_id": "tenant-a",
      "project_id": "project-a",
      "actor_id": "user:reviewer",
      "context_epoch": "tenant-a-policy-2026-08-20-1",
      "policy": {},
      "capabilities": {}
    }
  ]
}
```

No matching binding means empty policy/capabilities and therefore a deliberate
fail-closed result for operations that require trusted authority or external
facts. Hosts must advance `context_epoch` whenever a grant, revocation, policy,
provider registry, or trusted evidence set changes. Execution receipts bind the
epoch and canonical policy/capability digests, so a stale result is never
replayed under changed authority.

### Durable Skills14-16 content projections

Production composition routes requirement extraction, multi-asset fusion and
version/conflict detection through `ContentProjectionBridge`. Its independent
`content_projection.sqlite3` is created only below an owner-owned `0700`
directory as a non-symlink regular `0600` file. Every immutable version binds
the authenticated tenant/project/actor, authoritative host package version,
exact source content/provenance/version digests, request digest, output digest,
review state and outbox fact. Reusing an idempotency key with drift conflicts.

Caller input cannot assert approval, verification or resolution. Critical
conflicts, partial output and low confidence remain `NEEDS_REVIEW`; an existing
human-review link is accepted only from a same-scope host capability. Source
text is evaluated in memory but is not copied into source-binding rows, outbox
payloads or telemetry.

### Durable Skills22-23 cost and telemetry

Migration 021 persists cost estimates, exact-decimal line items, traces and
redacted events by tenant/project and immutable subject sequence. P50/P95 are
machine-wall-clock estimates only. Estimated and actual quantity/cost columns
are distinct; actuals become `RECONCILED` only when a host receipt binds the
same scope, subject, estimate digest, evidence digest and real byte count.
Missing or invalid evidence remains `PENDING` or `UNKNOWN`.

The Workbench explicitly requests an estimate for its current content-minimized
stage plan and displays calibration status plus actuals state. A missing trusted
history/price policy is shown as a blocked result. The client uses a digest-bound
idempotency key and never automatically retries the estimate mutation.

### Durable Skill24 evaluation evidence

Skill24 has no caller-attested fallback. Its runtime bridge binds one exact
tenant/project, validation profile, authorized dataset version, rubric version,
subject artifact/configuration tuple, and the immutable 240-ID source acceptance
catalog. The host-owned `policy.evaluation` binds dataset, rubric, and acceptance
catalog SHA-256 values; `capabilities.evaluation_catalog` supplies the exact
authorized manifests and independent verifier identities.

Observed bytes arrive only as bounded base64. The bridge computes their real
byte count and SHA-256, stores them in a tenant/project-partitioned CAS, and
records evaluator results in `evaluation.sqlite3`. It rejects caller fields such
as `status`, score, digest, byte count, or verifier identity. Local execution is
limited to the fixed in-process evaluator registry; uploaded or repository
content cannot select a command, import, plugin, or subprocess. Exact retries
replay one durable run, while key reuse for different bytes conflicts.

An executor can produce at most `AWAITING_INDEPENDENT_VERIFICATION`. A separately
authorized actor must use `verify` to reread every artifact, recheck bytes/digest,
and replay the exact evaluator and case manifest. Self-verification is forbidden,
failures cannot be overridden, and external cases stay `NOT_RUN`. Even a locally
verified pass remains engineering evidence with external evidence `NOT_RUN` and
production certification `NOT_CERTIFIED`.

### Durable Skill28 downstream context and Tool Gateway

Skill28 uses migration 022 for tenant/project-scoped `AgentContext`, single-use
context grants, gateway execution receipts, independently verified result links,
operation receipts, and an immutable-payload outbox. Public requests may select
only opaque source/tool/result receipt IDs from the host-owned
`capabilities.downstream_agent_receipts` registry. They cannot supply a command,
module, plugin, subprocess, executable, `tool_id`, capability body, raw bytes, or
base64 asset content.

`build_context` requires verified normalized CONTENT_BLOCK, REQUIREMENT, and
REPOSITORY_MAP receipts for the same subject and exact package version. Every
source has an immutable digest and anchor; the prompt projection explicitly
contains no raw assets and content never creates tool authority. Tool receipts
must be independently verified, allowlisted by host policy, subject/scope/input
digest bound, short-lived, revocable, and single-use.

Only a host-composed `DownstreamToolGateway` owns adapters and may claim a grant.
Repository content cannot register or select an adapter. A lost response,
timeout, invalid receipt, or unverifiable outcome becomes `UNKNOWN` and disables
automatic retry. Gateway composition requires a result-verifier object distinct
from every adapter and binds its exact verifier identity. A result is written
back only through a host-verified or
signature-verified receipt whose executor and verifier differ; the independent
link points to content-addressed result bytes and never mutates original source
records.

### Durable project-package lifecycle

Skills 38, 41-43 and 46-50 use migration 020 for tenant/project-scoped package
sessions. Folder manifests are appended in bounded chunks of at most 1,000
entries and finalized only at the declared count (up to 100,000); every entry
has a canonical digest and the immutable version has a Merkle root. Preview is
server-paginated in pages of at most 200 through a scope-, version-, and
manifest-bound cursor. Incremental plans require exact old/new package versions.

Per-file upload negotiation records every server-confirmed part and reports
`PARTIAL` until all negotiated parts exist. Confirmation includes canonical
base64 bytes; the server recomputes each part's size and SHA-256, stores it in
tenant CAS, rereads all parts in order, and verifies the negotiated whole-file
size and digest before publishing the final CAS object. Role and model-read changes use
optimistic versions plus immutable override/undo audit rows; quarantine or any
other non-`CLEARED` security state cannot be overridden into model readability.
Profile, classification, context-graph, and symbol artifacts bind one package
version and have rebuild/status/rollback histories. Repository bytes are parsed
as data and never executed. Non-Python heuristic symbol extraction remains
`PARTIAL` rather than claiming native parser equivalence.

## Supported versus planned inputs

The v1 direct allowlist covers text, Markdown/MDX/log, supported audio and
image formats, PDF, DOCX/DOC through an isolated converter, folders, ZIP,
TAR, TAR.GZ/TGZ and GZIP. Video, XLSX/CSV, PPTX, HTML/URL, 7z/RAR, tar.xz,
tar.zst, Git ingestion and Figma remain planned and return an explicit
unsupported result.

## Qualification

The source package importer and runtime tests are intentionally separate:

```bash
python3 tooling/integrate_multimodal_intake_skills.py --check
python3 -m pytest engines/multimodal-intake-engine/tests
```

Browser journeys live in
`apps/web-console/e2e/multimodal-intake.spec.ts`. Local tests may use protocol
fakes to exercise routing and failure behavior; such fakes never upgrade the
external evidence fields.
