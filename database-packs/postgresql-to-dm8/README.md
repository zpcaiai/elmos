# PostgreSQL 17.5 to DM8 8.1.4.6 rev244896

Directional, exact Batch 31 database modernization pack for PostgreSQL 17.5
Community to DM8 8.1.4.6 rev244896 Enterprise in explicitly selected
Oracle-compatible mode.

The checked-in local evidence covers one synthetic parameterized query through
typed parsing, the exact allowlisted DM8 adapter, emission, and target-dialect
reparse. The Phase-1 source/target SQL, CDC, reconciliation, failure-injection,
cutover, rollback, performance, and evidence contracts are executable candidate
assets, not execution evidence. Local Docker image and driver identities are
pinned, but this checkout does not contain a formal Enterprise license receipt,
an attested dedicated Runner, or an independent verifier engagement. Those
external states remain `NOT_RUN`; production certification remains
`NOT_CERTIFIED`.

The fixed pilot tuple is PostgreSQL 17.5 Community to single-instance, non-MPP
DM8 8.1.4.6 build `03134284294-20241009-244896-20119` Enterprise with
`dm-jdbc` 8.1.3.140, explicitly selected
Oracle-compatible mode, `UTF-8`, `BINARY`, and `Asia/Shanghai`. DM8 RLS must be
enabled and initialized before the security candidate can be executed. Exact
runtime image and driver identities must be reverified by the external
qualification provider together with the license, environment, and
Runner-attestation receipts.

Validate the repository-owned pack:

```sh
python3 scripts/batch31/validate_database_pack.py database-packs/postgresql-to-dm8
python3 scripts/batch31/validate_canonical_ir.py database-packs/postgresql-to-dm8/canonical-ir/model.json
python3 scripts/batch31/validate_dm8_phase1_contract.py
python3 scripts/batch31/run_database_gate.py database-packs/postgresql-to-dm8
```

Only `run_database_gate.py` may produce the Batch 31 decision. The DM8-specific
validator checks completeness and fail-closed state; it never certifies the
route.
