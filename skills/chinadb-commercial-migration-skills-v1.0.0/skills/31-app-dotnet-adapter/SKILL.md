# .NET Database Refactor Adapter

- **Skill ID:** `31-app-dotnet-adapter`
- **Version:** `1.0.0`
- **Category:** application-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `08-application-code-auto-refactor`

## Objective

Implement AST/project-aware refactoring for .NET, integrating shared SQL/procedural conversion results without blind global replacements.

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

- adapters/app/dotnet/discover.py
- adapters/app/dotnet/patch.py
- adapters/app/dotnet/build.py
- adapters/app/dotnet/frameworks.py

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

- ADO.NET providers/connections
- Dapper SQL/procedure calls
- EF Core provider/dialect/migrations/native SQL
- TransactionScope/isolation
- DbException vendor codes
- identity/sequence/generated keys
- configuration/health checks
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
