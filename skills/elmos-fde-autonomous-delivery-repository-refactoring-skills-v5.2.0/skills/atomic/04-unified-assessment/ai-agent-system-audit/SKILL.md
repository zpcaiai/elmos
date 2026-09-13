---
name: ai-agent-system-audit
description: Audit model, prompt, retrieval, memory, tool, agent, eval, safety, cost, and recovery behavior in AI-enabled repositories.
---

# Mission

Audit model, prompt, retrieval, memory, tool, agent, eval, safety, cost, and recovery behavior in AI-enabled repositories.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- agent audit
- RAG audit
- prompt injection
- LLM eval
- tool safety

## Do not use when

- judge quality from demo
- allow model to certify itself
- expose private evaluation data

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Map the complete AI execution and trust graph.
2. Collect representative and adversarial evaluation cases under data-use policy.
3. Run deterministic checks, model-based rubrics, red-team cases, and recovery tests.
4. Measure quality, safety, latency, cost, variance, and intervention by segment.
5. Validate high-risk findings with independent evaluators and runtime evidence.
6. Publish findings, eval gaps, and remediation gates.

## Required outputs

- AI system inventory
- quality and safety findings
- eval coverage
- cost-latency report
- remediation gates

## Invariants

- no claim without evidence
- no authority escalation
- all unknowns are explicit
- outputs bind to exact RevisionSet

## Fail closed on

- insufficient evidence
- unsupported technology
- stale RevisionSet
- authority denied
- validation failure
- Material `UNKNOWN`, `UNSUPPORTED`, stale evidence, unresolved critical side effects, or missing approvals.
- Any attempt by this Skill or an Adapter to become the canonical completion authority.

## Authority and side effects

Default deny. Read, workspace-write, external-write, and production-write are separate capabilities. Production writes are prohibited by this capability package. Tool results must be intercepted and checked against the approved plan before commit. Checkpoint before external effects and after each accepted ChangeSet.

## Definition of done

- All checks in `acceptance.yaml` pass with exact revision and environment identity.
- Evidence, counterexamples, unknowns, decisions, cost, and machine wall-clock are recorded.
- An independent verifier returns the result to K8; the producer does not self-approve.
- The maximum standalone claim is E3 capability readiness. E4/E5/P05 require the independent companion package and authorized customer execution.

## Local dependencies

- `issue-ontology-and-finding-normalization`
- `data-event-permission-lineage`
- `test-ci-cd-developer-experience-audit`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
