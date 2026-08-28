---
name: elmos-ai-golden-route-trusted-cross-org-agent
description: Certify signed A2A discovery, workload identity, delegated authority and auditable cross-organization task execution.
version: 4.0.0
status: production-contract
priority: P1
risk: critical
route_owner: domain-pack.project-generation
routable: false
---

# Golden Route: Trusted Cross-Organization Agent

## Objective

Certify signed A2A discovery, workload identity, delegated authority and auditable cross-organization task execution.

This Skill is a **commercial production implementation contract** for the Elmos `project-generation` Domain Pack. It is not a product-completion claim. The Skill may create typed commands and immutable artifacts, but it never owns a shadow Goal, semantic truth, execution authority, Proof Result or Completion Certificate.

## Use When

Use this Skill when a revision-bound Goal requires its capabilities, or when an existing generated project, protocol, Skill, plugin, agent system, RAG system or deployment must be imported, upgraded, validated or continuously recertified.

The router must select this Skill from explicit capability requirements. Merely mentioning a framework name is not enough to bypass capability negotiation, authority checks or proof planning.

## Non-Goals

- Do not replace K1 intent, K2/K3 semantic evidence, K7 execution authority or K8 completion authority.
- Do not treat a scaffold, generated file count, LLM review, mock-only test or successful syntax parse as production completion.
- Do not silently omit unsupported, conditional or version-dependent behavior.
- Do not invent provider versions, release digests, secrets, legal decisions, customer acceptance or production evidence.
- Do not execute tools, network calls, deployments or data writes with ambient authority.
- Do not promote self-generated tests or LLM judgments to an independent Oracle.

## Route and Canonical Ownership

- **Routable owner:** `domain-pack.project-generation`
- **Component routable:** `false`
- **Kernel authorities used:** K1, K3, K6, K7, K8
- **Intent authority:** K1 Goal/Specification and exact RevisionSet.
- **Semantic authority:** K2 evidence and K3 AI-SIR/protocol/target profiles.
- **Reasoning and transformation:** K4/K5 may propose and emit bounded candidates.
- **Execution authority:** K7 Environment, workspace, attachment and tool-request authority snapshots.
- **Proof authority:** independent K6 verifier portfolio.
- **Completion authority:** K8 E0–E5/P05 Certifier.

## Domain Semantics

The implementation must model at least these canonical entities:

- `RouteRun`
- `HoldoutSuite`
- `RepeatRun`
- `CustomerAcceptance`
- `CommercialCertificate`
- `GoldenRouteTrustedCrossOrganizationAgentRun`
- `GoldenRouteTrustedCrossOrganizationAgentDecision`

Required semantic capabilities:

- Signed Agent Card exchange
- Trust registry and version negotiation
- Workload attestation
- Attenuated downstream delegation
- Revocation and incident drill

All entities carry `tenant_id`, `project_id`, `goal_id`, `revision_set_id`, schema version, producer identity, content hash, provenance, freshness and lifecycle status. Mutable projections are reconstructible from an append-only event journal or equivalent durable history.

## Inputs

Required, typed and revision-bound inputs:

- `GoalContract`, `RequirementGraph`, `ObservableContract`, `AssumptionLedger` and acceptance scenarios.
- Exact `RevisionSet` fixing source, requirements, policy, workflow, model, toolchain, environment, adapter and Domain Pack versions.
- Relevant `RepositoryEvidenceGraph`, `AI-SIR`, target/protocol capability profiles and semantic-gap obligations.
- `EnvironmentAuthority`, tenant/data classification, budget, residency, network, secret and tool policy.
- `ProofObligationGraph`, accepted evidence classes, assurance level and release envelope.
- Outputs from declared dependencies.

## Dependencies

- `elmos-a2a-v1-agent-card-trust-compiler`
- `elmos-agent-registry-resource-discovery-governor`
- `elmos-agent-workload-delegated-identity-controller`

## Primary Outputs

- `golden-routes/trusted-a2a/evidence/`
- `cross-org-agent-certificate.json`
- `delegation-audit.json`
- `revocation-drill-report.json`

Every output is content-addressed or otherwise immutably versioned, source-linked, evidence-bound and assigned an explicit terminal or non-terminal status.

## Implementation Blueprint

1. **Discover and freeze.** Detect the actual source/target/protocol version, compute hashes and freeze the RevisionSet before mutating state.
2. **Compile domain semantics.** Parse typed inputs into the Skill domain model; reject unknown critical fields and emit gap obligations.
3. **Negotiate capability.** Resolve every required feature as `SUPPORTED`, `CONDITIONAL`, `EMULATED`, `EXTERNAL_RUNTIME`, `EXTERNAL_POLICY`, `UNSUPPORTED` or `BLOCKED`.
4. **Plan deterministically.** Build a dependency-aware, resumable work graph with idempotency, rollback, proof and cost/ETA contracts.
5. **Execute with scoped authority.** Use short-lived Environment-owned authority, current lease/fencing and a side-effect ledger.
6. **Materialize native artifacts.** Prefer compiler/schema/native APIs/templates; constrain generative edits to unresolved bounded gaps.
7. **Run native and adversarial validation.** Execute the Skill-specific matrix in `native-test-matrix.yaml`, not only generic unit tests.
8. **Close counterexamples.** Minimize failures, attribute them to source/spec/adapter/runtime, repair locally and rerun affected obligations.
9. **Seal evidence.** Record commands, exit codes, versions, digests, traces, resource bounds, assumptions and artifact hashes.
10. **Certify or block.** Only K8 may issue a bounded certificate; unresolved critical conditions produce `BLOCKED`.

