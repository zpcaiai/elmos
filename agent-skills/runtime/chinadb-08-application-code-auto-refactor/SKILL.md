---
name: chinadb-08-application-code-auto-refactor
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Application Code Automatic Refactoring. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "08-application-code-auto-refactor"
  source_path: "skills/08-application-code-auto-refactor/SKILL.md"
  source_sha256: "sha256:d623a66881810eb1d170722fd0cf4a7991a3f1c230828aea8343d5115138ab10"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
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

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `08-application-code-auto-refactor`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
