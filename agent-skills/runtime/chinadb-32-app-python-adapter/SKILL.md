---
name: chinadb-32-app-python-adapter
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Python Database Refactor Adapter. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "32-app-python-adapter"
  source_path: "skills/32-app-python-adapter/SKILL.md"
  source_sha256: "sha256:6be6743619b8b02b8affffca9769e5c527f370dfb36c4abcae18a9b08ceb93e1"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# Python Database Refactor Adapter

- **Skill ID:** `32-app-python-adapter`
- **Version:** `1.0.0`
- **Category:** application-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `08-application-code-auto-refactor`

## Objective

Implement AST/project-aware refactoring for Python, integrating shared SQL/procedural conversion results without blind global replacements.

## Inputs

- Repository/workspace
- Route manifest
- DB call graph
- Converted SQL/procedure strategy map
- Target driver/provider metadata

## Required outputs

- Reviewable patch set
- Build/dependency changes
- Config changes
- Updated tests
- Remaining vendor-specific dependency report

## Implementation modules / repository contract

- adapters/app/python/discover.py
- adapters/app/python/patch.py
- adapters/app/python/build.py
- adapters/app/python/frameworks.py

## Interfaces and contracts

- Implements app adapter: `discover`, `extract_db_calls`, `plan_patch`, `apply_patch`, `build`, `test`

## Workflow

1. Detect project/framework versions and build system.
2. Map source call sites to conversion results using source spans and call graph.
3. Patch dependencies/config and DB interaction code.
4. Preserve application domain APIs unless migration plan explicitly changes them.
5. Compile/build and execute unit+target-integration tests.
6. Report unresolved dynamic SQL or framework-specific vendor APIs.

## Mandatory tests

- DB-API drivers
- SQLAlchemy engine/dialect/text SQL
- Django backend/raw SQL
- Alembic migrations
- stored procedure/cursor calls
- transaction/retry behavior
- async DB clients
- Dynamic/literal SQL extraction
- Build on clean checkout
- Patch idempotency

## Required evidence

- Git diff manifest
- Build/test log
- DB dependency scan before/after
- Target integration evidence

## Fail-closed / escalation rules

- Do not hand-edit lockfiles/generated code outside package-manager/framework conventions.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `32-app-python-adapter`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
