# Batch 20 verification

## Repository-complete scope

- Independent Java 21 `ELMOS_ENTERPRISE_INTEGRATION` Worker with capabilities, scan, plan, leased execute-step, validate, tenant-scoped job query, and cancellation contracts.
- Eighteen Runtime Skills for Engine contracts, estate discovery, Canonical Integration IR, target planning, ESB/SOA, IBM MQ, Kafka, RabbitMQ, API Gateway, event governance, schema registry, B2B, workflow, security, observability/replay, equivalence, parallel cutover, and unified evidence.
- Twelve fail-closed Adapter declarations, seven Draft 2020-12 schemas, nine fixtures including the requested matrix and 30 acceptance scenarios, OpenAPI 3.1, two policy manifests, and seven isolated Runner policies.
- Shared Engine API, routing, portfolio dependency types, control-plane read/evaluate API, and independent Cutover and Decommission decisions. Cutover does not prematurely require post-cutover zero-usage or credential/certificate revocation evidence; Decommission does.
- Flyway V21 creates 70 new strong-RLS projections and extends four existing authorities to cover all 74 requested integration objects. V21 is physical migration 21 because the pre-existing commercial-loop migration owns V20.

## Evidence boundary

Repository evidence proves deterministic acceptance policy, contract/fixture integrity, tenant and idempotency boundaries, default read-only discovery, lease/resource-scope enforcement, denial of destructive broker and gateway operations, replay and partner authorization checks, and separation between Workers and Cutover authority. It does not prove a customer integration estate was scanned, transformed, replayed, cut over, or retired.

The following remain `NOT_CONFIGURED`, `NOT_RUN`, `INCONCLUSIVE`, or `BLOCKED`:

- Customer ESB, IBM MQ, Kafka, RabbitMQ, Schema Registry, API Gateway, AS2/EDI, MFT/SFTP, BPM/Workflow, scheduler, trace, log, and network-flow adapters;
- Customer configuration exports, queue/topic/exchange data, producer/consumer ownership, partner agreements, certificates, payloads, mappings, runtime traces, lag, DLQ, offsets, acknowledgements, workflow instances, owners, and approvals;
- Ephemeral product test environments, licensed product binaries, partner endpoints, real replay, message ordering, effectively-once side effects, semantic comparison, shadow/mirror/dual publish, production cutover, credential revocation, stability hold, and decommission evidence.

No registry compatibility pass proves business-semantic compatibility. No broker transaction proves external payment exactly once. No HTTP response or AS2 MDN proves business acceptance. No zero daily traffic proves retirement while seasonal flows, unknown consumers, partners, backlog, workflow instances, credentials, or certificates remain.

## Verification commands

```bash
python3 /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py agent-skills/runtime/<batch-20-skill>
JAVA_HOME=/opt/homebrew/opt/openjdk@21 /opt/homebrew/bin/mvn -B clean verify
PATH=/opt/homebrew/bin:$PATH dotnet test engines/dotnet-engine/Elmos.Dotnet.slnx
/opt/homebrew/bin/uv --directory engines/python-engine run --locked pytest
/opt/homebrew/bin/uv --directory engines/python-engine run --locked ruff check src tests
/opt/homebrew/bin/uv --directory engines/python-engine run --locked mypy src
PATH=/Users/stephen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin /opt/homebrew/bin/pnpm --dir engines/frontend-client-engine check
PATH=/Users/stephen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin /opt/homebrew/bin/pnpm --dir apps/web-console check
/Applications/Docker.app/Contents/Resources/bin/docker compose -f deploy/compose/docker-compose.yml config --quiet
```

Direct PostgreSQL 17 validation runs V1–V21 against a fresh database and verifies the 70 V21-created tables, four extended authorities, forced RLS policies, identity indexes, append-only triggers, and effective cross-tenant isolation. HTTP validation starts the packaged Worker on an isolated port and confirms `NOT_RUN` behavior without approved adapters, leases, scopes, replay/partner authorization, or independent production approval.

## Verification status

Repository implementation and the closing verification run completed on 2026-07-21:

- Maven clean verification: 52 reactor projects, 111 Surefire reports, 709 tests, 0 failures, 0 errors, and 1 expected skip for the Docker-conditioned Flyway test. The Enterprise Integration engine contributes 42 passing tests, including all 30 acceptance scenarios.
- Cross-engine regression: .NET 12/12 tests; Python 31/31 tests plus clean Ruff and MyPy checks; Frontend Client engine 34/34 tests.
- PostgreSQL 17 fresh-database migration: V1–V21 completed. All 70 new tables exist with forced RLS and a tenant policy; all four authority extensions, five unique identity indexes, and 15 append-only triggers exist. A tenant-A session saw only tenant-A data and a tenant-A write for tenant B was rejected by RLS.
- Packaged Worker HTTP: capabilities report 12 adapters as `NOT_CONFIGURED`, control-plane execution `false`, and production mutation `DENY`. Discovery returned `INTEGRATION_RUNNER_REQUIRED` with `NOT_RUN`, zero evidence, and no customer-code execution. Missing lease, replay authorization, partner authorization, production approval, and destructive offset reset returned their dedicated fail-closed errors without production mutation or accepted message loss.
- Skills and static artifacts: all 18 Batch 20 Skills passed `quick_validate.py`; the repository contains 218 Runtime and 35 Build Skills with valid `SKILL.md` files. The 25 Batch 20 JSON artifacts and YAML contracts parse successfully.
- Delivery surface: the Next.js 16.2.10 production build and Docker Compose configuration validation passed. The executable JAR packaging and local HTTP run passed. Container image construction was not executed because the configured Docker/OrbStack daemon was unavailable; this is not represented as container-runtime evidence.

Real customer middleware execution remains external and is not represented as completed.
