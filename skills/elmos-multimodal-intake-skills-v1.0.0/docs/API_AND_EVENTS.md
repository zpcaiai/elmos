# API and Event Contract

The exact route names may be adapted to the existing Elmos API, but semantics, idempotency, authorization, versioning and durable state must remain.

## 1. Common requirements

### Headers

```http
Authorization: Bearer <token>
Idempotency-Key: <opaque-client-key>
X-Tenant-Id: <tenant>          # only if existing identity architecture requires it
X-Project-Id: <project>
X-Trace-Id: <optional client correlation>
```

Never trust tenant/project headers without validating them against the authenticated principal.

### Asynchronous response

```json
{
  "job_id": "job_01...",
  "resource_id": "pkg_01...",
  "status": "UPLOADED",
  "status_url": "/api/v1/jobs/job_01...",
  "events_url": "/api/v1/jobs/job_01.../events",
  "trace_id": "trace_01..."
}
```

### Error

```json
{
  "error": {
    "code": "ARCHIVE_PATH_TRAVERSAL",
    "message": "The archive contains an unsafe entry.",
    "retryable": false,
    "trace_id": "trace_01...",
    "details": {
      "entry_id": "entry_01..."
    }
  }
}
```

Do not include host paths, secrets, passwords, raw file content or provider credentials in errors.

## 2. Input sessions and assets

```text
POST   /api/v1/input-sessions
GET    /api/v1/input-sessions/{sessionId}
POST   /api/v1/input-sessions/{sessionId}:cancel
POST   /api/v1/input-sessions/{sessionId}:submit
GET    /api/v1/input-sessions/{sessionId}/assets
POST   /api/v1/input-sessions/{sessionId}/assets:init-upload
POST   /api/v1/uploads/{uploadId}/parts
PUT    /api/v1/uploads/{uploadId}/parts/{partNumber}
POST   /api/v1/uploads/{uploadId}:complete
POST   /api/v1/uploads/{uploadId}:abort
GET    /api/v1/uploads/{uploadId}
GET    /api/v1/assets/{assetId}
GET    /api/v1/assets/{assetId}/preview
GET    /api/v1/assets/{assetId}/content
DELETE /api/v1/assets/{assetId}
```

`DELETE` creates a deletion request; it is not proof that every derivative was immediately erased.

## 3. Folder input

```text
POST /api/v1/input-sessions/{sessionId}/folders
POST /api/v1/folder-inputs/{folderInputId}/manifest
POST /api/v1/folder-inputs/{folderInputId}:negotiate
POST /api/v1/folder-inputs/{folderInputId}:complete
POST /api/v1/folder-inputs/{folderInputId}:pause
POST /api/v1/folder-inputs/{folderInputId}:resume
GET  /api/v1/folder-inputs/{folderInputId}/progress
GET  /api/v1/folder-inputs/{folderInputId}/missing-entries
```

The manifest contains only normalized relative paths. Completion verifies each expected file and the manifest digest.

## 4. Archives

```text
POST /api/v1/input-sessions/{sessionId}/archives
POST /api/v1/archives/{archiveId}:inspect
POST /api/v1/archives/{archiveId}:extract
POST /api/v1/archives/{archiveId}:provide-password
GET  /api/v1/archives/{archiveId}
GET  /api/v1/archives/{archiveId}/entries
GET  /api/v1/archives/{archiveId}/security-findings
POST /api/v1/archives/{archiveId}/nested/{entryId}:inspect
POST /api/v1/archives/{archiveId}/nested/{entryId}:extract
```

Password submission returns only a short-lived secret handle; the password value must not be returned or persisted in normal application records.

## 5. Packages and versions

