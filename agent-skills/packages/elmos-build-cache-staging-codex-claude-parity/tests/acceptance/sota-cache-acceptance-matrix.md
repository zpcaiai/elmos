# SOTA Cache Acceptance Matrix

All comparisons use the same request sequence, capacity, warm-up, object-size semantics, protected roots, and trace subset.

| ID | Scenario | Required evidence | Pass condition |
|---|---|---|---|
| SOTA-01 | Deterministic replay | Same trace/config run three times | Identical decisions and metrics |
| SOTA-02 | Strong baselines | LRU, SIEVE, S3-FIFO, W-TinyLFU, GDSF | All complete without correctness failures |
| SOTA-03 | One-hit scan | Monorepo/dependency scan trace | Adaptive policy does not materially underperform S3-FIFO/SIEVE |
| SOTA-04 | High temporal reuse | Repeated AST/IR/action trace | W-TinyLFU or selected policy improves weighted value over LRU |
| SOTA-05 | Heterogeneous size | Tiny manifests plus large build outputs | Size-aware policy reports BHR and avoided-work gains without capacity mismatch |
| SOTA-06 | Expensive sparse reuse | Model/compile/test artifacts | Cost-aware policy retains high-value objects and improves avoided compute |
| SOTA-07 | DAG known future | Planned conversion graph | Protected next-use objects are not evicted; prefetch precision and critical-path savings reported |
| SOTA-08 | Restore slower than recompute | Slow remote cache | Restore bypass executes and reduces net wall-clock cost |
| SOTA-09 | Workload regime shift | Scan → reuse → large-object phases | Selector uses hysteresis, avoids oscillation, and falls back safely |
| SOTA-10 | OOD/drift | Feature distribution outside certified range | Learning disabled; fixed fallback selected |
| SOTA-11 | Model unavailable | Inference/signature failure | Data plane continues with fixed policy; no lookup outage |
| SOTA-12 | Multi-tenant pressure | Skewed tenant burst | Quotas/fairness hold and protected active roots remain available |
| SOTA-13 | Cache restart | Policy-state snapshot/recovery | No corruption; reset or restore is explicit and auditable |
| SOTA-14 | Trace privacy | Inspect emitted trace corpus | No raw source, prompt, generated code, secret, or reversible tenant identifier |
| SOTA-15 | Equal-capacity certification | Final untouched trace window | Configured weighted improvement gate passes; worst cohort and p95 overhead guardrails pass |
| SOTA-16 | Cache correctness | Corruption, stale key, wrong validation, cross-tenant attempts | Zero invalid reuse; all attempts rejected and recorded |
| SOTA-17 | Project file staging | Crash during generated-file write/promotion | Staged state recovers; no half-published tree |
| SOTA-18 | Rollback | Induced hit/value or latency regression | Automatic rollback restores certified fixed policy and policy epoch |

## Minimum report fields

- trace corpus and split digests;
- policy implementation/config/model digests;
- capacity and protected-root configuration;
- object and byte hit ratio;
- avoided compute and model-token ratios;
- critical-path and net wall-clock savings;
- p95 lookup/policy overhead;
- prefetch precision/coverage/wasted bytes;
- churn/write amplification;
- tenant fairness;
- correctness/security failures;
- confidence intervals or repeated-run variance;
- selection, rejection, and rollback reasons.
