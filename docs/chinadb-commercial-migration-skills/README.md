# ChinaDB Commercial Migration Skills Integration

This directory records the repository installation of `chinadb-commercial-migration-skills` version `1.0.0`.

- Canonical source: `skills/chinadb-commercial-migration-skills-v1.0.0/`
- Installed aliases: 47 exact `chinadb-<source-directory>` names in both `agent-skills/runtime/` and `.agents/skills/`
- Target planning baselines: 13, copied byte-for-byte into their target Skill directories
- Planned directed routes: 78
- Excluded targets: PolarDB, PolarDB-X, TDSQL
- Current state: `SPEC_ONLY` / external evidence `NOT_RUN` / production certification `NOT_CERTIFIED`

Static package validation and installation are engineering evidence only. They do not prove SQL, procedural, DDL, data, CDC, application, performance, cutover, rollback, security, or production behavior. Exact source and target database execution plus the conservative Batch 31 gate remain required.

Verify the canonical package, both installation roots, all copied baselines, interfaces, provenance, digests, and drift with:

```sh
python3 tooling/integrate_chinadb_commercial_migration_skills.py --check
```
