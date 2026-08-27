# ETGB SOTA Skills v1.1 repository implementation

The pinned source archive is
`skills/subskills/elmos-etgb-sota-skills-package-v1.1.0.tar.gz` with SHA-256
`6c95898310e1b9052e5431c7996e1f397b54612084ef70761d9bb5a78760fe1e`.
The extracted package remains immutable, untrusted reference material. The
repository-owned executable implementation is
`engines/etgb-engine/src/elmos_etgb`.

The importer independently checks archive format, path/link safety, checksums,
manifest identity, the 24-Skill dependency DAG, schemas, materialized case
coverage, and provenance before generating wrappers. The exact source names
are bound through `SkillRegistry`; no generic dispatcher silently claims a
missing provider capability.

Implemented local control-plane surfaces include candidate freezing, risk plans
and stable shards, durable phase state/CAS/fencing, checkpoint resume, budget
reservation and reconciliation, owner-bound authority, hidden-test partition
checks, content-addressed redacted evidence, differential/metamorphic oracles,
statistics, performance budgets, failure triage, incident regressions, supply
chain inventory, and tenant-isolated fair scheduling.

The v1.1 materialization contains 46,664 cases with complete declared coverage:
cross-cutting 800, cross-language 29,535, project-generation 1,451,
spring-modernization 3,117, and sql-conversion 11,761.

## Evidence boundary

Local unit/integration and smoke results are engineering evidence. The latest
local smoke gate is `READY_FOR_EXTERNAL_GATE`; it is not certification. The
release gate intentionally remains `BLOCKED / NOT_CERTIFIED` because the
corpus has 17 missing signed license reviews and there is no independently
verified release attestation, native external provider evidence, or production
Harness evidence in this checkout.

Run the repository integration target with `make etgb-sota-skills`. It does not
execute source-package scripts, grant provider access, deploy, certify, or
approve a release.
