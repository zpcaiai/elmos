# Implementation notes: architecture-diagram-mindmap-ppt-generation

## Production objective

生成 C4、UML、数据流、部署图、思维导图和项目介绍演示文稿。

## Required components

- typed task and capability contracts;
- version-pinned repository, data, model, toolchain and environment snapshots;
- Semantic IR or an equivalent typed domain representation;
- deterministic executor, independent verifier and evidence aggregator;
- durable workflow checkpoints, idempotency keys and compensation handlers;
- tenant-aware observability, cost accounting and machine Wall-clock ETA.

## Algorithmic considerations

1. Prefer parser/compiler/database/runtime facts over model guesses.
2. Keep uncertainty and unsupported constructs explicit in the IR.
3. Minimize the modified surface and compute blast radius before writes.
4. Validate at multiple levels: syntax, build, behavior, security, performance and operations.
5. Use shadow, dual-run, canary or simulation for high-risk transitions.
6. Preserve source locations, rules, decisions and counterexamples in the Evidence Bundle.

## Edge cases

- mixed versions and partially generated repositories;
- reflection, dynamic code, vendor extensions and undocumented behavior;
- flaky tests, environment drift and non-deterministic outputs;
- data, time, locale, precision, concurrency and retry differences;
- offline/private environments and unavailable external dependencies;
- cross-tenant, licensing, privacy and training-rights restrictions.

## Telemetry and SLOs

Record activation precision, semantic coverage, verification pass rate, repair count, regression escapes, human edit distance, queue time, machine Wall-clock, tool/model cost, rollback success and customer acceptance.

## Promotion rule

`specification-ready` does not mean runtime-complete. Production promotion requires implementation, independent replay, target-matrix testing and the Evidence level declared in `skill.yaml`.
