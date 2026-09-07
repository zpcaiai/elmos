---
name: compatibility-runtime-and-protocol-adapter-builder
description: Design and validate temporary deterministic protocol adapters and compatibility runtimes for cross-language migrations. Use for HTTP, gRPC, SOAP, message, database, file, model, or auth bridges.
---

# Compatibility Runtime and Protocol Adapter Builder

## Boundary

Adapters translate protocol or schema; they must not introduce business logic. An agent may propose code but cannot publish, deploy, route traffic, or approve lossy behavior.

## Workflow

1. Select a bounded runtime: gateway translator, gRPC proxy, SOAP/REST bridge, message transformer, event up/downcaster, schema translator, SDK facade, compatibility view, file/model adapter, auth bridge, or sidecar.
2. Specify owner, expiry, route, input/output contracts, transformation, loss policy, error semantics, authentication context, observability, and rollback.
3. Require deterministic generation, statelessness or explicit state, idempotency, independent deploy/rollback, and no embedded business policy.
4. Require explicit approval for lossy mappings and reject unsupported transformations.
5. Compile and run contract, property, security, error/auth, performance, and rollback validation.
6. Require human approval for agent-generated candidates and attach immutable evidence.

## Output

Return `APPROVED` only when all gates pass; otherwise return exact blockers and no publish action.
