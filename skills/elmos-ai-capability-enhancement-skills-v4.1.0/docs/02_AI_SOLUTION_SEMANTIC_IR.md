# AI Solution Semantic IR (AI-SIR)

## Purpose

AI-SIR is the framework-neutral semantic contract from which Elmos imports, generates, migrates, compares and upgrades AI systems. It is not a generic JSON dump and not an abstraction over class names. It captures observable behavior, state, side effects, authority, data grounding and operational semantics that must survive a target change.

## Top-level domains

| Domain | Canonical content | Typical target lowerings |
|---|---|---|
| Solution | business goal, actors, inputs/outputs, nonfunctional envelope | app metadata, APIs, UI contracts |
| Model | model roles, capabilities, routing, structured output, fallback, data policy | provider clients, model settings, gateways |
| Agent | roles, responsibilities, handoff, supervision, termination, permissions | agent objects, teams, supervisors |
| Workflow | state, nodes, branches, loops, parallel joins, interrupts, retries, compensation | Dify graph, LangGraph, ADK/MAF workflows |
| Tool/Protocol | typed inputs/outputs, MCP/A2A/OpenAPI, effects, authority, idempotency | tools, servers, clients, gateways |
| RAG | ingestion through citation/abstention/evaluation and lifecycle | vector/graph stores, retrievers, pipelines |
| Memory | scope, retention, write/read policy, deletion, conflict resolution | checkpointer/store/memory providers |
| Interaction | web/API/streaming/voice/messaging/AG-UI semantics | routes, events, channels, UI |
| Security/Governance | identity, tenancy, secret, data, sandbox, approval, audit | policy, middleware, infrastructure |
| Runtime/Operations | durability, workers, queue, telemetry, FinOps, deployment, rollback | Temporal/runtime, K8s, OTel |
| Assurance | obligations, oracles, metrics, tolerances, evidence, release thresholds | tests, evaluators, certifier |

## Node identity and provenance

Every semantic node includes:

```yaml
id: ai-sir://solution/contracts-assistant/workflow/retrieve
kind: WorkflowNode
schemaVersion: 1
source:
  artifacts:
    - uri: source://dify/app.yml#/workflow/nodes/4
      sha256: ...
  confidence: 0.98
  counterevidence: []
semantics:
  effect: read
  retrySafe: true
  authority:
    scopes: [knowledge:contracts]
lineage:
  compiler: elmos-ai-sir-compiler
  compilerDigest: sha256:...
  createdFromRevisionSet: ...
gaps: []
```

IDs are stable across target generation. Target files and runtime traces point back to these IDs.

## Workflow semantics

A workflow is more than edges:

```yaml
workflow:
  state:
    schema: ...
    mergePolicy: field-level-explicit
  nodes:
    - id: retrieve
      effect: read
      determinism: bounded
      retry:
        safe: true
        maxAttempts: 3
    - id: external_write
      effect: external-write
      idempotency:
        required: true
      approval:
        required: true
  transitions:
    - from: retrieve
      to: answer
      guard: evidence.count > 0
  loops:
    - entry: refine_query
      exit: sufficient_evidence
      bound: 4
  durability:
    checkpoint: after-each-effect
    resume: exact-state
  liveness:
    terminalReachable: required
```

Lowering to a framework that lacks a required semantic feature is possible only through an explicit external runtime/policy/emulation obligation.

## Tool and side-effect semantics

Tools are classified by effect, not merely by call syntax:

- `none`: pure/local computation.
- `read`: external read with no intended mutation.
- `write`: internal mutable state.
- `external-write`: email, payment, deployment, database mutation, issue/PR, device control or other externally visible action.

For write effects, AI-SIR records:

- idempotency key derivation;
- authority and approval;
- retry/replay behavior;
- compensation or reconciliation;
- expected output and postcondition;
- audit/evidence requirements.

## RAG semantics

The RAG IR represents:

```text
source → parse/OCR → normalize/deduplicate → classify/ACL
       → chunk/link → embed/sparse/graph indexes
       → query understanding/rewrite → filters
       → retrieve → fuse → rerank → context pack
       → answer → citation → abstention
       → feedback/evaluation
       → incremental update/delete/reindex/version
```

Key invariants:

- ACL is applied before evidence reaches model context.
- Deletion propagates to every index/cache and is testable.
- Each citation resolves to a source/version/span visible to the caller.
- Unsupported claims trigger abstention according to contract.
- Evaluation separates retrieval quality from answer/grounding quality.
- Index/provider changes invalidate affected evidence.

## Memory semantics

Memory is never a single chat-history list. AI-SIR distinguishes:

- turn and thread state;
- durable session state;
- user and organization memory;
- episodic and semantic memory;
- procedural skills;
- repository memory.

Each store has tenant namespace, retention, data class, write authority, conflict policy, deletion propagation and provenance. User memory is not copied into organization memory without a declared rule.

## Security semantics

Security requirements are part of the program meaning:

- caller and agent identity;
- tenant/project/environment boundaries;
- tool authority attached to exact request;
- data classification and provider eligibility;
- prompt/indirect injection policy;
- secret references and materialization;
- sandbox/egress;
- approval and break-glass;
- audit and retention.

A target implementation that returns the same text but bypasses approval or leaks cross-tenant evidence is semantically non-equivalent.

## Semantic gaps

A gap record is mandatory when a target cannot directly lower a construct:

```yaml
gapId: gap-approval-01
sourceNode: ai-sir://.../external_write
target: target://visual-platform-x
feature: request-scoped-approval
status: external-policy
preservationStrategy:
  kind: elmos-runtime-integration
proofObligations:
  - policy-negative-test
  - resume-after-approval
certificationImpact: bounded-until-executed
```

Critical `unsupported` or `blocked` gaps stop generation unless the Goal changes.

## Evolution and compatibility

AI-SIR follows additive versioning with explicit migration:

- readers reject unknown critical node kinds;
- adapters declare accepted AI-SIR versions;
- migrations preserve IDs and emit a semantic delta;
- re-import compares AI-SIR rather than source text;
- certification pins the exact schema and migration chain.

## Required compiler tests

1. Schema and referential integrity.
2. Stable ID generation.
3. Source map and provenance completeness.
4. Lossless import fixtures where the target format permits it.
5. Semantic-gap detection for deliberately unsupported fixtures.
6. Round-trip AI-SIR comparisons.
7. Open-world/opaque boundary handling.
8. Incremental invalidation.
9. Million-node sharding and content-addressed cache behavior.
10. Security and authority invariants.
