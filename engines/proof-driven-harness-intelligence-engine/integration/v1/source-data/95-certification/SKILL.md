---
name: elmos-e0-e5-harness-certification
description: Consume semantic, transformation, runtime, policy, test, security, and production evidence into release gates.
priority: P0
---

# K10 — E0–E5 Integration

## E0 — Environment & Repository Readiness

Evidence:
- repository manifest;
- build-system discovery;
- dependency resolution;
- language/framework detection;
- toolchain versions;
- LSP/compiler availability;
- fixture identity;
- environment reproducibility.

## E1 — Static Semantic Integrity

Evidence:
- compile/typecheck;
- LSP diagnostics;
- symbol/reference integrity;
- AST/IR validation;
- semantic graph diff;
- API/schema compatibility.

## E2 — Functional & Regression Verification

Evidence:
- generated/curated tests;
- regression suite;
- mutation tests;
- contract tests;
- data fixtures;
- negative tests;
- flaky-test classification.

## E3 — Runtime Behavioral Equivalence

Evidence:
- DAP traces;
- state/exception equivalence;
- DB side effects;
- transactions;
- messages;
- API behavior;
- deterministic replay;
- counterexamples resolved or accepted.

## E4 — Nonfunctional / Security / Resilience

Evidence:
- security review;
- dependency vulnerabilities;
- authorization checks;
- concurrency;
- performance;
- load/stress;
- fault injection;
- recovery;
- resource behavior.

## E5 — Production Confidence

Evidence:
- shadow/canary;
- observability;
- rollback;
- real workload;
- SLO/SLA;
- production runbook;
- residual risks;
- operator sign-off where required.

## Release verdict

PASS
CONDITIONAL_PASS
FAIL
INSUFFICIENT_EVIDENCE

`INSUFFICIENT_EVIDENCE` MUST NOT be mapped to PASS.

## Finding policy

- P0 unresolved → FAIL.
- P1 unresolved → FAIL unless explicit approved exception policy permits.
- P2/P3 → recorded risk and route-specific threshold.
