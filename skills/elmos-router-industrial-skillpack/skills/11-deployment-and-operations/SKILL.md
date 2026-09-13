# Skill 11 — Deployment & Operations

## Goal
Deploy the routing plane as an HA, independently scalable production subsystem.

## Services
Recommended logical components:
- Elmos Router API/library
- Model Registry/Policy service or module
- LiteLLM Proxy cluster
- provider adapter workers if isolation is desired
- telemetry collector
- PostgreSQL
- optional Redis

Keep initial deployment simpler if possible; preserve logical boundaries even if some modules share a process.

## HA
- >=2 instances for stateless router/gateway
- multi-AZ where platform supports it
- readiness based on local health, not every provider being up
- graceful drain for streaming requests
- bounded shutdown
- connection pool protection
- DB migrations backward-compatible

## Configuration rollout
- draft -> validate -> canary -> active
- immutable version ids
- instant rollback to prior active version
- reject invalid model capability/policy combinations before activation

## Secret rotation
- credentials referenced by secret id
- adapter resolves latest valid secret at call time or short TTL cache
- dual-key rotation where providers permit
- rotation does not require app redeploy

## SLO starting targets
Treat these as initial engineering targets to validate in staging, not universal guarantees:
- route decision p95 < 25 ms excluding external calls
- router availability >= 99.95%
- no single gateway dependency for native-capable strategic routes
- 100% inference attempts have trace id and cost attribution
- 0 plaintext provider secrets in logs/events

## Acceptance
- rolling deploy preserves active streams or drains them safely.
- gateway outage leaves eligible native lane functional.
- config rollback tested.
