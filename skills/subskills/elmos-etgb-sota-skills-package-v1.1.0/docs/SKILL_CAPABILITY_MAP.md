# ETGB v1.1 Skill Capability Map

`skills/manifest.yaml` is authoritative. This document explains how the 24 Skills compose into one production evaluation system.

| Skill | Primary responsibility | Required production evidence |
|---|---|---|
| `etgb-orchestrator` | End-to-end plan, run, resume, aggregate and certify | candidate digest, plan digest, state transitions, final gate decision |
| `test-case-authoring` | Matrix/case/Oracle authoring and review | schema validation, capability-cell trace, independent Oracle owner |
| `spring-modernization-validation` | Servlet/JSP/Struts/Spring to Boot 4 | HTTP/UI/session/transaction/security/DB differential evidence |
| `repository-translation-validation` | Whole-repository language conversion | source/target build, behavior/state, dependency and architecture adaptation evidence |
| `project-generation-validation` | Greenfield and evolutionary project generation | executable requirements, acceptance tests, deployment and backward-compatibility evidence |
| `sql-dialect-routine-validation` | SQL/DDL/DML/Routine/Trigger conversion | dual-DB result/state/side-effect/transaction evidence |
| `differential-oracle-engine` | Capture, normalize and compare source/target | raw evidence, normalized evidence, first difference, ignore-policy digest |
| `metamorphic-fuzz-mutation` | Property, fuzz, metamorphic, mutation and fault campaigns | seed, generator version, minimized reproducer, mutation kill result |
| `corpus-governance` | Pin, license-review, time-split and maintain corpora | commit SHA, license decision, provenance, contamination controls |
| `release-certification` | Evaluate hard gates and promotion | complete score, gate config digest, waiver records, signed decision |
| `production-harness-integration` | Durable phase execution and Adapter contract | state history, checkpoint, usage, outbox/idempotency receipts |
| `environment-authority-sandbox` | Environment/Attachment-owned least privilege | authority document/digest, owner/fence decision, denied attempts |
| `checkpoint-resume-recovery` | Pause/resume/cancel/compensate/crash recovery | checkpoint chain, side-effect receipts, fresh fencing token, recovery replay |
| `evidence-provenance-ledger` | Content-addressed redacted tamper-evident evidence | blob digests, event chain, root digest, signature verification |
| `budget-cost-eta-governance` | Token/credit/compute/wall-clock budgets | reservation, idempotent usage events, reconciliation, calibrated machine ETA |
| `risk-based-test-selection` | Impact/history/uncertainty/gap-based plans | selection reasons, random control seed, stable shards, plan digest |
| `benchmark-integrity-hidden-tests` | Prevent leakage, memorization and self-grading | hidden-test authority separation, temporal split and leakage probes |
| `observability-failure-triage` | OTel instrumentation and failure clustering | trace/span IDs, normalized signature, root-cause class, reproducer link |
| `performance-scale-certification` | Latency/resource/cost/L4 repository certification | workload and hardware digest, warmup, percentiles, baseline ratios, soak evidence |
| `statistical-validity-reproducibility` | Seeds, confidence and non-inferiority | seed set, distribution, confidence interval and stability result |
| `supply-chain-artifact-security` | Untrusted repo and artifact security | SBOM, provenance, signature, dependency policy and sandbox result |
| `incident-regression-learning` | Convert incidents into permanent regression assets | incident link, minimized fixture, hidden case, mutant and planner regression |
| `multi-tenant-scheduling-isolation` | Tenant isolation, concurrency and fairness | tenant/account scope, quota, lease, queue decision, cache/artifact isolation |
| `release-candidate-integrity` | Freeze all candidate components | source/model/Prompt/Skill/rule/image/Oracle/normalization digests |

## Invocation graph

1. `release-candidate-integrity` freezes the evaluated object.
2. `risk-based-test-selection` freezes case scope and shards.
3. `etgb-orchestrator` invokes the applicable domain Skills through `production-harness-integration`.
4. Runtime authority, checkpoint, budget and evidence Skills enforce execution invariants on every phase.
5. Oracle, fuzz/mutation and statistical Skills produce assurance results.
6. Observability/triage and incident learning turn failures into actionable and permanent regressions.
7. `release-certification` consumes only complete, sealed evidence and returns `PROMOTE`, `PROMOTE_WITH_WAIVER`, `REJECT` or `BLOCKED`.

A dependency is never permission inheritance. Every Skill invocation is re-authorized against the exact owning Environment or Attachment.
