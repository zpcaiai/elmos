# Codex/Claude-Class Cache Parity Acceptance Matrix

Every row is mandatory unless the related provider/runtime is explicitly unsupported and the release claim excludes it.

| ID | Scenario | Required assertion | Evidence |
|---|---|---|---|
| CP-001 | Stable 10-turn same-project session | cached eligible input tokens >=90% after turn 3 | provider counters + prefix manifests |
| CP-002 | Stable session | unexpected full-prefix miss <=2% | miss events + first differences |
| CP-003 | Exact validated rerun | weighted Action reuse >=99%; redundant model/compiler/test calls =0 | coordinator trace + worker/provider counters |
| CP-004 | <=1% file edit, interfaces unchanged | weighted compute reuse >=90% | expected/actual invalidation closure |
| CP-005 | Implementation-only edit | unnecessary downstream invalidation <=5% | public-interface hashes + DAG trace |
| CP-006 | Formatting-only edit | semantic AST/IR reuse; no semantic downstream rebuild | raw vs semantic hashes |
| CP-007 | Public-interface edit | affected dependents invalidate; unrelated modules remain hits | dependency graph |
| CP-008 | Unchanged lockfiles/toolchain | environment snapshot hit >=95% | snapshot observations |
| CP-009 | Warm environment | p95 startup reduction >=80% versus clean cold control | repeated timing report |
| CP-010 | Service restart | sealed artifact reuse >=99.9% | recovery plan + CAS verification |
| CP-011 | Stable same-project follow-up | net wall-clock saved >=70% | cold/warm paired runs |
| CP-012 | Stable same-project follow-up | model input cost saved >=80% | normalized provider usage/cost |
| CP-013 | 100-turn session with compaction | no overflow/lost state; post-warmup cached-token reuse >=80% | checkpoint equivalence replay |
| CP-014 | Model change | explicit necessary miss and namespace transition | provider profile + reason code |
| CP-015 | Effort change | explicit necessary miss and namespace transition | prompt observation |
| CP-016 | Tool-schema change | exact changed segment reported | prefix first-difference |
| CP-017 | TTL expiry | `TTL_EXPIRED`, not unknown | provider observation |
| CP-018 | Wrong worker/replica injection | `WRONG_SHARD/REPLICA`; affinity fixes or safe miss | routing decisions |
| CP-019 | Corrupt CAS/environment object | execution rejected; clean fallback succeeds | corruption test |
| CP-020 | Cross-tenant request | hit=0, access denied/safe miss | security test |
| CP-021 | Cache store outage | correct slower path; no data loss/duplicate side effect | chaos trace |
| CP-022 | Worker death during generation | checkpoint/staged files recovered | lease/recovery journal |
| CP-023 | Provider cache disabled | correct result through no-cache path | provider kill switch |
| CP-024 | Accounting | raw counters and unified attribution differ <=0.5% | reconciliation report |
| CP-025 | Unknown outcomes | <=0.1% eligible observations; alert and budget consumption | dashboard/alert test |
| CP-026 | False hit sentinel | accepted false hits=0 | negative corpus |
| CP-027 | Under-validated cached result | cannot publish; required validation reruns | validation-level test |
| CP-028 | Autotuning regression | 5% mandatory-SLO regression triggers halt/rollback | controlled canary |
| CP-029 | Fairness stress | no cohort starvation; configured worst-cohort floors pass | multi-tenant load test |
| CP-030 | Package/release integrity | all 42 Skills, schemas, tests, benchmark CLI, checksums pass | `./validate.sh` |
