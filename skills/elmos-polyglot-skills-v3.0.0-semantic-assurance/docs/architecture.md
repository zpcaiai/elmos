# ELMOS Polyglot Architecture

## 1. Product boundary

This package defines an implementation contract for an enterprise software generation and transformation platform. It is not a collection of prompt-only syntax translators.

```text
Requirements / Repository / Runtime evidence
                  ↓
Authorization + Immutable Snapshot
                  ↓
Discovery + API/Data/Behavior contracts
                  ↓
Project IR + Semantic IR + Framework IR
                  ↓
Target Profile + Route + Migration DAG
                  ↓
Deterministic Codemods → Bounded Agent Patches
                  ↓
Trusted Runner + Compile/Test/Repair
                  ↓
Differential/Data/Performance/Security Validation
                  ↓
Evidence Graph → Readiness Gate → Delivery
```

## 2. Control plane

The control plane owns durable run state, policy, approvals, Skill and adapter registry, route profiles, evidence metadata, checkpoints, and delivery status. Interactive clients only observe or request transitions; a disconnected client must not terminate server-side work.

Recommended service boundaries:

- Run API and durable workflow engine
- Repository snapshot and artifact service
- Skill/adapter/rule registry
- Policy and approval service
- Planner and DAG service
- Runner scheduler and private-runner gateway
- Evidence and readiness service
- Delivery/PR service

## 3. IR strategy

Pairwise conversion among 14 technology entries would create 182 directed cross routes, or 196 cells including same-stack modernization. ELMOS avoids implementing each route as an isolated translator.

### Project IR

Models repositories, modules, services, endpoints, stores, queues, jobs, screens, tests, deployments, ownership, and provenance.

### Semantic IR

Models declarations, types, generics, control/data flow, effects, errors, async/cancellation, concurrency, ownership, lifetime, and unsupported constructs.

### Framework IR

Models routing, lifecycle, dependency injection, configuration, ORM, transactions, security, queues, scheduling, UI components/widgets, state, navigation, forms, accessibility, and platform services.

### Behavior contracts

Model observable inputs, outputs, errors, state changes, ordering, side effects, timing tolerances, serialization, timezone, numeric, Unicode, and nondeterminism.

Direct route profiles remain useful for prioritization, high-risk mappings, target architecture defaults, and route-specific validation, but they do not replace the shared IR.

## 4. Transformation strategy

1. Deterministic rules with fixtures and idempotency.
2. Compatibility layers and interoperability boundaries.
3. Bounded agent-generated patches for unresolved local gaps.
4. Human decisions for semantic loss, public breaking changes, security, data, or irreversible work.
5. Incremental cutover with rollback or compensation.

## 5. Trust and evidence

Every execution is bound to run ID, snapshot ID, toolchain, policy, target profile, route, and Skill version. Evidence is content-addressed. Changes to source, dependencies, tools, tests, rules, adapters, policy, or environment invalidate affected evidence.

`not-run` is the default state. Static Skills validation proves package integrity only; it does not prove a route implementation or production migration.
