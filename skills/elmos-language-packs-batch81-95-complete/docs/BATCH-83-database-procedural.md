# Batch 83: PL/SQL / T-SQL / PL/pgSQL / SQL PL Pack

Recovers and modernizes business logic embedded in stored procedures, packages, triggers, jobs, and database-specific programming languages.

## Skills

- PG247 `database-program-unit-discovery`
- PG248 `plsql-parser-and-semantic-model`
- PG249 `tsql-parser-and-semantic-model`
- PG250 `plpgsql-sqlpl-parser-and-semantic-model`
- PG251 `stored-procedure-business-rule-extractor`
- PG252 `trigger-job-dblink-impact-analyzer`
- PG253 `dynamic-sql-injection-safety-analyzer`
- PG254 `database-logic-retain-refactor-extract-decider`
- PG255 `procedure-to-service-generator`
- PG256 `database-code-test-harness-generator`
- PG257 `transaction-concurrency-equivalence-verifier`
- PG258 `database-program-modernization-certifier`

## Safety boundary

Logic must remain in the database when atomicity, data locality, or performance evidence requires it; extraction cannot be automatic dogma.

## Principal risks

- transaction semantic drift
- trigger side effects
- dynamic SQL injection
- cursor behavior mismatch
- isolation-level drift
- numeric/date conversion
