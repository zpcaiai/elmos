# Execution-level evidence

The engine validates every emission by re-parsing it with `sqlglot` in the
target's strict mode. That leg is a third-party **parser**, not the target's
own grammar, and it cannot see a statement that parses but that the server
refuses. These four scripts close that gap for the two servers that run
rootless.

They are **not** unit tests and are not part of `pytest`: they need live
servers, so they are run deliberately and their output is recorded in
`.ai/measurement-2026-08-25/`.

## Bringing the servers up

```bash
apt-get install -y postgresql mysql-server        # PostgreSQL 16, MySQL 8
export PGDATA=/tmp/pgdata PGPORT=55432
su postgres -c "initdb -D $PGDATA -A trust -U postgres"
su postgres -c "pg_ctl -D $PGDATA -o '-p $PGPORT -k /tmp' -l /tmp/pg.log start"
mysqld --initialize-insecure --user=mysql --datadir=/tmp/mysqldata
mysqld --user=mysql --datadir=/tmp/mysqldata --socket=/tmp/mysqld/m.sock --port=33306 &
```

**Check `@@collation_server` before trusting any regex result.** The MySQL
default is `utf8mb4_0900_ai_ci`, which is case-INsensitive; that is the whole
condition `run_refusal_justification.py` exists to demonstrate. A server
configured with a case-sensitive collation would make the evidence pass for
the wrong reason.

## The scripts

| script | what it establishes |
| --- | --- |
| `run_regex_check_execution.py` | the counterfactual: a naive `REGEXP` emission is strictly weaker than the PostgreSQL source, and the engine's `REGEXP_LIKE(..., 'c')` is not |
| `run_regex_equivalence.py` | all 8 regex patterns in the corpus accept and reject the same strings on PostgreSQL and MySQL |
| `run_refusal_justification.py` | the two refusals this profile added are justified by real server behaviour, not by argument |
| `run_corpus_execution.py` | every admitted statement, emitted and really executed, applied in migration order |

## Two harness defects worth not repeating

Both produced a plausible, wrong number before being caught:

1. **One statement per rolled-back transaction.** A migration corpus is a
   sequence; every `ALTER` then failed with "table doesn't exist" and the run
   reported a false 31%. Statements are applied in order and committed.
2. **Multi-statement scripts.** `emit_alter_table` legitimately emits
   `ALTER ...;\nALTER ...` for a multi-action ALTER, and a driver executes one
   statement per call. The driver's refusal looked exactly like an engine
   syntax error.

Both would have been reported as engine defects. Split refusals into
`MISSING_OBJECT` (a cascade from partial coverage) and `EMISSION_DEFECT`
(the server rejected SQL this engine produced) before drawing any conclusion.

## What this cannot cover

Oracle and SQL Server have no free rootless local instance, so they stay
`EXECUTION_NOT_AVAILABLE` — **not** passing. Every claim about those two
targets rests on the syntax leg and on each vendor's documented grammar.