```text
GET  /api/v1/packages/{packageId}
GET  /api/v1/packages/{packageId}/versions
GET  /api/v1/package-versions/{versionId}
GET  /api/v1/package-versions/{versionId}/manifest
GET  /api/v1/package-versions/{versionId}/tree
GET  /api/v1/package-versions/{versionId}/inventory
GET  /api/v1/package-versions/{versionId}/project-profile
GET  /api/v1/package-versions/{versionId}/repository-map
GET  /api/v1/package-versions/{versionId}/security-findings
POST /api/v1/package-versions/{versionId}:create-analysis-view
POST /api/v1/package-versions/{versionId}:detect-project-roots
POST /api/v1/package-versions/{versionId}:index
POST /api/v1/package-versions/{versionId}:reindex
POST /api/v1/package-versions/{versionId}:compare
POST /api/v1/package-versions/{versionId}:activate
POST /api/v1/package-versions/{versionId}:rollback
```

A running task is pinned to a package version. `activate` affects future tasks unless an explicit task rebase operation is approved.

## 6. Parsed content and review

```text
GET   /api/v1/assets/{assetId}/blocks
GET   /api/v1/content-blocks/{blockId}
GET   /api/v1/content-blocks/{blockId}/source
PATCH /api/v1/content-blocks/{blockId}:correct
POST  /api/v1/content-blocks/{blockId}:reprocess
GET   /api/v1/packages/{packageId}/requirements
GET   /api/v1/packages/{packageId}/conflicts
POST  /api/v1/conflicts/{conflictId}:resolve
GET   /api/v1/review-tasks
POST  /api/v1/review-tasks/{reviewTaskId}:complete
```

Corrections create a new content version and preserve the original.

## 7. Tasks and durable execution

```text
POST /api/v1/tasks
GET  /api/v1/tasks/{taskId}
POST /api/v1/tasks/{taskId}:pause
POST /api/v1/tasks/{taskId}:resume
POST /api/v1/tasks/{taskId}:cancel
POST /api/v1/tasks/{taskId}:retry
GET  /api/v1/tasks/{taskId}/runs
GET  /api/v1/task-runs/{runId}/nodes
GET  /api/v1/task-runs/{runId}/checkpoints
POST /api/v1/task-runs/{runId}/checkpoints/{checkpointId}:restore
GET  /api/v1/task-runs/{runId}/progress
GET  /api/v1/task-runs/{runId}/cost
GET  /api/v1/task-runs/{runId}/evidence
```

Client connection state is not task state. A closed SSE/WebSocket connection does not cancel a task.

## 8. Context

```text
GET  /api/v1/task-runs/{runId}/context
GET  /api/v1/task-runs/{runId}/context/usage
GET  /api/v1/task-runs/{runId}/context/sources
GET  /api/v1/task-runs/{runId}/context/load-plans
GET  /api/v1/task-runs/{runId}/context/integrity
POST /api/v1/task-runs/{runId}/context:recalculate
POST /api/v1/task-runs/{runId}/context:compact
POST /api/v1/task-runs/{runId}/context:rehydrate
POST /api/v1/task-runs/{runId}/context:pin
POST /api/v1/task-runs/{runId}/context:unpin
```

Example usage response:

```json
{
  "model": {
    "provider": "openai",
    "model_id": "configured-model",
    "capability_snapshot_id": "mcs_01...",
    "context_window_tokens": 1050000,
    "max_output_tokens": 128000,
    "as_of": "2026-08-19"
  },
  "usage": {
    "system_tokens": 12800,
    "policy_tokens": 5200,
    "skill_tokens": 19300,
    "conversation_tokens": 28600,
    "document_tokens": 214000,
    "audio_transcript_tokens": 63000,
    "image_equivalent_tokens": 48000,
    "repository_tokens": 171000,
    "tool_definition_tokens": 21820,
    "tool_result_tokens": 39910,
    "reserved_output_tokens": 64000,
    "safety_headroom_tokens": 50000,
    "remaining_tokens": 312370,
    "pressure_ratio": 0.6416
  },
  "estimate_status": "MIXED_MEASURED_AND_ESTIMATED"
}
```

