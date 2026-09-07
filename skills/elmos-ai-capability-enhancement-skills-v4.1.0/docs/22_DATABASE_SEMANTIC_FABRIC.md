# Database Semantic Fabric

DB-SIR separates Catalog, Query, Routine/Trigger, Transaction/Operational and Data-Semantics layers. Parser/transpiler tools are verifier inputs, while real source and target engines remain the behavioral authority. H2 or an unrelated in-memory engine cannot certify a production database route.

Every route must compare results, database state, errors, transactions, locks, triggers, sequences, CDC offsets, execution plans and rollback behavior. Elmos control-plane persistence remains PostgreSQL 17-first; customer project generation and migration is multi-dialect.
