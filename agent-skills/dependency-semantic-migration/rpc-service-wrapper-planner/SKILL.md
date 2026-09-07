---
name: rpc-service-wrapper-planner
description: Design versioned RPC or service wrappers for retained capabilities across process or network boundaries. Use when isolation or independent scaling is required.
---
# RPC Service Wrapper Planner
Read `../references/dependency-migration-v1.md`. Define protocol/schema, compatibility policy, client/server ownership, authentication/authorization, deadlines, cancellation, retries/idempotency, streaming/backpressure, error model, health/readiness, observability, deployment and shutdown. Separate local process RPC from remote service trust. Never inherit in-process assumptions, retry non-idempotent calls implicitly, omit failure semantics, expose secrets, or call a stubbed endpoint production-ready.
