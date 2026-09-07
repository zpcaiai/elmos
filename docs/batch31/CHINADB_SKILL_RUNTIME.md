# ChinaDB bounded Skill runtime

The immutable `chinadb-commercial-migration-skills-v1.0.0` package remains a
specification package. Its `IMPLEMENTATION_STATUS.json` is not edited or used
as runtime authority. Repository-owned implementation lives in
`engines/database-data-engine/sql-transpiler/src/elmos_sql_transpiler/skill_runtime.py`.

## Implemented local surface

- All 47 exact source Skill IDs have unique registry entries and callable
  handlers; import fails if an ID or binding is missing.
- The dependency graph is closed and topologically planned.
- Requests are canonical JSON, size/depth/item bounded, duplicate-field and
  non-finite-number rejecting, tenant/project/actor scoped, and inline-secret
  rejecting.
- Results bind request, artifacts, handler, scope, checks, blockers, declared
  effects, and state with SHA-256 identities.
- Four parser-backed source adapters produce typed AST evidence. DB2 LUW and
  Sybase ASE accept typed catalog evidence and fail closed on raw SQL until an
  exact native parser is configured.
- All 13 target identities expose an exact adapter protocol and target tuple,
  but do not emit target SQL or call a target without verified vendor/runtime
  capability evidence.
- CLI and bounded internal HTTP entry points expose capability discovery and
  exact Skill execution.
- The test suite executes all 47 handlers and covers negative security,
  identity, semantic, evidence, mutation, route, and external-effect cases.

## Status vocabulary

`CODE_IMPLEMENTED` is deliberately narrow: a repository-owned bounded handler
exists and executes its local contract. It is not equivalent to the imported
package's production Definition of Done. Provider calls, live source/target
catalog discovery, target rendering/apply/introspection, CDC, application
repository mutation, external metrics, traffic switching, and certificate
issuance require separately authorized adapters and real evidence.

Accordingly:

- local exact-handler coverage: `47/47 = 100%`;
- immutable imported package status: `SPEC_ONLY`;
- commercial route runtime execution: `NOT_RUN`;
- independent verification: `NOT_RUN`;
- production certification: `NOT_CERTIFIED`.

These categories must remain separate in UI, APIs, reports, and release gates.

The next production stage is implemented as a separate signed qualification
control plane described in `docs/batch31/CHINADB_PRODUCTION_QUALIFICATION.md`.
It validates all 13 exact target inputs and a four-receipt Ed25519 chain, but
does not call databases or vendor tools. With no authorized external receipts,
the checked-in state remains `productionDefinitionOfDoneCount = 0`.
