# Canonical Semantic IR, Compiler Frontends, and Transformation Platform

- Skill: `elmos-semantic-ir-compiler-platform`
- Priority: `P1`
- Phase: `G5`
- Dependencies: `elmos-incremental-semantic-index`, `elmos-reproducible-toolchain`, `elmos-content-addressed-cache`

## Objective

Make language and framework modernization depend on compiler evidence and deterministic transformations rather than file-by-file LLM translation.

## Task groups

### Layered IR contract

- [ ] `ELMOS-IR-001` Define Surface CST, Language Semantic IR, Canonical Semantic IR, Domain IR, Target Framework IR, and generated-source stages.
- [ ] `ELMOS-IR-002` Give every node a stable ID, schema version, source span, language/version, provenance, annotations, and extension envelope.
- [ ] `ELMOS-IR-003` Model modules, types, functions, properties, generics, exceptions, concurrency, resources, transactions, serialization, reflection, and side effects.
- [ ] `ELMOS-IR-004` Define Web, Data, AI/ML, Infrastructure, API, database, message, and configuration domain dialects.
- [ ] `ELMOS-IR-005` Define canonical ordering, deterministic serialization, digesting, and schema migration.
- [ ] `ELMOS-IR-006` Store large IR in CAS and metadata/index references in PostgreSQL.

### Adapter SPI

- [ ] `ELMOS-IR-007` Define frontend, backend, framework, type resolver, dependency resolver, runtime trace, build, and test-discovery interfaces.
- [ ] `ELMOS-IR-008` Require adapters to publish capability, supported versions, loss model, known gaps, required toolchain, and deterministic status.
- [ ] `ELMOS-IR-009` Negotiate schema/capability versions before execution.
- [ ] `ELMOS-IR-010` Include adapter binary/config digest in action keys and evidence.
- [ ] `ELMOS-IR-011` Provide conformance fixtures and compatibility tests for each adapter.

### Native language frontends

- [ ] `ELMOS-IR-012` Integrate javac/OpenRewrite for Java and Kotlin compiler APIs for Kotlin.
- [ ] `ELMOS-IR-013` Integrate Roslyn for C# and TypeScript Compiler API for TypeScript/JavaScript.
- [ ] `ELMOS-IR-014` Integrate LibCST plus AST and mypy/Pyright for Python.
- [ ] `ELMOS-IR-015` Integrate Clang LibTooling for C/C++/Objective-C.
- [ ] `ELMOS-IR-016` Integrate go/packages/go/types, rust-analyzer or rustc interfaces, SwiftSyntax/compiler APIs, PHP static analysis, and Dart Analyzer as applicable.
- [ ] `ELMOS-IR-017` Use Tree-sitter as incremental syntax/fallback layer, not the final authority for resolved semantics.

### Framework and domain modeling

- [ ] `ELMOS-IR-018` Implement Spring/Jakarta, ASP.NET, Django/Flask/ASGI, React/Vue, Flutter, persistence, messaging, authentication, caching, and deployment adapters.
- [ ] `ELMOS-IR-019` Map endpoints, middleware, filters, transactions, ORM mappings, configuration binding, scheduled jobs, and lifecycle hooks.
- [ ] `ELMOS-IR-020` Capture implicit framework behavior as explicit IR or an unresolved gap.
- [ ] `ELMOS-IR-021` Separate framework upgrade rules from cross-language translation rules.

### Rule and mutation runtime

- [ ] `ELMOS-IR-022` Define versioned Rule DSL, Mutation DSL, Scenario DSL, and Evidence DSL.
- [ ] `ELMOS-IR-023` Require preconditions, source/target ranges, risk, confidence, ordering, conflicts, reversibility, and idempotency declaration.
- [ ] `ELMOS-IR-024` Support dry run, match explanation, deterministic patch generation, dependency ordering, and composable campaigns.
- [ ] `ELMOS-IR-025` Run a second pass and require no new diff for idempotent recipes.
- [ ] `ELMOS-IR-026` Preserve original worktree and isolate each patch/change set.
- [ ] `ELMOS-IR-027` Emit rule-execution manifest with inputs, matches, outputs, skipped reasons, timing, and evidence.

### Source mapping and gaps

- [ ] `ELMOS-IR-028` Maintain generated node/file mappings back to source CST, semantic nodes, rules, and model edits.
- [ ] `ELMOS-IR-029` Represent unsupported, ambiguous, approximate, manual, and runtime-only semantics explicitly.
- [ ] `ELMOS-IR-030` Attach severity, affected symbols, remediation, evidence requirement, and certification impact.
- [ ] `ELMOS-IR-031` Expose gaps to planning, agent context, validation, review, and evidence pack.
- [ ] `ELMOS-IR-032` Prevent high-risk unresolved gaps from automatic promotion.

### IR quality gates

- [ ] `ELMOS-IR-033` Build CST-to-IR, IR-to-target, same-language round-trip, schema migration, source-map, overload, generics, inheritance, exception, transaction, concurrency, and reflection fixtures.
- [ ] `ELMOS-IR-034` Compare native compiler symbol resolution with canonical graph.
- [ ] `ELMOS-IR-035` Run deterministic-repeat tests across clean workers.
- [ ] `ELMOS-IR-036` Track IR coverage and unknown-node rates by language/framework/version.
- [ ] `ELMOS-IR-037` Reject adapters that silently ignore unknown node kinds.

## Validation

- [ ] Rebuild identical source on separate runners and compare IR digests.
- [ ] Exercise overloads, generics, reflection, transactions, async/concurrency, serialization, and framework lifecycle.
- [ ] Run every idempotent rule twice and require no second diff.
- [ ] Inject unsupported semantics and require explicit blocking gaps.
- [ ] Validate schema migration and source-map round trips.

## Exit gate

- [ ] At least the Java modernization path produces stable canonical IR and compilable target output.
- [ ] Unsupported semantics are visible, scored, and certification-aware.
- [ ] Rules are explainable, composable, versioned, and repeatably idempotent.
- [ ] Every generated region can be traced to source/rule/model provenance.
