# PostgreSQL 17.5 to DM8 8.1.3.140

Directional, exact Batch 31 database modernization pack for PostgreSQL 17.5
Community to DM8 8.1.3.140 Enterprise in explicitly selected
Oracle-compatible mode.

The checked-in local evidence covers one synthetic parameterized query through
typed parsing, the exact allowlisted DM8 adapter, emission, and target-dialect
reparse. It does not contain a licensed DM8 instance, PostgreSQL execution,
result equivalence, data movement, performance, security, cutover, or
independent evidence. Those states remain `NOT_RUN`; production certification
remains `NOT_CERTIFIED`.

Validate the repository-owned pack:

```sh
python3 scripts/batch31/validate_database_pack.py database-packs/postgresql-to-dm8
python3 scripts/batch31/validate_canonical_ir.py database-packs/postgresql-to-dm8/canonical-ir/model.json
python3 scripts/batch31/run_database_gate.py database-packs/postgresql-to-dm8
```
