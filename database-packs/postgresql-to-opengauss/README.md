# PostgreSQL 17.5 to openGauss 5.0.0

Directional, exact Batch 31 database modernization pack for PostgreSQL 17.5
Community to openGauss 5.0.0 Enterprise in explicitly selected
PG-compatible mode.

The checked-in local evidence covers one synthetic parameterized query through
typed parsing, the exact allowlisted openGauss adapter, emission, and target-dialect
reparse. It does not contain a licensed openGauss instance, PostgreSQL execution,
result equivalence, data movement, performance, security, cutover, or
independent evidence. Those states remain `NOT_RUN`; production certification
remains `NOT_CERTIFIED`.

Validate the repository-owned pack:

```sh
python3 scripts/batch31/validate_database_pack.py database-packs/postgresql-to-opengauss
python3 scripts/batch31/validate_canonical_ir.py database-packs/postgresql-to-opengauss/canonical-ir/model.json
python3 scripts/batch31/run_database_gate.py database-packs/postgresql-to-opengauss
```
