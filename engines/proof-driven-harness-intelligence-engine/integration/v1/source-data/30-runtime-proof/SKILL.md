---
name: elmos-runtime-equivalence-proof
description: Use debugger/runtime traces, differential execution, replay, and side-effect comparison to prove behavioral preservation.
priority: P0
---

# K3 — Runtime Equivalence & Debugging

## Skills

- dap-adapter-discovery
- dap-runtime-driver
- breakpoint-plan-generator
- runtime-state-capture
- call-stack-capture
- variable-snapshot
- exception-trace
- memory-state-probe
- differential-debugger
- control-flow-equivalence
- state-equivalence
- exception-equivalence
- api-response-equivalence
- database-effect-equivalence
- transaction-boundary-equivalence
- message-effect-equivalence
- file-effect-equivalence
- concurrency-observation
- deterministic-replay
- scenario-replay
- fault-injection-runner
- counterexample-generator
- runtime-root-cause-localizer
- auto-debug-repair-loop

## Differential scenario

The source and target MUST run from equivalent scenario inputs and environment contracts where feasible.

Compare:

- observable outputs;
- state transitions;
- exceptions;
- persistence effects;
- transaction boundaries;
- queue/message effects;
- authorization outcomes;
- timing/order where semantically relevant.

## Non-equivalence

A difference is classified as:

- intended_change;
- allowed_nondeterminism;
- environment_difference;
- semantic_regression;
- insufficient_evidence.

`insufficient_evidence` MUST NOT be treated as pass.

## Acceptance

E3-ready evidence requires reproducible scenario ids, input digests, source/target traces, normalized diff, verdict, and residual uncertainty.
