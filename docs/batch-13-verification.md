# Batch 13 verification: cross-language composite modernization

Verified on macOS on 2026-07-21. This document distinguishes repository implementation from production-system evidence.

## Repository completion

Batch 13 is implemented as a system control layer above the existing Java, .NET, and Python engines:

- `modules/composite-modernization` contains immutable landscape/version contracts, dependency/SCC/shared-database analysis, contract consumer matrices, runtime topology correlation, Wave 0–6 planning, compatibility windows/adapters, data ownership/CDC/backfill/reconciliation, shadow comparison, progressive traffic decisions, business journeys, cutover/rollback/stability/decommission, and composite evidence mapping.
- `apps/control-plane` exposes only capabilities and evaluate endpoints. There is no fourth `/engine/v1`, source edit, provider mutation, production-write switch, database deletion, or automatic decommission operation.
- ArchUnit keeps the composite domain framework-, JDBC-, Docker-, OpenRewrite-, Worker-, Recipe-, Repair-, and Agent-Gateway-free.
- Seven Draft 2020-12 JSON Schemas, seven valid fixtures, an OpenAPI 3.1 control contract, a 76-object V13 persistence projection, and 18 executable acceptance scenarios are present.
- X001–X014 are valid Runtime Skills. X001 has three adversarial prompt evaluations explicitly marked `PROMPTS_ONLY_NO_SUBAGENT_AVAILABLE`; they are not reported as executed agent evaluations.

## Verification results

| Gate | Result |
|---|---|
| Maven `clean verify` | 40 reactor projects; 213 tests, 0 failures, 0 errors, 1 Docker-dependent skip |
| Composite domain | 23 tests: all 18 required scenarios plus 5 governance/topology/evidence tests passed |
| Composite control API | 3 tests passed |
| Python engine | 31 pytest tests passed; Ruff passed; strict mypy passed across 19 source files |
| .NET engine | 11 tests passed on .NET 10; `dotnet format --verify-no-changes` passed |
| Web console | TypeScript check and Next.js 16.2.10 production build passed; `/` statically generated |
| JSON Schema | 7 Draft 2020-12 metaschemas and their 7 fixtures passed `jsonschema` 4.25.1 validation |
| Composite OpenAPI | OpenAPI 3.1 document passed `openapi-spec-validator` |
| Skill inventory | 35 Build Skills and 101 Runtime Skills; all X001–X014 passed `quick_validate.py` |

The one Maven skip is the existing Testcontainers Flyway test because Docker was unavailable. It was replaced with a direct PostgreSQL 17 execution, not counted as a pass-through skip.

## PostgreSQL V1–V13 result

All thirteen SQL migrations were applied in order to a temporary PostgreSQL 17 database:

- 597 public tables;
- 596 forced tenant-isolation policies;
- 597 `organization_id` columns;
- 31 append-only trigger objects (18 introduced by V13; `information_schema.triggers` exposes 62 UPDATE/DELETE event rows);
- both reused authority tables, `message_contracts` from V7 and `model_endpoints` from V9, received `landscape_version_ref` without duplicate-table creation;
- a non-owner role with `app.organization_id=org-b13-a` saw one A row and no B row; the B context likewise saw one B row;
- mutation of `shadow_differential_results` was rejected by the append-only trigger.

V13 represents all 76 specified object types by creating 74 tables and extending two existing tenant authorities. The temporary database and schema-validator directories were stopped and moved to macOS Trash for recoverable cleanup.

## Required fail-closed external gates

The following are deliberately not claimed complete:

| Capability | Status | Evidence still required |
|---|---|---|
| Customer system landscape | `NOT_RUN` | Authorized repositories, deploy manifests, production inventory, external-system declarations |
| Runtime topology | `NOT_CONFIGURED` | OpenTelemetry, gateway/mesh, broker, database audit and log evidence with environment coverage |
| Native contract registries/checkers | `NOT_CONFIGURED` | Customer OpenAPI/AsyncAPI/Proto/WSDL/Schema registries and consumer/version observations |
| Compatibility runtime | `NOT_RUN` | Built, security-reviewed, performance-tested, independently deployable/rollbackable adapters |
| CDC and production data | `NOT_CONFIGURED` | Connector offsets, lag/retry evidence, backfill checkpoints, hashes, reconciliation and frontier |
| Shadow traffic | `NOT_RUN` | Authorized privacy-safe capture, suppressed side effects, primary/shadow responses and business comparisons |
| Canary and traffic shift | `NOT_CONFIGURED` | Gateway/mesh/load-balancer/flag provider, technical and business SLO observations, rollback drill |
| Production write ownership | `BLOCKED` | Human approval, idempotency, data authority, rollback and business-owner evidence |
| System cutover/rollback | `NOT_RUN` | Frozen production manifest, executed steps, data-aware rollback or forward-fix drill |
| Legacy decommission | `BLOCKED` | Zero traffic/consumers/writes/batch access, credential revocation, archive/legal/audit/CMDB/owner evidence |

No repository test, schema validation, fixture, shadow plan, or evaluator response is evidence that a customer production cutover or decommission occurred.

## Standards checked

The design was checked against the current official [OpenAPI 3.2.0 specification](https://spec.openapis.org/oas/v3.2.0.html), [AsyncAPI 3.0.0 specification](https://www.asyncapi.com/docs/reference/specification/v3.0.0), [Protocol Buffers proto3 guide](https://protobuf.dev/programming-guides/proto3/), [Buf breaking-change guidance](https://buf.build/docs/breaking/), [OpenTelemetry baggage API](https://opentelemetry.io/docs/specs/otel/baggage/api/), [Debezium documentation](https://debezium.io/documentation/reference/stable/index.html), [Istio traffic mirroring](https://istio.io/latest/docs/tasks/traffic-management/mirroring/), and [Kubernetes Gateway API](https://gateway-api.sigs.k8s.io/).
