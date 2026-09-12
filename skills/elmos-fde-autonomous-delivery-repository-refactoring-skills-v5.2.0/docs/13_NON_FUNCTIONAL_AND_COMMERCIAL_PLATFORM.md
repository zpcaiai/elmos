# 13 — Non-functional and Commercial Platform Requirements

| ID | Name | Requirement |
|---|---|---|
| NFR-001 | Tenant isolation | No data, artifact, cache, telemetry, vector, graph, credential, or execution context may cross tenant boundaries. |
| NFR-002 | Default-deny authority | All tool and connector capabilities are denied unless granted by an invocation-scoped lease. |
| NFR-003 | Environment ownership | Authority must belong to the actual execution environment and survive resume without widening. |
| NFR-004 | Verified security context | Privileged requests must carry a host-minted, integrity-protected security context. |
| NFR-005 | Remote executor fencing | Replaced or stale executors must be unable to commit results or effects. |
| NFR-006 | Result interception | Every tool result must be intercepted, typed, policy-checked, and attached to the correct invocation before commit. |
| NFR-007 | Atomic commit | Repository changes must be purpose-bounded, independently verifiable, and individually reversible. |
| NFR-008 | Idempotency | Retry or resume must not duplicate repository, database, message, billing, or external side effects. |
| NFR-009 | Checkpoint durability | Accepted progress must survive process, worker, and network failure according to the task durability class. |
| NFR-010 | Cancellation | Long-running jobs must support bounded cancellation and explicit effect reconciliation. |
| NFR-011 | Auditability | Every material decision, tool call, artifact, approval, waiver, and state transition must be attributable and queryable. |
| NFR-012 | Artifact identity | All source, generated, evidence, model, tool, and deployment artifacts must use immutable content identity. |
| NFR-013 | Evidence freshness | Evidence reuse must be invalidated by incompatible changes to revisions, environments, policies, tools, models, databases, or adapters. |
| NFR-014 | Independent verification | The producer of a change or claim must not be the sole verifier or completion authority. |
| NFR-015 | Honest completeness | Unknown, unsupported, inaccessible, ambiguous, and stale areas must remain visible in all completion statements. |
| NFR-016 | Production claim boundary | The capability package may claim E3 readiness at most and must never issue E4, E5, P05, regulatory, or customer certification. |
| NFR-017 | Data minimization | Only data necessary for the approved purpose may be read, retained, displayed, or sent to a model. |
| NFR-018 | Secret isolation | Secrets must be brokered to tools and never copied into model-visible prompts, logs, or artifacts. |
| NFR-019 | Data residency | Storage, processing, backup, telemetry, and model routing must honor tenant and engagement residency policy. |
| NFR-020 | Retention and deletion | Artifacts and derived data must have explicit retention, legal hold, deletion, and cryptographic erasure behavior. |
| NFR-021 | Encryption | Sensitive data must be encrypted in transit and at rest with customer-appropriate key ownership. |
| NFR-022 | Supply-chain integrity | Build inputs, dependencies, images, tools, and outputs require provenance, integrity checks, and policy evaluation. |
| NFR-023 | Multi-tenant fairness | Schedulers and quotas must prevent one tenant or repository from starving others. |
| NFR-024 | Backpressure | Queues, event streams, model calls, and analysis workers must have bounded concurrency and backpressure. |
| NFR-025 | Control-plane responsiveness | Interactive control-plane operations should meet the configured p95 latency objective excluding long-running jobs. |
| NFR-026 | Progress visibility | Long jobs must emit monotonic, evidence-backed progress and blocker states. |
| NFR-027 | Horizontal scale | Stateless coordinators and partitionable workers must scale independently without changing semantic ownership. |
| NFR-028 | Large-repository readiness | The architecture must support controlled pilots above 500k LOC and at least one benchmark above 1M LOC before commercial claims. |
| NFR-029 | Incremental analysis | Unchanged artifacts and compatible evidence should be reused by content identity rather than rescanned blindly. |
| NFR-030 | Deterministic replay | A run must be reproducible from pinned inputs or explicitly state sources of nondeterminism. |
| NFR-031 | Observability | Trace, metrics, structured logs, profiles, policy decisions, and artifact identities must correlate by tenant, engagement, run, step, and revision. |
| NFR-032 | SLO ownership | Each production service and workflow requires defined SLIs, SLOs, error budgets, owners, and escalation. |
| NFR-033 | Graceful degradation | Unavailable models, analyzers, connectors, or services must produce controlled degradation or explicit blockers, never silent omission. |
| NFR-034 | Recovery | Backup, restore, failover, replay, and disaster-recovery procedures must be testable and evidence-producing. |
| NFR-035 | Compatibility | Public APIs, events, schemas, CLI output, and persisted contracts require versioning and backward-compatibility policy. |
| NFR-036 | Extensibility | Language, framework, database, scanner, model, connector, and runtime integrations must use replaceable adapters. |
| NFR-037 | Adapter non-authority | Adapters may produce candidate artifacts and evidence but cannot own semantic truth or completion status. |
| NFR-038 | Accessibility | User-facing product surfaces must support configured accessibility targets and keyboard-complete critical workflows. |
| NFR-039 | Internationalization | Time, locale, currency, units, encoding, text direction, and translation must be explicit and testable. |
| NFR-040 | Usability | Critical FDE and approval workflows must expose evidence, risk, scope, and next action without requiring raw log inspection. |
| NFR-041 | Cost attribution | Model, compute, storage, network, license, and human-review costs must be separately attributable. |
| NFR-042 | Machine time | Estimates and actuals must report machine wall-clock, queue, and human-review time separately. |
| NFR-043 | Budget enforcement | Tenant, engagement, route, model, tool, and worker budgets require alert, throttle, stop, and approval policies. |
| NFR-044 | Safe model routing | Model choice must consider task ambiguity, evidence risk, privacy, latency, cost, and provider policy. |
| NFR-045 | Model/provider portability | Canonical task, tool, result, evidence, and checkpoint contracts must not depend on one provider. |
| NFR-046 | Statistical rigor | Noisy or probabilistic evaluations require sample size, variance, uncertainty, segmentation, and decision rules. |
| NFR-047 | Counterexample retention | Failed cases and contradictory evidence must be retained as first-class artifacts. |
| NFR-048 | Policy as code | Consequential deterministic controls should be enforceable through versioned policy or validation code. |
| NFR-049 | Human approvals | Irreversible, destructive, privileged, regulated, or production-impacting actions require named human approval. |
| NFR-050 | Separation of duties | Planning, execution, verification, waiver, and certification roles must be independently assignable. |
| NFR-051 | Workspace isolation | Each write-heavy agent or plan step must use an isolated workspace or non-overlapping file scope. |
| NFR-052 | Context control | Agents should receive a map and task-relevant references rather than a monolithic instruction dump. |
| NFR-053 | Documentation integrity | Architecture, runbooks, rules, and capability catalogs require owners, freshness checks, and broken-link validation. |
| NFR-054 | Skill trigger quality | Skills require positive, contextual, negative-control, and adjacent-intent eval cases. |
| NFR-055 | Safe installation | Package installation must support dry-run, clean-state checks, backup, receipt, modified-file protection, and reversible uninstall. |
| NFR-056 | Deterministic release archive | Repeated release builds from identical inputs must have stable file sets and hashes. |
| NFR-057 | Migration safety | Schema and contract migrations must be additive-first, replayable, reconciled, and rollback-aware. |
| NFR-058 | No duplicate ownership | The extension must not create a second Goal store, AI-SIR owner, runtime authority, or completion authority. |
| NFR-059 | Commercial isolation | Billing, quotas, support entitlements, and contract terms must not alter technical evidence or completion results. |
| NFR-060 | Customer export | Customers must be able to export approved reports, evidence indexes, changes, and runbooks in stable machine-readable formats. |

## Commercial operating requirements

Multi-tenant plans and entitlements; per-account concurrency; project/token/compute credits; budgets and alerts; queue fairness; audit exports; customer-managed connectors; private/VPC/on-prem deployment; support tiers; SLA/SLO definitions; status and incident communication; data portability/deletion; billing reconciliation; plugin/Skill/Adapter marketplace governance.
