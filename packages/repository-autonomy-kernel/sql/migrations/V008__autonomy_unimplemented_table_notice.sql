-- Truth-in-schema for the tables nothing writes.
--
-- V001-V004 declare a control plane this package never implemented against
-- PostgreSQL: 23 of the 37 tables the migrations create have no writer and no
-- reader anywhere in the codebase, autonomy_runs - the root the other 22
-- foreign-key to - among them. Measured on a live server: with every migration
-- applied, a dispatch sequence exercising the lease and cache paths writes
-- three SQLite tables and zero PostgreSQL rows.
--
-- Those migrations are released and digest-pinned; they cannot be edited or
-- withdrawn, and a deployment that already applied them has the tables. What
-- can be fixed is the belief. An operator reads \d+, a schema browser or a
-- generated data dictionary far more often than a README, so the warning goes
-- where they are already looking.
--
-- This migration adds comments only. It creates nothing, drops nothing and
-- changes no data, so it is safe to re-run and safe to reverse.
--
-- When one of these tables gains a real writer, delete its line here and its
-- entry in tests/test_persistence_split.py. The test fails if only one moves.


comment on table autonomy_acceptance_decisions is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_adapter_conformance is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_approvals is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_artifacts is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_cache_entries is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_capability_packages is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_change_edges is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_change_nodes is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_checkpoints is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_cost_events is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_elo_ratings is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_eval_runs is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_events is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_evidence is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_findings is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_leases is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_policy_decisions is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_repository_snapshots is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_runs is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_semantic_indices is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_steps is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_tool_calls is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';

comment on table autonomy_validations is
  'NOT WRITTEN BY THIS PACKAGE as of v2.x. Applied, indexed and backed up, and it stays empty. Dispatcher state goes to SQLite via storage.DurableStore under bare names. See sql/README.md and tests/test_persistence_split.py.';
