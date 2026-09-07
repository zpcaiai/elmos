# ELMOS Project Synthesis Engine — Batch 53–56

This package contains 48 implementation-grade Skills:

- Batch 53 — Java Project Pack: PG077–PG088
- Batch 54 — Python Project Pack: PG089–PG100
- Batch 55 — C# / .NET Project Pack: PG101–PG112
- Batch 56 — Database, API and External Integration: PG113–PG124

## Certified Golden Paths

- Java: Spring Boot REST API, modular monolith, worker/batch, evidence-backed microservices.
- Python: FastAPI service, Django web application, CLI/worker, data/AI/RAG/agent backend.
- .NET: ASP.NET Core API, modular monolith, worker/console, MVC/Blazor.
- Shared: PostgreSQL/MySQL/SQL Server relational design, migrations, OpenAPI, gRPC, event brokers, cache/search, object storage, external clients, resilience, idempotency/outbox/saga, service virtualization and contract registry.

## End-to-End Generation Contract

```text
Approved Blueprint
→ language profile
→ domain/application sources
→ API/persistence/security/messaging adapters
→ build and dependency metadata
→ tests
→ container/deployment assets
→ generation manifest and SBOM
```

## Non-negotiable Rules

1. Language generators consume approved Blueprint and contracts only.
2. Domain code remains independent of web and persistence frameworks.
3. Public API, database and event changes are compatibility-checked.
4. Database certification uses target-compatible database engines.
5. At-least-once delivery cannot duplicate protected side effects.
6. Authorization is deny by default and tenant-aware.
7. Production secrets are never generated.
8. Runtime containers execute as non-root.
9. Identical inputs produce no semantic diff.
10. User-owned source is never overwritten.
