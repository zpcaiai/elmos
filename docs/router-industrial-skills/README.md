# Elmos Router Industrial Skills

- **Package**: `elmos-router-industrial-skillpack`
- **Version**: `1.0.0`
- **Archive SHA-256**: `90ebe2dcf3f4c9e21d80c508c268429d3944e7780a3054a7416bff59197d9319`
- **Installed Skills**: 14
- **Runtime Engine**: `engines/router-industrial-engine`

## Architecture & Subsystems

1. **Domain Contracts & Error Taxonomy (`01`)**: Provider-neutral `RouteRequest`, `ModelExecutionPlan`, `RouteDecision`, and 17-class error taxonomy.
2. **Registry Subsystem (`02`)**: Thread-safe dynamic `Model`, `Provider`, and `Deployment` registry with real-time health snapshots.
3. **Policy & Security Guardrails (`03`)**: 15 hard eligibility filters, data residency fences, capability leases, and credential redaction.
4. **Routing Engine (`04`)**: 4-phase deterministic decision pipeline (Hard filter -> Scoring -> Diversity tie-break -> Fallback plan) with shadow routing.
5. **Execution Lane Adapters (`05`, `06`, `07`)**: LiteLLM proxy gateway, native high-throughput direct adapters (OpenAI, Anthropic, Self-Hosted vLLM), and OpenRouter long-tail router.
6. **Resilience & Replay (`08`)**: Scoped circuit breakers, jittered exponential backoff, stream epoch coordinator, exactly-once CAS idempotency commit, and deterministic replay.
7. **Cost, Rate-Limiting & Accounting (`09`)**: Hierarchical budgets, token buckets, concurrency semaphores, and append-only cost ledger with reconciliation.
8. **Observability & Benchmarks (`10`)**: Latency percentiles, span tracing with prompt hashing, and task benchmark quality scoring.
9. **Operations & Deployment (`11`)**: Readiness probes, graceful drain, and zero-downtime configuration updates.
10. **Certification & Phased Rollout (`12`)**: Phased traffic ramp (1% -> 5% -> 25% -> 100%), anti-regression gates, and E0-E5 readiness.

## Verification

Run:
```bash
make router-industrial-skills
```
