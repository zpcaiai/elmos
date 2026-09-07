# Repository Semantic Graph

Minimum node families:
- Repository, module, file, package, component, owner.
- Symbol, type, function, method, field, endpoint, event, message.
- Build target, dependency, artifact, container, deployment.
- Database, schema, table, column, constraint, routine, query.
- Runtime span, RPC, queue/topic, exception, metric hot path.
- Test, contract, fuzz target, invariant, proof obligation.
- Transformation edit, rule, skill, tool, model, assumption.
- Evidence, gate decision, SBOM, provenance and signature.

Minimum edge families:
`DEFINES`, `REFERENCES`, `IMPLEMENTS`, `CALLS`, `DEPENDS_ON`, `BUILDS`, `DEPLOYS`, `READS`, `WRITES`, `EMITS`, `CONSUMES`, `TRACED_AS`, `TESTED_BY`, `PROVES`, `TRANSFORMED_BY`, `OWNED_BY`, `AFFECTS`.

All graph facts must carry source, timestamp/revision and confidence/authority so compiler-grade facts can outrank heuristic LLM inferences.
