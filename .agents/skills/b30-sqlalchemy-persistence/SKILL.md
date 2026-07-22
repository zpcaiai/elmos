---
name: b30-sqlalchemy-persistence
description: Implement or certify SQLAlchemy persistence migration, covering declarative and imperative mappings, sessions and unit of work, relationships, loading, queries, transactions, async sessions, events, migrations, provider behavior, and target ORM or data-access profiles.
---

## Operating mode

Work in the repository. Inspect existing Batch 20-29 modules, contracts, build commands, framework packs, and tests before editing. Implement the smallest production-shaped vertical slice that satisfies this skill; do not stop at a design document when code, manifests, and executable tests can be added.

Read these shared contracts first:

- `../../../docs/batch30/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch30/QUALITY_GATES.md`
- `../../../docs/batch30/REPOSITORY_LAYOUT.md`
- `../../../docs/batch30/VERSION_POLICY.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch30/scaffold_framework_pack.py ...`
- `python3 scripts/batch30/validate_framework_pack.py ...`
- `python3 scripts/batch30/run_framework_gate.py ...`

## Global constraints

- Treat every framework migration pack as directional and version-specific. Reverse migration and version upgrade are separate packs.
- Extract runtime behavior into the framework-neutral Framework Contract Model before generating target code. Do not implement annotation-name substitution as the migration architecture.
- Invoke real source and target build/runtime tools. A generated project that only parses is not evidence of support.
- Preserve authentication, authorization, transaction, persistence, message delivery, configuration precedence, validation, lifecycle, and error contracts.
- Keep development, holdout, and representative-repository corpora physically separate. Do not author rules from holdout cases.
- Prefer deterministic mappings and certified adapters. Model-generated output is a candidate and must pass the same build, contract, behavior, security, and test-integrity gates.
- Record unsupported, conditional, and unknown behavior explicitly. Never hide it with TODOs, permissive stubs, broad exception swallowing, disabled security, or weakened tests.
- Record exact framework/runtime/provider versions, source and target commits, recipe digest, model/prompt versions, toolchain digests, and evidence references.
- Fix repeated failures in the fingerprint, contract model, recipe, adapter, or generator instead of patching many generated files.
- Run the narrowest relevant tests first, then the independent holdout suite and framework certification gate before making release claims.


## Skill 1175: SQLAlchemy and Python persistence migration

Extract SQLAlchemy runtime persistence contracts and migrate them to an approved target ORM or data layer without losing query, unit-of-work, relationship, transaction, concurrency, or schema behavior.

## Use this skill when

- A FastAPI, Flask, or other Python application uses SQLAlchemy.
- SQLAlchemy is moving to EF Core, JPA/Hibernate, another Python ORM, or explicit SQL.
- A framework pack has unresolved data/query/transaction behavior.

## Framework-specific risks and invariants

- SQLAlchemy supports declarative, imperative, hybrid, event-driven, sync, and async patterns.
- Identity map, autoflush, expire-on-commit, loading, cascades, and unit-of-work differ from target ORMs.
- Expression language and custom SQL may not have safe target equivalents.
- Alembic history, models, and live schema may disagree.

## Workflow

1. Lock SQLAlchemy, Alembic, database/driver, sync/async, and target ORM/provider versions.
2. Fingerprint mappings, types, keys, relationships, cascades, loading, sessions/scopes, events, queries, transactions, locks, custom types, raw SQL, and migrations.
3. Extract persistence/transaction contracts with query AST or retained SQL forms.
4. Select a target profile and map each query/session/relationship behavior to translation, adapter, retained SQL, or block.
5. Generate model/config/query/unit-of-work code and schema migration artifacts for a complete repository/service slice.
6. Run source/target database tests for CRUD, flush, rollback, detached/expired state, relationships, concurrency, and representative queries.
7. Compare models, Alembic history, live schema, and target plan; prevent destructive automatic changes.
8. Run holdout cases for hybrid properties, custom types, events, complex queries, async sessions, and provider-specific SQL.

## Required repository outputs

- `framework-packs/sqlalchemy-to-<target-persistence>/`
- Mapping/session/query/runtime fingerprint
- Persistence/transaction contracts and query corpus
- Target model/query/unit-of-work generators
- Schema/migration reconciliation report
- Database behavior/holdout evidence

## Verification

- Run source SQLAlchemy and target ORM on representative real database providers.
- Compare query results, transactions, cascades, loading, concurrency, and provider-specific behavior.
- Validate schema plans without destructive production execution.
- Run holdout and the gate.

## Stop and escalate when

- Live schema or migration history is unavailable for production claims.
- Complex queries are translated by string or regex substitution.
- Session/unit-of-work semantics are ignored because CRUD passes.
- Provider-specific locking, precision, or transactions cannot be proven.

## Definition of done

The SQLAlchemy pack captures models, sessions, queries, transactions, and schema history, generates a real target persistence slice, passes database and holdout tests, and retains or blocks unsupported constructs explicitly.
