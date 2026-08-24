# Application Code Automatic Refactoring

- **Skill ID:** `08-application-code-auto-refactor`
- **Version:** `1.0.0`
- **Category:** core/application
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Refactor database-dependent application code across drivers, ORM dialects, native SQL, stored-procedure calls, pagination, identity retrieval, error handling and transactional assumptions, with AST-aware patches and compile/test evidence.

## Inputs

- Application repositories
- Source/target route
- Database call graph from assessment
- SQL/procedural conversion outputs
- Framework-specific application adapters

## Required outputs

- Patch set per repository
- Driver/config migration
- Converted embedded/native SQL
- Stored-logic call replacements
- Updated tests/fixtures
- Compile and integration evidence

## Implementation modules / repository contract

- app_refactor/discovery.py
- app_refactor/patch_plan.py
- app_refactor/sql_literals.py
- app_refactor/config.py
- app_refactor/transactions.py
- app_refactor/errors.py

## Interfaces and contracts

- Language-specific skills implement AST/project tooling
- Generated patches are reviewable diffs; no direct production deployment

## Workflow

1. Discover DB access frameworks and generated code boundaries.
2. Change drivers/URLs/pools/dialects/config without leaking secrets.
3. Rewrite native SQL using source maps from SQL conversion.
4. Update sequence/identity/key generation and generated-key retrieval.
5. Rewrite stored procedure/function calls, including lift-to-app paths.
6. Map vendor error codes/SQLSTATE to stable domain exceptions.
7. Re-check transaction propagation, isolation, retries and distributed-lock assumptions.
8. Compile, unit test and run app+target integration tests.

## Mandatory tests

- String-built SQL
- ORM native queries
- MyBatis XML/dynamic tags
- EF/Dapper raw SQL
- Batch generated keys
- Optimistic locking
- Retry on deadlock/serialization
- Large IN lists
- Pagination
- Connection session init
- Stored procedure OUT/REF cursor

## Required evidence

- Patch manifest with source spans
- Build/test logs
- DB call graph after refactor
- Remaining vendor-specific dependency count

## Fail-closed / escalation rules

- Never modify generated/vendor directories unless adapter declares them owned.
- Ambiguous SQL string construction becomes manual/high-risk.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