## API, Events and Persistence

The reference control API is defined in `api-contract.yaml`. Implementations may map it to REST/gRPC/commands but must preserve:

- idempotency keys and request/response schema versions;
- tenant, Goal, RevisionSet, execution epoch and fencing checks on every write;
- `Requested`, `Profiled`, `Planned`, `Started`, `Checkpointed`, `EvidenceProduced`, `Blocked`, `Failed`, `Cancelled` and `CompletedCandidate` events;
- durable run/step/event tables, content-addressed artifacts, proof/evidence indexes and side-effect reconciliation records;
- PostgreSQL RLS or an independently verified equivalent for tenant isolation.

## Production Controls

1. **Fail closed:** critical `UNKNOWN`, `UNSUPPORTED`, stale evidence, unresolved authority or unsettled side effect blocks affected claims.
2. **Deterministic first:** schema compilers, native APIs, codemods and reproducible builders precede model-generated patches.
3. **No ambient authority:** deny-by-default filesystem, network, secret and deployment access; authorize path and parameter scope.
4. **Durable execution:** checkpoint, replay, pause/resume/cancel, lease generation, fencing, idempotency and transactional outbox.
5. **Version discipline:** exact source/target/protocol/provider/tool versions and digests are pinned at release time.
6. **Independent evidence:** generator and repair agents cannot certify their own outputs.
7. **Multi-tenant isolation:** storage, memory, cache, vector namespace, trace, dataset and evidence are tenant-scoped.
8. **Privacy and residency:** data egress, retention, deletion and provider use follow the compiled policy profile.
9. **Budget enforcement:** wall-clock, token, compute, storage, network, tool, fanout and side-effect budgets are machine-enforced.
10. **Upgrade safety:** semantic drift invalidates evidence; upgrades use three-way semantic merge and rollback checkpoints.

## Threat Model

- **cross-org impersonation** — must have a preventive control, a detective signal, a negative fixture and a response action.
- **delegation escalation** — must have a preventive control, a detective signal, a negative fixture and a response action.
- **trust anchor compromise** — must have a preventive control, a detective signal, a negative fixture and a response action.
- **tenant confusion** — must have a preventive control, a detective signal, a negative fixture and a response action.
- **revocation not propagated** — must have a preventive control, a detective signal, a negative fixture and a response action.

The complete trust-boundary and abuse-case specification is in `threat-model.yaml`. Security tests are release gates, not optional documentation.

## Required Tests

- two trust domains
- tampered card
- unattested workload
- delegation boundary
- tenant isolation
- revocation during run

Also execute applicable schema, unit, contract, integration, differential, property, metamorphic, mutation, fuzz, fault, recovery, security, performance, backup/restore, installer, upgrade and evidence-integrity suites.

## Verification

A valid Proof Result records:

```yaml
subject_revision_set: <exact-id>
claim: <typed-claim>
status: PROVED|TESTED|BOUNDED|RUNTIME_MONITORED|WAIVED|UNKNOWN|UNSUPPORTED|REFUTED
verifier:
  name: <independent-tool-or-suite>
  digest: <release-pinned-digest>
inputs:
  hashes: []
  assumptions: []
resource_bounds:
  timeout_seconds: <integer>
  cpu_memory: <declared>
evidence:
  artifacts: []
  trace_ids: []
```

`BOUNDED`, `RUNTIME_MONITORED` and `WAIVED` are never displayed as `PROVED`. A model may propose tests or explain results, but cannot be the authoritative verifier or certifier.

## Stop and Escalate

Stop the affected path and emit a typed blocked result when:

- tenant, authority, execution epoch, lease generation or fencing cannot be resolved;
- an exact version is outside the adapter's certified envelope;
- a critical capability is unsupported or only approximated without approved preservation evidence;
- a native conformance, security, isolation, recovery, deletion, rollback or supply-chain gate fails;
- required independent verification is unavailable and policy disallows a bounded substitute;
- source semantics, data ownership, consent, side-effect settlement or customer acceptance remains unknown;
- repair exceeds cycle, patch-size, semantic-risk, budget or machine wall-clock limits.

## Definition of Done

This Skill is complete for a run only when:

- all declared artifacts exist, validate and bind to the exact RevisionSet;
- native tests required by `native-test-matrix.yaml` executed with current versions and digests;
- required proof obligations have policy-valid terminal statuses;
- critical counterexamples and security findings are closed, or certification is blocked;
- side effects are reconciled and rollback state is known;
- the evidence bundle is sealed and independently evaluated under the applicable E0–E5/P05 envelope.

## Completion Report

Report exact revision/commit/tree hashes; adapter/runtime/model/verifier versions; test and obligation status counts; machine wall-clock duration; token/compute/storage/network cost; cache use; approvals; side effects; rollback state; residual risks; and the Evidence Bundle plus Completion Certificate or Blocked Result references.
