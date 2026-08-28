# AI-Native Project Factory Reference Architecture

## 1. Position inside Elmos v3

This package is a **non-routable extension of the existing `project-generation` Domain Pack**. It does not add a ninth kernel and does not increase the 16 routable v3 entry points.

```text
K1 Goal / Specification
        │ requirements, target intent, acceptance
        ▼
K2 Repository Intelligence ────── source DSLs, repositories, runtime evidence
        │
        ▼
K3 Repository Semantic Compiler ─ AI Solution Semantic IR (AI-SIR)
        │
        ▼
K4 Agentic Reasoning ──────────── archetype, target portfolio, proof/repair plans
        │
        ▼
K5 Transformation ─────────────── target-native repositories and extensions
        │
        ▼
K6 Proof & Verification ───────── native, differential, security, performance evidence
        │
        ▼
K8 Certification ──────────────── exact bounded completion certificate
        ▲
        │ durable execution, authority, cost/ETA, checkpoints, reconciliation
K7 Harness Runtime
```

The package preserves four separated authorities:

1. **Intent authority:** K1 owns Goal, RevisionSet, RequirementGraph and acceptance.
2. **Semantic authority:** K2 evidence and K3 semantic profiles/AI-SIR determine meaning.
3. **Execution authority:** K7 Environment/workspace/attachment/tool request determines what may execute.
4. **Completion authority:** K6 evidence and independent K8 certification determine whether the claim is earned.

No target framework, adapter, LLM, worker, chat thread, operator UI or generated repository owns all four.

## 2. Product planes

| Plane | Responsibilities |
|---|---|
| Product/API | Solution creation, import, target portfolio, run control, evidence/certificate views |
| Control plane | Goal compiler, target planner, adapter registry, policy, scheduler, approval, certifier |
| Semantic plane | Source importers, AI-SIR compiler, target profiles, semantic-gap analysis |
| Execution plane | Isolated workspaces, target emitters, native conformance workers, verifier workers |
| Data plane | PostgreSQL 17 + RLS, content-addressed artifact/evidence store, event bus, cache |
| Enterprise edge | Customer VPC runner, private model/vector endpoints, Git/artifact mirrors, SSO |
| Experience plane | Operator console, developer CLI, SDK, generated project portal |

## 3. Canonical objects

```text
Tenant
 └─ Project
    └─ Goal
       ├─ GoalContract
       ├─ RequirementGraph
       ├─ ObservableContract
       ├─ AcceptanceScenarios
       ├─ AssumptionLedger
       ├─ RevisionSet
       │  ├─ SourceSnapshot / Source DSL Export
       │  ├─ AI-SIR
       │  ├─ TargetPortfolio
       │  ├─ TargetCapabilityProfiles
       │  ├─ Adapter and Toolchain Locks
       │  ├─ Policy Bundle
       │  └─ Assurance Contract
       ├─ ProofObligationGraph
       └─ Run
          ├─ ExecutionEpoch
          ├─ EnvironmentAuthority
          ├─ WorkGraph / Step / Attempt
          ├─ Checkpoint / SideEffectLedger
          ├─ GeneratedProject / ChangeGraph
          ├─ NormalizedAgentTrace
          ├─ ProofResult / EvidenceArtifact
          └─ GateEvaluation / CompletionCertificate
```

Each object has exactly one writer/owner. Other components reference immutable versions or issue typed commands.

## 4. End-to-end compiler pipeline

```text
Business requirement, PRD, source repository, visual DSL or existing agent project
                                      │
                                      ▼
                  Requirement and Source Evidence Compilation
                                      │
                                      ▼
                         AI Solution Semantic IR
                                      │
                         Capability Negotiation
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                    ▼
            Prototype target     Production target    Channel/Harness target
            Dify/Langflow        LangGraph/Spring     OpenClaw/Pi/Harness
                 │                    │                    │
                 └────────────────────┼────────────────────┘
                                      ▼
              Native import/build/start/load + normalized trace recording
                                      ▼
              Differential, RAG, graph, security and nonfunctional verification
                                      ▼
                    Bounded repair or independent E0–E5 certification
```

