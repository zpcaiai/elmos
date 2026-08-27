# Test and Validation Strategy

Formal assurance itself requires testing.

## Test pyramid

1. Schema and contract tests: every JSON/YAML/API/event contract.
2. Pure-kernel unit tests: status, cache, gate, DAG, fencing and evidence.
3. Adapter conformance: success, refutation, timeout, crash, malformed output, resource exhaustion and cancellation.
4. Semantic mutation tests: seed incorrect transformations and ensure the verifier finds them.
5. Differential tests: source/target runtime, database and trace comparison.
6. Model mutation tests: weaken an invariant or alter transition order and require a counterexample.
7. Failure injection: worker crash, stale token, duplicate events, partition, database failover, object-store failure.
8. Security tests: cross-tenant, source leakage, malicious formulas, sandbox escape and waiver abuse.
9. Scale tests: million-line repositories, large proof DAGs, formula size and artifact throughput.
10. Golden Route certification.

## Soundness-focused mutations

- change `<=` to `<` or `==`;
- remove authorization guard;
- swap filter order;
- change transaction propagation or rollback exception;
- narrow integer/decimal type;
- alter NULL predicate;
- remove SQL constraint;
- duplicate billing event;
- allow stale fencing token;
- map UNKNOWN to PASS.

A commercial verifier should kill seeded mutations relevant to its declared proof profile. Mutation score is not a proof, but low mutation sensitivity reveals missing obligations or broken adapters.

## Test data

Counterexamples are minimized and promoted into permanent regression corpora. Customer data is redacted or stays in customer-controlled execution environments.
