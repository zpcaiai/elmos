---
name: elmos-harness-intelligence
description: Optimize tool choice, model routing, prompt surfaces, context, retries, and harness behavior for quality/cost/latency.
priority: P0
---

# K8 — Harness / Model / Context Intelligence

## Skills

### Tool authority
- tool-authority-router
- semantic-tool-priority
- tool-capability-negotiator
- tool-failure-classifier
- no-silent-fallback
- tool-approval-router

### Model routing
- model-role-router
- model-capability-profile
- model-fallback-chain
- quota-aware-fallback
- provider-failure-fallback
- effort-aware-routing
- phase-model-handoff
- cost-aware-routing
- latency-aware-routing
- quality-aware-routing
- path-scoped-model-policy
- tenant-model-policy
- credential-pool-affinity

### Prompt / skill surface
- prompt-compiler
- prompt-linter
- rfc-normative-policy
- tool-doc-surface-optimizer
- example-contract-validator
- skill-lazy-loader
- rule-lazy-loader

### Context
- context-budget-manager
- append-only-context-optimizer
- adaptive-compaction
- checkpoint
- rewind
- context-promotion
- provider-stream-reset
- context-rebuild
- foreign-session-import

### Benchmark
- harness-ab-test
- tool-format-benchmark
- edit-format-benchmark
- prompt-benchmark
- context-strategy-benchmark
- routing-benchmark
- retry-policy-benchmark

## Model phase routing

RECOMMENDED default:

explore → cheap/fast
architecture → balanced
plan → reasoning
edit → coding
debug → coding/reasoning
review → independent reviewer
formal check → tool-first / formal system

## Metrics

- first-pass success;
- semantic success;
- compile-pass rate;
- test-pass rate;
- repair loops;
- tool calls;
- tokens;
- wall-clock;
- cost;
- provider fallbacks;
- human intervention;
- certification level.

## Acceptance

A routing optimization MUST show no quality regression beyond configured tolerance before promotion.
