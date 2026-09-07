# Runtime Estimation Contract

## Required distinction

### Autonomous system wall-clock runtime

Elapsed time eLMOS itself needs to generate or convert a project:

```text
T_system =
  T_queue
+ T_snapshot/materialization
+ T_parse/index/IR
+ T_rule/generation
+ T_model
+ T_build/test/verification
+ T_transfer/promotion
+ T_retry/recovery
- safe parallel overlap
- cache reuse savings
```

Return at least:

- P50, P80 and P95 wall-clock duration.
- Confidence and data coverage.
- Queue and execution components.
- Critical path and parallel work.
- Cold/warm/cache assumptions.
- Runner/toolchain/model/capacity assumptions.
- Retry, failure and manual-approval risks.
- Estimate version and subsequent actual/variance.

### Human-equivalent effort

A separate comparison: how much engineering, migration, testing and review effort people would normally spend. It may be person-hours/days but must never be labeled as eLMOS runtime.

### Human-in-the-loop delay

Natural elapsed waiting for approval, customer response, manual recovery, merge, credentials or external change window. Report separately. It is excluded from autonomous runtime unless the user explicitly asks for total calendar completion.

## Example

```yaml
system_runtime:
  p50_seconds: 4200
  p80_seconds: 6300
  p95_seconds: 9900
  confidence: medium
  queue_seconds_p50: 180
  critical_path:
    - snapshot
    - baseline-build
    - deterministic-rewrite
    - full-verification
  assumptions:
    cache_state: partial-warm
    runner: 8-vCPU-32GB
    model_route: local-small-then-approved-frontier
human_equivalent:
  engineering_hours_p50: 96
  review_hours_p50: 12
human_in_loop_delay:
  excluded_from_system_runtime: true
  risks:
    - plan approval
    - repository credential resolution
```

## Calibration

Store predicted and actual duration per stage. Evaluate interval coverage and error by repository size, language/framework, toolchain, cache state, runner class, model route, validation scope and failure mode. Do not publish precise ETAs when historical coverage is insufficient; widen the interval and explain why.
