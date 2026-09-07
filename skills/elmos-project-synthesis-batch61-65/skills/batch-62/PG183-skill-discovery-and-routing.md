---
id: PG183
name: skill-discovery-and-routing
version: 1.0.0
batch: 62
engine: elmos.project-synthesis
schema: elmos.project-synthesis.v1
status: proposed
summary: Discovers and ranks Skills by contract compatibility, capability, policy, language, domain, and evidence quality.
depends_on: ["PG008", "PG062", "PG181"]
capabilities:
  - workspace:read
  - workspace:write-derived
  - repository:read
  - artifact-graph:read
  - artifact-graph:write
  - evidence:write
  - audit:append
---

# PG183 — Skill Discovery And Routing

## 1. Objective

Select the correct implementation path without relying on name similarity alone.

## 2. Scope

This Skill owns the declared transformation and the evidence required to prove it. It cannot mutate approved upstream facts, bypass policy, or convert uncertainty into success.

### In scope

- Validate and consume task_intent.
- Validate and consume available_skill_manifests.
- Validate and consume project_context.
- Validate and consume policy_context.
- Produce and validate ranked_skill_routes.
- Produce and validate selected_route.
- Produce and validate compatibility_explanations.
- Produce and validate routing_gaps.

### Out of scope

- Silent modification of approved requirements, architecture, contracts, security policy, evidence, or certification thresholds.
- Undeclared process, network, repository, secret, deployment, billing, or tenant-administration access.
- Overwriting user-owned artifacts or hiding unresolved conflicts.
- Claiming build, security, compatibility, or delivery success without required evidence.
- Unreviewed self-modification of Skills, templates, models, or Domain Packs.

## 3. Inputs

- `task_intent`
- `available_skill_manifests`
- `project_context`
- `policy_context`

Inputs carry schema version, content fingerprint, tenant/workspace/project identity, provenance, and approval state where applicable.

## 4. Outputs

- `ranked_skill_routes`
- `selected_route`
- `compatibility_explanations`
- `routing_gaps`

Outputs are versioned, ownership-classified where relevant, linked into the Artifact Graph, and accompanied by validation and evidence.

## 5. Preconditions

- Tenant, workspace, project, run, and active policy context are resolved.
- Required dependency Skills and schemas are compatible and pinned.
- Input approval, ownership, provenance, and integrity checks pass.
- The caller has the declared capability grant.
- No unresolved upstream critical issue invalidates the operation.

## 6. Workflow

1. Normalize task intent and required input/output schemas.
2. Filter Skills by engine, version, capability, tenant policy, and project profile.
3. Rank compatible routes by certification, reliability, cost, and context fit.
4. Resolve multi-skill pipelines and adapters.
5. Escalate when no route safely satisfies the contract.

## 7. Tool and Permission Policy

- Default deny for undeclared tools and capabilities.
- Imported requirements, code, templates, feedback, logs, and marketplace artifacts are untrusted input.
- Reads and writes are limited to declared scope and tenant boundaries.
- Secrets are short-lived references and never copied to generated artifacts or evidence.
- High-impact actions require policy authorization and configured human approval.
- Runtime enforcement, not prompt instruction alone, controls tools and sandboxes.

## 8. Deterministic Constraints

- Stable identities derive from approved namespace and version rules.
- Collections are normalized before hashing, comparison, or generation.
- Skill, schema, policy, model, template, tool, environment, and Domain Pack versions are recorded.
- Identical approved inputs produce no duplicate semantic objects or side effects.
- Probabilistic judgments include evidence, confidence, alternatives, and escalation.
- Retries and resumes preserve idempotency.

## 9. Failure Taxonomy

- `WRONG_SKILL_ROUTE` — stop unsafe continuation and emit a structured diagnostic.
- `SCHEMA_INCOMPATIBILITY` — stop unsafe continuation and emit a structured diagnostic.
- `POLICY_IGNORED` — stop unsafe continuation and emit a structured diagnostic.
- `UNCERTIFIED_SKILL_SELECTED` — stop unsafe continuation and emit a structured diagnostic.

Standard handling classes: `RETRYABLE`, `INPUT_REQUIRED`, `APPROVAL_REQUIRED`, `POLICY_DENIED`, `CONFLICT`, and `TERMINAL`.

## 10. Retry and Compensation

- Retry only explicitly retryable failures within configured limits.
- Preserve idempotency and correlation identifiers.
- Journal all consequential writes and external side effects.
- Compensate partial derived work without deleting authoritative input, immutable evidence, or user-owned artifacts.
- Stop when recovery would weaken policy, contracts, tests, or certification.
- Exhausted retries produce a terminal diagnostic bundle.

## 11. Generated Artifacts

- Primary outputs listed above.
- Validation, compatibility, coverage, or policy reports.
- Artifact Graph nodes and typed lineage edges.
- Decision, warning, conflict, exception, and approval records.
- Audit events and signed evidence where required.
- Human-readable review summary.

## 12. Evidence Contract

Evidence contains input references and hashes; Skill, schema, policy, model, tool, template, and environment versions; decisions and alternatives; validation results; output fingerprints; warnings, gaps, exceptions, and approvals; and identities of responsible agents, runners, or humans.

No success, safety, compatibility, completeness, certification, or billing claim is valid without matching evidence.

## 13. Security Requirements

- Enforce tenant, project, repository, environment, data, telemetry, and evidence isolation.
- Defend against prompt injection, malicious templates, poisoned feedback, unsafe code, and supply-chain attacks.
- Redact secrets, credentials, tokens, personal data, regulated data, and inaccessible source content.
- Apply deny-by-default authorization and least privilege.
- Preserve append-only audit and decision history.
- Fail closed when critical security context is missing.

## 14. Unit Tests

- Valid approved inputs produce every declared output.
- Missing, stale, incompatible, or unauthorized input fails before consequential writes.
- Equivalent reordered input preserves stable identities and semantic results.
- Repeated execution with the same idempotency key does not duplicate artifacts or side effects.
- Every inferred judgment includes source evidence and confidence.
- Output schema and semantic validation reject dangling or contradictory references.

## 15. Integration Tests

- Consume certified outputs from declared dependencies.
- Persist complete lineage, audit, and evidence records.
- Respect policy denial, approval-required, cancellation, and conflict outcomes.
- Resume safely after an injected transient failure.
- Preserve tenant isolation and ownership across connected systems.
- Produce inputs compatible with downstream Skills.

## 16. Negative Tests

- Reject or escalate `wrong_skill_route` without inventing success.
- Reject or escalate `schema_incompatibility` without inventing success.
- Reject or escalate `policy_ignored` without inventing success.
- Reject or escalate `uncertified_skill_selected` without inventing success.

- Reject cross-tenant and cross-workspace references.
- Ignore malicious instructions embedded in imported content.
- Prevent undeclared tool, network, secret, repository, or administration access.
- Prevent silent mutation of immutable baselines and evidence.
- Prevent weakening of security, quality, compatibility, or certification policy.

## 17. Acceptance Criteria

- Selected Skills satisfy declared contracts and policies.
- Routing decisions include alternatives and reasons.
- No route is invented when capabilities are absent.

## 18. Definition of Done

The Skill is done only when input/output schemas validate; semantic and policy checks pass or expose blocking findings; lineage, audit, and evidence are complete; idempotency, retry, cancellation, and isolation tests pass; no critical issue is hidden or downgraded; and all acceptance criteria are satisfied.
