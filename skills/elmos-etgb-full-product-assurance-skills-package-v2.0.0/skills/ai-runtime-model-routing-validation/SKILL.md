---
name: ai-runtime-model-routing-validation
description: Validate all declared AI Runtime, Model Routing and Context Management capabilities with executable positive, boundary, adversarial, concurrency, recovery and evidence-backed release tests.
---

# AI Runtime, Model Routing and Context Management Validation

## Purpose

Use this Skill to plan, execute and certify the `ai-runtime-model-routing` product domain. It owns **67 declared capabilities** (37 P0, 25 P1, 5 P2) across 4 execution contexts and four mandatory variants.

## Inputs

- Frozen release candidate and feature-registry revision.
- Tenant, project, environment authority, budget and fencing context.
- Concrete cases from `suites/full-product.jsonl` whose business line is `ai-runtime-model-routing`.
- Exact provider, browser, SDK, database or infrastructure profiles required by each case.
- Hidden-test authority and sealed evidence destination.

## Workflow

1. Resolve every feature ID to `matrices/feature-registry.yaml` and reject unknown or untested functionality.
2. Provision an isolated context for: synchronous, streaming, batch, fallback-chain.
3. Execute nominal, boundary, negative-security and concurrent-recovery variants.
4. Capture API/UI/event/state traces before normalization.
5. Apply the domain Oracle `ai-runtime-quality-cost-safety-trace-and-reproducibility` plus security, state, audit and unsupported-disclosure Oracles.
6. Reconcile side effects, retry receipts, checkpoints, usage and tenant ownership.
7. Seal evidence and return pass, fail, blocked or unavailable; never infer success from compilation or HTTP status alone.

## Capability surface

Representative capabilities include: Provider Registration And Health, Model Catalog And Capabilities, User Selected Model, Automatic Model Selection, Task Specific Model Routing, Quality Cost Latency Policy, Provider Fallback, Model Timeout And Retry, Rate Limit Backoff, Circuit Breaker, Streaming Token Order, Stream Cancel And Resume Policy. The complete source of truth is `matrices/full-product.yaml`; no prose list may override it.

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

Route execution through `external-ai-runtime-harness` under `integrations/harness/full-product-adapters.yaml`. An adapter stub or skipped case is implementation progress, not product certification.

## Outputs

- Per-case result and normalized Oracle findings.
- Raw trace, state, security and recovery evidence.
- Feature coverage deltas, failure clusters and permanent regressions.
- Signed domain certificate or a fail-closed blocker report.
