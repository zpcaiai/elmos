# ExecPlan: Multimodal intake 50-Skill runtime closeout

## Metadata

- Owner: ELMOS multimodal intake maintainers
- Created: 2026-08-24
- Updated: 2026-08-24
- Primary Skill: `elmos-multimodal-input-orchestrator`
- Supporting Skills: `elmos-unified-multimodal-content-ir`, `elmos-source-anchor-and-provenance`, `elmos-durable-processing-and-recovery`, `b35-security-authorization-properties`, `b35-verification-certification-gate`
- Target repository/branch: `elmos` / `perf/analyzer-build-cache-and-batching`
- Package version: `elmos-multimodal-intake-skills@1.0.0`
- Risk level: P0 for identity, tenant isolation, authorization, archive safety, and downstream side effects
- Rollout flag: local engineering runtime only; external execution and certification remain disabled

## Goal and user-visible outcome

Deliver the pinned 50-Skill ZIP as an immutable, safely imported specification plus a runnable local intake engine, versioned API/SDK contracts, and a browser workbench. A caller can submit bounded text, files, folders, or archives; observe durable progress; recover or cancel work; review source-bound corrections; and hand a normalized, provenance-bearing package to downstream integrations without treating input content as authority.

## Existing repository findings

- Relevant modules/services: `engines/multimodal-intake-engine`, the `/intake` Next.js workbench and BFF routes, the pinned importer, and the Batch 35 authorization verification pack.
- Existing data model: SQLite migrations cover intake state, immutable assets, outbox/checkpoints, review corrections, archive lineage, deletion, context lifecycle, project packages, telemetry/cost, and downstream-agent grants.
- Existing APIs/events: versioned execute, progress, OpenAPI/AsyncAPI, webhook, Python/TypeScript/Java SDK, and local CLI/HTTP surfaces.
- Existing task/workflow behavior: durable idempotency, partial results, checkpoint/recovery, explicit `UNKNOWN` reconciliation, and append-only human review.
- Existing authz/tenant model: host-derived tenant/project/actor bindings and exact `INTAKE_READ`, `INTAKE_WRITE`, `INTAKE_REVIEW`, and `INTAKE_ADMIN` permissions.
- Existing storage/index/provider integrations: local content-addressed storage and lexical indexing are implemented; external antivirus, OCR, ASR, vision, strong sandbox, vector, downstream-agent provider, browser/device, and independent verifier evidence remain `NOT_RUN`.
- Reusable components: strict JSON/canonical digest helpers, SQLite stores, transactional outbox, operation registry, provenance schemas, progress stream, and importer transaction journal.
- Conflicts/gaps: shared worktree contains unrelated owner changes; the authorization pack still has placeholder artifact/environment bindings; final importer generation, full local tests, TypeScript check, conservative gate, and scoped Git closeout are pending.

## Scope

### In scope

- Verify the pinned ZIP without executing package scripts and publish the immutable source plus two 50-Skill installation roots.
- Close local runtime, migration, API/SDK, workbench, security, recovery, provenance, and operation-registry defects revealed by focused validation.
- Produce digest-bound local engineering evidence and run the conservative Batch 35 gate.
- Commit and push only the multimodal intake-owned files and exact shared-file hunks.

### Out of scope

- Production uploads, provider calls, deployment, release, signing, billing, customer data, external identity providers, and certification.
- Manufacturing holdout, representative-production, independent-review, browser/device, or provider evidence.
- Unrelated shared-worktree changes, including polyglot, cache, CAS, execution-intelligence, and other Skill packages.

## Non-negotiable invariants

- [ ] Original assets immutable
- [ ] Tenant/project/version/actor/resource isolation
- [ ] Source anchors for key conclusions
- [ ] No content-as-instruction privilege
- [ ] Ingestion executes no user code or package script
- [ ] Durable/idempotent recovery
- [ ] No duplicate side effects/cost
- [ ] No silent truncation/omission/version switch
- [ ] Machine wall-clock ETA
- [ ] Real local tests and digest-bound evidence before local completion
- [ ] Missing external evidence remains `NOT_RUN`; certification remains `NOT_CERTIFIED`

## Design

### Components and ownership

| Component | Responsibility | Data owner | Existing/new |
|---|---|---|---|
| Pinned importer | ZIP identity, safe extraction, contracts, dual-root install, drift checks | Repository integration | Existing, closeout pending |
| Intake engine | Immutable intake, parsing, IR, provenance, durable jobs, reviews, governance | Tenant/project SQLite + CAS | Existing, validation pending |
| API/SDK/operation registry | Exact 50-Skill and operation boundary | Runtime/API maintainers | Existing, drift validation pending |
| Workbench/BFF | Authenticated intake and progress UI without exposing host secrets | Web console | Existing, type/browser validation pending |
| Verification pack | P0 authorization and boundary evidence with fail-closed gate | Verification maintainers | In progress |

### Data changes

| Migration | Table/object | Compatibility | Backfill | Rollback |
|---|---|---|---|---|
| 001, 004-022 | Intake, knowledge, review, lineage, governance, context, package, cost, downstream tables | Additive/versioned SQLite migrations | None for local reference runtime | Restore pre-migration database snapshot or use a fresh local state root |

### API/event changes

