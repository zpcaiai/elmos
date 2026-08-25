# Implementation Roadmap

This roadmap is ordered to reduce security and data-model rework. Each phase should be a runnable vertical slice, not a documentation-only milestone.

## Phase 0 — Repository discovery and decisions

**Primary skills:** package-level contract.

### Work

- Map current Elmos architecture, task engine, upload API, database, object storage, auth, model router, RAG, cost ledger and UI.
- Identify reusable modules and conflicting schemas.
- Choose workflow durability, outbox, object quarantine, parser sandbox and index boundaries.
- Create ADRs from `templates/ADR.md`.
- Establish CI, migration, fixture and evidence directories.
- Add package validation to CI.

### Exit criteria

- Existing-state report and target-state diff approved.
- ExecPlan contains dependencies, migration, rollback, test and rollout.
- No duplicate platform is introduced without an ADR.
- Security trust zones and data owners are named.

## Phase 1 — Secure immutable intake

**Skills:** 01, 02, 03, 04, 12, 13, 21, 26, 27.

### Work

- InputSession/Asset/Upload/Package domain and migrations.
- Multipart upload, checksum, idempotency, quota reservation and resumability.
- Quarantine object prefix and MIME/magic/structure validation.
- Scanner and sandbox interfaces.
- Initial ContentBlock and SourceAnchor schema.
- Durable workflow/outbox and progress API.
- Retention/deletion skeleton.

### Exit criteria

- Upload survives disconnect and duplicate part delivery.
- Original assets are immutable and tenant isolated.
- Invalid/unsafe files never reach parser workers.
- Task state survives worker/process restart.
- A simple TXT/Markdown asset reaches READY with line anchors.

## Phase 2 — Document and audio/image parsing

**Skills:** 05–11, 17, 19, 22, 23.

### Work

- Provider abstractions and routing.
- Audio ASR/diarization/time anchors and correction UI.
- Image preprocessing/OCR/vision/UI/diagram models.
- PDF page classifier and layout/table/OCR.
- DOCX OOXML and isolated DOC conversion.
- Markdown/TXT/log parsers.
- ETA, provider usage, stage telemetry.

### Exit criteria

- Golden fixtures produce stable Content IR and anchors.
- Low confidence is visible and correctable.
- Provider failure/fallback is deterministic and policy-compliant.
- Passwords and secrets are absent from logs/traces.
- Machine ETA reconciles with actual runtime.

## Phase 3 — Fusion, requirements and project memory

**Skills:** 14–16, 18, 20, 24, 28, 37.

### Work

- Multi-asset role/version/duplicate association.
- Requirement/entity/relation extraction.
- Conflict detection/review/decision workflow.
- Prompt Injection classifier and tool authorization boundary.
- Full-text/vector/metadata/graph indexing.
- Project memory write/read/delete lifecycle.
- Downstream TaskContextBundle contract.
- Quality and provenance eval harness.

### Exit criteria

- Multi-file fixture detects seeded conflicts.
- Every key requirement has valid sources.
- Document instructions cannot invoke tools or modify system policy.
- Project/tenant/version filters are enforced in retrieval.
- Deleting an asset propagates to allowed derivatives and indexes.

## Phase 4 — Dynamic long context

**Skills:** 29–40.

### Work

- Model capability registry and provider synchronization.
- Context Budget Manager and multimodal token accounting.
- Candidate ranking, packing, P0/P1 pinning and explainability.
- Pressure state machine and growth prediction.
- Structured compaction and raw history externalization.
- Task/context checkpoints and side-effect ledger integration.
- Exact rehydration and project-memory/repository-map retrieval.
- CriticalFactSet and integrity gates.

### Exit criteria

- Current Codex parity fixture passes without business hardcoding.
- Model switch triggers budget recalculation and compatibility check.
- No overflow or silent truncation under stress.
- ≥2M-token scenario performs ≥3 compactions and ≥5 rehydrations.
- Critical fact/source retention is 100%.
- Recovery does not duplicate provider or external costs.

## Phase 5 — Folder and archive package intake

**Skills:** 41–47, 50.

### Work

- Folder scan/manifest and multi-file resumable upload.
- Deterministic package manifest/digest and analysis views.
- ZIP/TAR/TAR.GZ/TGZ/GZIP pre-scan and sandbox extraction.
- Zip Slip, bombs, links, special files and nested budgets.
- Ephemeral encrypted-password handling.
- Project root/language/framework detection.
- ignore/generated/vendored/binary/secret classification.
- Project package preview and review UI.

### Exit criteria

- Paths and same-name files are preserved; local absolute paths never leave client.
- 100k-file folder resumes after network failure.
- Archive attack corpus causes no sandbox escape/resource exhaustion.
- Input stage executes no project code.
- Package review clearly distinguishes included/indexed/loaded/quarantined/failed.
- Normal and encrypted archives behave per policy.

## Phase 6 — Repository map and incremental versions

**Skills:** 38, 46–49.

### Work

- Multi-language parser/LSP/static-index adapters.
- Modules, symbols, APIs, data, messages, configs and tests.
- Typed dependency/call/test graph and L0–L5 context map.
- Package diff, rename candidates and impact analysis.
- Content-addressed parsed artifact reuse.
- Version pinning/rebase/rollback.

### Exit criteria

- Repository nodes trace to exact version/path/range.
- Indexing executes no user scripts.
- Incremental rebuild matches full rebuild for same version.
- Running task cannot silently change project version.
- Large repository performance meets declared reference SLO.

## Phase 7 — Product completion and operations

**Skills:** 22–28, 33, 40, 50 plus all cross-cutting skills.

### Work

- Unified workbench, context dashboard, review queues and access controls.
- Cost/revenue reconciliation and tenant pricing integration.
- Operational dashboards, alerts, SLOs, runbooks and capacity plans.
- Retention/export/deletion/hold workflows.
- SDKs, webhook, API compatibility and documentation.
- Chaos, backup/restore, disaster recovery and security red team.
- Gradual rollout, kill switches and provider fallback.

### Exit criteria

- Full acceptance matrix passes on production-like infrastructure.
- Security threat model controls have evidence.
- Cost and usage reconcile with provider receipts.
- RPO/RTO and failover are tested.
- Accessibility and large-data UI tests pass.
- Rollout/rollback and incident runbooks are exercised.

## Delivery waves

A practical commercial rollout can use:

| Wave | User value | Included phases |
|---|---|---|
| Alpha | Secure text/PDF/Word/image/audio intake with evidence | 0–2 |
| Beta | Cross-file requirements, conflicts and task handoff | 3 |
| Long-task Beta | Codex-parity context and durable continuation | 4 |
| Project Package Beta | Folder/ZIP/TAR.GZ and project preview | 5 |
| Repository Intelligence | Symbol map and incremental project versions | 6 |
| Production | Governance, billing, SLO, red-team and DR | 7 |

## Parallelization

Safe parallel streams after Phase 0:

- Parser adapters can run in parallel behind finalized Content IR.
- UI can implement mock-contract components, but production completion waits for real APIs.
- Context capability/usage can run alongside parser work after base task model exists.
- Archive security and folder upload can run in parallel after PackageManifest is fixed.
- Repository language adapters can run in parallel after Symbol/Edge schema is stable.

Do not parallelize migrations to the same tables without a single owner.

## Milestone reporting

Do not report person-days as Elmos runtime. For implementation planning, ordinary engineering estimates may be tracked separately, but runtime acceptance must report:

```text
reference hardware
fixture size and complexity
queue state
machine wall-clock elapsed
P50/P95/P99
peak resources
provider cost
compute/storage cost
```