The example values are illustrative; production values come from the model capability and token accounting services.

## 9. Models and provider capabilities

```text
GET  /api/v1/model-capabilities
GET  /api/v1/model-capabilities/{snapshotId}
POST /api/v1/model-capabilities:refresh
POST /api/v1/model-capabilities/{modelId}:probe
GET  /api/v1/model-compatibility?taskId=...&modelId=...
```

Admin override requires elevated permission and creates a new versioned snapshot.

## 10. Progress subscription

```text
GET /api/v1/jobs/{jobId}/events        # SSE
GET /api/v1/ws/jobs/{jobId}            # WebSocket, if supported
```

On reconnect, clients send the last event id. If events are expired, they fetch the latest durable progress snapshot and continue.

## 11. Core event envelope

```json
{
  "event_id": "evt_01...",
  "event_type": "asset.ocr.completed",
  "schema_version": "1.0",
  "occurred_at": "2026-08-19T10:00:00Z",
  "tenant_id": "tenant_01...",
  "project_id": "project_01...",
  "aggregate_type": "asset",
  "aggregate_id": "asset_01...",
  "aggregate_version": 12,
  "trace_id": "trace_01...",
  "causation_id": "evt_00...",
  "correlation_id": "job_01...",
  "idempotency_key": "ocr:asset_01:v3",
  "data": {}
}
```

Consumers deduplicate by event id or domain idempotency key. PII and raw file content should not be put in event payloads.

## 12. Event catalog

### Upload and package

```text
input.session.created
asset.upload.initialized
asset.part.received
asset.upload.completed
asset.validation.failed
folder.manifest.submitted
folder.upload.negotiated
folder.upload.completed
package.manifest.created
package.manifest.verified
package.version.created
package.diff.completed
package.ready
package.partially_ready
package.failed
```

### Security and archives

```text
asset.scan.started
asset.scan.completed
asset.quarantined
archive.inspection.started
archive.password.required
archive.extraction.started
archive.extraction.completed
archive.path_traversal.blocked
archive.bomb.suspected
archive.limit.exceeded
archive.entry.quarantined
security.prompt_injection.detected
security.secret_suspected
```

### Parsing

```text
asset.parsing.started
asset.transcription.started
asset.transcription.completed
asset.ocr.started
asset.ocr.completed
asset.vision.completed
asset.normalization.completed
content.correction.created
content.source_anchor.created
content.source_anchor.invalidated
```

### Fusion and indexing

```text
package.fusion.started
requirement.extracted
requirement.conflict.detected
requirement.conflict.resolved
repository.profile.created
repository.index.started
repository.index.completed
repository.context_map.updated
memory.index.updated
```

### Context

```text
model.capability.discovered
model.capability.changed
context.budget.calculated
context.plan.created
context.source.loaded
context.source.deferred
context.pressure.elevated
context.pressure.high
context.pressure.critical
context.compaction.started
context.compaction.completed
context.rehydration.started
context.rehydration.completed
context.integrity.passed
context.integrity.failed
context.loss.detected
```

### Durable tasks and cost

```text
task.created
task.run.started
task.node.started
task.progress.updated
task.checkpoint.created
task.recovery.started
task.recovery.completed
task.paused
task.cancelled
task.completed
task.failed
usage.estimated
usage.recorded
cost.estimated
cost.reconciled
eta.prediction.updated
```

## 13. Webhooks

Webhook subscriptions must specify event types and project scope. Each delivery includes:

- timestamp and unique delivery id;
- HMAC or asymmetric signature;
- replay window;
- exponential backoff;
- delivery status and response hash;
- dead-letter/manual replay;
- no raw secrets or file body.

## 14. Versioning

- API breaking changes use a new major route or negotiated media type.
- Event schema has independent `schema_version`.
- JSON schemas are immutable after release; changes create a new version.
- Provider-specific fields live under extension objects.
- A deprecation includes date, replacement and telemetry of remaining users.