| Contract | Version | Producer | Consumer | Idempotency |
|---|---|---|---|---|
| Execute envelope | `multimodal-intake-v1` | BFF/SDK/CLI | Engine dispatcher | Required key and canonical request digest |
| Progress events | versioned SSE/WS batch | Durable store | Workbench/SDK | Cursor and event digest bound |
| Human review | versioned source/correction/reservation documents | Review workflow | Workbench/downstream projections | Task version, fence, request digest, and operation key |
| Downstream context | receipt/grant/result-link documents | Engine PEP | Host adapter | Single-use grant and exact input/result digest |

### Security/trust changes

- New input/egress: bounded local HTTP/BFF input; no archive-provided executable path or network authority.
- Secrets: only host-owned environment allowlists and opaque secret/credential handles; never request fields or persisted raw tokens.
- Sandbox: complex parsing and archive publication require exact byte-bound CLEAN receipts; absent strong sandbox remains `NOT_RUN`/blocked.
- Tool permissions: exact operation registry plus host-derived principal/resource/action context; unknown pairs fail closed.
- Abuse limits: byte, JSON depth, archive entry/ratio/depth, upload part, cursor, event, timeout, and retry limits.
- Audit: immutable receipts/events/outbox records with content-minimized telemetry.

### Context/cost/ETA changes

- Model capability dependency: persisted, versioned host-verified snapshot; unknown or stale capacity blocks model use.
- Token budget: current-window reservations are distinct from cumulative usage.
- Cost attribution: exact-decimal estimates and actuals remain separate; actuals require host evidence.
- ETA features: bounded local P50/P95 machine wall-clock estimate; absent calibration remains unknown.
- Failure/reconciliation: lost responses become `UNKNOWN` and require exact reconciliation rather than automatic retry.

## Implementation milestones

### Milestone 1 — immutable package and runtime closure

- [ ] Safe ZIP validation and immutable extraction
- [ ] Dual-root 50-Skill installation and generated manifests
- [ ] Runtime/migration/API/SDK drift closure
- [ ] Importer and engine unit/integration tests

### Milestone 2 — authenticated workbench and evidence

- [ ] Workbench/BFF strict boundary and recovery validation
- [ ] TypeScript and focused browser verification where locally available
- [ ] P0 authorization pack artifact/environment bindings
- [ ] Batch 35 validation and conservative gate output

### Milestone 3 — scoped delivery

- [ ] Task-only diff and whitespace validation
- [ ] Exact shared-file hunk staging
- [ ] Commit(s), push, and local/tracking/remote SHA verification

## Test plan

| Test | Fixture | Command | Expected | Evidence path |
|---|---|---|---|---|
| Importer | pinned ZIP and generated roots | `python3 tooling/integrate_multimodal_intake_skills.py --check` | exact identity and drift checks pass | local command output + verification pack manifest |
| Importer tests | adversarial ZIP/AST/transaction fixtures | `python3 -m pytest -q -p no:cacheprovider tests/multimodal-intake/test_integration.py` | all pass | local test evidence |
| Engine | local SQLite/CAS fixtures | `PYTHONPATH=engines/multimodal-intake-engine/src python3 -m pytest -q -p no:cacheprovider engines/multimodal-intake-engine/tests` | all pass | local test evidence |
| Web contracts | TypeScript project | `pnpm --dir apps/web-console exec tsc --noEmit` | exit 0 | local test evidence |
| Workbench journey | focused Playwright fixture | focused multimodal intake Playwright command | pass or remain explicitly `NOT_RUN` if host prerequisites are absent | local browser evidence when run |
| Verification | exact local pack | Batch 35 validator and gate | schema passes; strongest result stays experimental/blocked and `NOT_CERTIFIED` | `verification-packs/multimodal-intake-authorization-v1/certification/` |
| Repository gate | all local components | `make multimodal-intake-skills` | exit 0, including expected conservative non-certification decision | local command output |

## Rollout

- Feature flags: local workbench/runtime composition only.
- Tenant cohort: disposable local test tenants.
- Migration order: ascending migration number before request handling.
- Backfill: none.
- Capacity: bounded local fixtures and explicit archive/context budgets.
- Alerts: stable error codes, trace IDs, durable progress and reconciliation state.
- Kill switch: remove/disable local BFF host configuration and stop the local engine.
- Rollback: revert scoped commits; retain immutable source assets and state snapshots for audit.

## Progress log

### 2026-08-24

- Completed: read the orchestrator, Content IR, provenance, durable recovery, Batch 35 authorization, and conservative gate contracts; froze overlapping writers; inventoried the existing runtime and validation surfaces.
- Evidence: prior importer suite `77 passed in 60.90s`; this run has not yet adopted that as final evidence.
- Decision: keep all provider, independent, holdout, representative, production, and certification states fail closed.
- Blocker: another owner currently runs unrelated polyglot tests; heavy multimodal qualification waits for resource release.
- Next: finish gap audit, implement fixes, bind exact local artifacts, then run focused and repository gates.

## Final completion check

- [ ] All locally implementable relevant Skill acceptance criteria pass
- [ ] No skipped relevant local tests
- [ ] Migrations and rollback behavior tested proportionally to local scope
- [ ] API/schema/docs updated
- [ ] Source/integrity report attached
- [ ] Security evidence attached
- [ ] Bounded timing evidence attached
- [ ] Machine wall-clock and local cost effect reported
- [ ] Remaining external limitations disclosed
