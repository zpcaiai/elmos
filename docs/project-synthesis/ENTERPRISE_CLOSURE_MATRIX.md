# Project Synthesis enterprise closure matrix

This matrix is the acceptance and traceability record for business line 5
(B46-B95). It separates repository implementation, local execution, external
runtime evidence, independent verification, customer acceptance, and
certification. A later stage never inherits an earlier stage's result.

## Delivered in this change

| ID | Acceptance criterion | Repository implementation | Local verification | Current decision |
| --- | --- | --- | --- | --- |
| GEN-REL-01 | All eight targets accept more than one entity | Shared request model and every bundled emitter iterate the complete entity set | Source-bound 16/16 PostgreSQL 17.5 matrix | `PASSED_LOCAL`; external `NOT_RUN` |
| GEN-REL-02 | M:N does not silently degrade | `relational-v2` lowers M:N into a deterministic association entity, two tenant-scoped FKs, pair uniqueness, cascade cleanup, permissions and CRUD/OpenAPI | Unit tests plus the 16-profile real PostgreSQL matrix | repository-complete; external `NOT_RUN` |
| GEN-RULE-01 | Invalid domain rules fail closed | Typed same-record literal and field-to-field comparisons validate entity, field, scalar type and operator before SQL generation | PostgreSQL, MySQL and SQLite SQL-contract tests | repository-complete; cross-entity FSM guards remain open |
| GEN-DB-01 | Database claims name an exact engine/version/route | `database-profile-support.json` records PostgreSQL 17.5, MySQL 8.0.41 Python, SQLite 3.45 Python, and explicit unsupported engines | support-matrix validator | only PostgreSQL 17.5 has an eight-language real-engine local matrix |
| GEN-RUN-01 | A Runner cannot mint or replay cross-tenant job authority | Ed25519 job token binds tenant, actor, job, scopes, digest-pinned image, resource limits and <=15 minute lifetime; Runner holds public key only | Python token tests, Node contract replay, Java Runner Agent self-test | bounded local implementation; deployed multi-node fleet `NOT_RUN` |
| GEN-EVID-01 | Local evidence is bound to the executing source | matrix records a length-prefixed engine-source digest and Git subject; validator rejects drift | matrix validator | repository-complete |
| GEN-EXT-01 | External runtime status cannot be produced by source scanning | external gate requires 16 content-addressed receipts, PostgreSQL 17.5 TLS facts, exact engine digest, runtime checks and distinct executor/verifier identities | positive and negative fixture tests | real provider receipts `NOT_RUN` |
| GEN-UAT-01 | Two real design partners provide signed scenario and economics acceptance | governed blank template in `DESIGN_PARTNER_ACCEPTANCE.md` | structural review only | `NOT_RUN`; cannot be completed by a repository agent |

## Remaining exact gaps

| Workstream | What is still absent | Required closure evidence | Priority/status |
| --- | --- | --- | --- |
| Complex archetypes | Banking, supply-chain and billing aggregates are not symmetric, equivalent native implementations in all eight targets | independent corpus, native builds, behavior comparison and target-specific review for every archetype/language cell | P1 / `OPEN` |
| Cross-entity invariants | State-machine guards, atomic aggregate constraints and cross-entity transaction semantics are not compiled comprehensively | typed rule contract, transactional lowering and real database negative/concurrency tests per target | P1 / `OPEN` |
| Additional databases | MariaDB, SQL Server, Oracle, TiDB, OceanBase and DM8 exact routes are not implemented; MySQL 8.0.41 real-engine execution is absent | Batch 31 exact route contracts, licensed media where needed, real source/target engines and reconciliation | P1 / `NOT_RUN` |
| Managed databases | AWS RDS, GCP Cloud SQL and Alibaba Cloud RDS TLS, secret rotation, pool failover, read/write topology and restore have not run | provider-authenticated receipts and content-addressed logs | P1 / `NOT_RUN` |
| Distributed middleware | Seata/Temporal, Kafka/RabbitMQ/RocketMQ, DLQ, idempotency, Redis protection and locking are not proven as a symmetric eight-language runtime matrix | real multi-service topology, broker/cache failure injection and reconciliation receipts | P2 / `NOT_RUN` |
| Hosted Runner Fleet | The repository has durable queue, node credential/rotation, lease fencing, quotas and a rootless Runner Agent; no authorized multi-node cloud fleet or remote attestation campaign has run | provider deployment, scheduler saturation/fairness, isolation escape tests, kill/recovery, attestation and cost receipts | P0 / `NOT_RUN` externally |
| SRE and DR | No authorized canary rollback, PITR, offsite restore, spike/soak, chaos or SLO campaign for the exact release | deployment/rollback receipt, restore reconciliation, load traces, SLO report and accountable owner | P2 / `NOT_RUN` |
| Independent gate and customer UAT | No current independent signature and no two real customer acceptances | verifier outside the executor environment, external trust anchor, two signed UAT records and unit-economics report | P1 / `NOT_RUN`, `NOT_CERTIFIED` |

## Claim boundary

The maximum current claim is `LOCAL_ENGINEERING / limited`. The local
PostgreSQL matrix does not prove a hosted provider, production deployment,
disaster recovery, independent review, customer acceptance, or certification.
Those states remain `NOT_RUN` and the business line remains `NOT_CERTIFIED`.
