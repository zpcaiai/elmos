---
name: agent-protocol-tooling-validation
description: Validate all declared Agent, Tool, MCP, A2A, AG-UI and Harness Protocols capabilities with executable positive, boundary, adversarial, concurrency, recovery and evidence-backed release tests.
---

# Agent, Tool, MCP, A2A, AG-UI and Harness Protocols Validation

## Purpose

Use this Skill to plan, execute and certify the `agent-protocol-tooling` product domain. It owns **65 declared capabilities** (40 P0, 20 P1, 5 P2) across 4 execution contexts and four mandatory variants.

## Inputs

- Frozen release candidate and feature-registry revision.
- Tenant, project, environment authority, budget and fencing context.
- Concrete cases from `suites/full-product.jsonl` whose business line is `agent-protocol-tooling`.
- Exact provider, browser, SDK, database or infrastructure profiles required by each case.
- Hidden-test authority and sealed evidence destination.

## Workflow

1. Resolve every feature ID to `matrices/feature-registry.yaml` and reject unknown or untested functionality.
2. Provision an isolated context for: mcp, a2a, ag-ui, local-or-remote-tool.
3. Execute nominal, boundary, negative-security and concurrent-recovery variants.
4. Capture API/UI/event/state traces before normalization.
5. Apply the domain Oracle `agent-protocol-authority-side-effect-trace-and-security` plus security, state, audit and unsupported-disclosure Oracles.
6. Reconcile side effects, retry receipts, checkpoints, usage and tenant ownership.
7. Seal evidence and return pass, fail, blocked or unavailable; never infer success from compilation or HTTP status alone.

## Capability surface

Representative capabilities include: Tool Registry Discovery, Tool Schema And Version Negotiation, Tool Whitelist, Parameter Level Authorization, Environment Owned Authority, Attachment Owned Authority, Invocation Scoped Capability Lease, Lease Expiry Before Side Effect, Verified Security Context, Secret Broker Short Lived Token, Network Egress Deny By Default, Filesystem Root Policy. The complete source of truth is `matrices/full-product.yaml`; no prose list may override it.

## Mandatory negative and recovery coverage

- Unauthorized, cross-tenant, replayed, stale, malformed and over-budget requests.
- Duplicate delivery, partial commit, provider timeout, worker loss and resume from durable checkpoint.
- Secret exposure, prompt/tool injection and unsafe output where AI or external content is involved.
- Concurrency races, idempotency conflicts and stale fencing-token rejection.
- Failure disclosure: unsupported or unavailable paths must block a success claim.

## Release gates

- Feature binding coverage: 100%.
- P0 critical Oracle pass: 100%; P0 SSER: 0.
- Unavailable Adapter or environment profile: 0 for release.
- Cross-tenant leakage, privilege expansion, duplicate charge or unreconciled side effect: 0.
- Evidence completeness and provenance integrity: 100%.

## Production Adapter

Route execution through `external-agent-protocol-harness` under `integrations/harness/full-product-adapters.yaml`. An adapter stub or skipped case is implementation progress, not product certification.

## Outputs

- Per-case result and normalized Oracle findings.
- Raw trace, state, security and recovery evidence.
- Feature coverage deltas, failure clusters and permanent regressions.
- Signed domain certificate or a fail-closed blocker report.