## 5. Generation modes

Every adapter declares which modes it supports:

- **Application-on-X:** complete application using target framework/platform.
- **Extension-for-X:** plugin, tool, skill, prompt, package, provider or channel extension.
- **Distribution-of-X:** deployable customized platform/harness distribution.
- **Migration-to/from-X:** import, semantic recovery, cross-target generation and differential validation.
- **Upgrade-of-X:** version drift analysis, preservation-aware regeneration and recertification.

A target that cannot support a mode must declare `unsupported`; the planner cannot infer support from ecosystem similarity.

## 6. Shared-versus-target repository model

Generated portfolios use one canonical solution tree:

```text
generated-ai-solution/
├── solution/
│   ├── agentic-solution.json
│   ├── contracts/
│   ├── policies/
│   └── target-portfolio.json
├── shared/
│   ├── schemas/
│   ├── prompts/
│   ├── tools/
│   ├── protocols/
│   ├── datasets/
│   └── evals/
├── targets/
│   ├── dify/
│   ├── langgraph/
│   ├── spring-ai/
│   └── openclaw/
├── deploy/
├── tests/
└── evidence/
```

Shared assets are generated once and referenced by target-specific lowerings. A target adapter may fork an asset only with a recorded semantic reason and cross-target obligation.

## 7. Authority and lifecycle

Every execution attempt carries:

```yaml
environmentAuthority:
  tenantId: ...
  projectId: ...
  goalId: ...
  revisionSetId: ...
  executionEpoch: ...
  leaseGeneration: ...
  fencingToken: ...
  allowedTools: []
  allowedPaths: []
  allowedEgress: []
  secretReferences: []
  approvals: []
  expiresAt: ...
```

Thread and Turn are conversational containers, not authority owners. A resumed session retains the authority attached to the Environment/Attachment; it does not inherit a broader thread-wide sandbox.

Long tasks require event-sourced or equivalently durable state, checkpoints, replay, pause/resume/cancel, idempotency, fencing and side-effect reconciliation. An unknown external side effect blocks terminal completion.

## 8. Adapter boundary

Adapters are replaceable and cannot own AI-SIR or certification. The SPI is:

```text
detect → profile → import → lower → emit → native_validate → upgrade → evidence
```

Each adapter declares:

- exact upstream version policy and artifact digest;
- supported/conditional/emulated/external/unsupported features;
- semantic lowering rules and gaps;
- native conformance commands;
- authority and network requirements;
- upgrade/drift rules;
- evidence classes and invalidation triggers.

## 9. Completion model

Generation success is not one boolean. The system reports:

- repository emitted;
- native import/build/start/load;
- scenario and contract tests;
- normalized trace equivalence;
- RAG grounding;
- graph liveness/side-effect safety;
- prompt/tool/tenant security;
- performance/resilience/operations;
- E0–E5/P05;
- customer acceptance;
- certificate envelope and residual risk.

`UNKNOWN`, `UNSUPPORTED`, `BOUNDED`, `RUNTIME_MONITORED` and `WAIVED` remain distinct.

## 10. Non-negotiable invariants

1. Every terminal state references an exact RevisionSet.
2. Every target claim references an exact upstream version and adapter digest.
3. Every generated file can be traced to AI-SIR nodes, rules/templates and source evidence.
4. Every worker write checks tenant, execution epoch, lease generation and fencing.
5. Every side effect has an idempotency key and reconciliation state.
6. Every proof result records tool digest, inputs, assumptions, resource bounds and evidence hash.
7. Every certificate is independently bound to a sealed evidence root.
8. No visual DSL or target framework becomes canonical semantic truth.
9. No unsupported feature is silently dropped.
10. No package-validation result is presented as target-repository production certification.
