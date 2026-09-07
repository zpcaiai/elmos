# Business-line Assurance Matrix

| Business line | Core claim | Main observations | Formal methods |
|---|---|---|---|
| Spring modernization | Spring Boot 4 refines legacy Struts/Servlet behavior | HTTP, binding, Session, DB, messages, auth, exception, transaction | route-language inclusion, JML, state/refinement models, trace validation |
| Cross-language conversion | target repository preserves source semantics | values, heaps, exceptions, effects, concurrency | formal SIR, rule proofs, product programs, assume–guarantee |
| Project generation | implementation satisfies frozen requirements | data/API/workflow/security/resource properties | Alloy/SMT, TLA+, verified core, noninterference |
| SQL conversion | target SQL/routines preserve result and state semantics | bag/set/order, NULL, types, state, trigger/transaction trace | SQLSolver/VeriEQL, SMT, Boogie/Dafny, model checking |
| Elmos platform | task, credit, lease and evidence protocols remain safe | state, owner, token, ledger, artifact commits | TLA+/Apalache, invariants, fencing protocol |

## Skill distribution

| Domain | Count | Representative Skills |
|---|---:|---|
| core | 10 | `elmos-formal-spec-ir`, `elmos-observable-behavior-contract`, `elmos-proof-obligation-planner`, `elmos-assumption-ledger` … |
| spring-modernization | 10 | `elmos-spring-route-binding-proof`, `elmos-spring-security-chain-model`, `elmos-spring-transaction-refinement`, `elmos-java-jml-contract-verifier` … |
| cross-language | 10 | `elmos-language-semantic-profile`, `elmos-semantic-ir-formal-semantics`, `elmos-rule-preservation-prover`, `elmos-cross-language-product-program` … |
| project-generation | 9 | `elmos-requirement-to-formal-spec`, `elmos-architecture-constraint-checker`, `elmos-generated-workflow-model-checker`, `elmos-tenant-noninterference-verifier` … |
| sql-conversion | 10 | `elmos-sql-semantic-ir`, `elmos-sql-query-equivalence`, `elmos-schema-losslessness-proof`, `elmos-routine-contract-verifier` … |
| platform | 11 | `elmos-tla-task-runtime-model`, `elmos-credit-billing-invariant-model`, `elmos-lease-fencing-verifier`, `elmos-counterexample-to-test` … |

## Cross-cutting minimum

Every line uses Formal Spec IR, Observation Contract, Assumption Ledger, Proof Status Policy, TCB Registry, Verifier Router, Proof Cache, durable orchestration, immutable evidence, drift monitoring and fail-closed release gates.
