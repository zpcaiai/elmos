# PL/SQL & T-SQL Conversion / Logic Decomposition

- **Skill ID:** `07-plsql-tsql-conversion`
- **Version:** `1.0.0`
- **Category:** core/conversion
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Convert stored procedures, functions, packages, triggers and jobs when the target can preserve semantics; otherwise decompose database logic into SQL, application services, event handlers or schedulers with traceable behavior contracts.

## Inputs

- Procedural IR/control-flow graph
- Source package/session/global state
- Target procedural capabilities
- Application architecture hooks
- Transaction and error contracts

## Required outputs

- Native target procedural code OR lift-to-app plan/code
- Call-site rewrite map
- State/transaction mapping
- Unsupported construct report
- Behavioral fixture suite

## Implementation modules / repository contract

- convert/proc/cfg.py
- convert/proc/plsql.py
- convert/proc/tsql.py
- convert/proc/strategy.py
- convert/proc/packages.py
- convert/proc/triggers.py
- convert/proc/dynamic_sql.py
- convert/proc/lift_to_app.py

## Interfaces and contracts

- Target adapter publishes procedural capability taxonomy
- Lift-to-app patches feed application adapters

## Workflow

1. Classify each unit: NATIVE, REWRITE, LIFT_TO_APP, EMULATE_WITH_APPROVAL or UNSUPPORTED.
2. Preserve parameter modes, default args, exceptions, cursor state and transaction boundaries.
3. Map package state/session state explicitly.
4. Rewrite dynamic SQL with bind preservation and injection controls.
5. Handle autonomous transactions, bulk operations, temp tables/table variables and trigger ordering explicitly.
6. When lifting, generate service/event/scheduler interfaces plus application call-site changes and compensating tests.
7. Retain source procedure signature adapters during strangler migration when needed.

## Mandatory tests

- Oracle package body/state
- Nested procedures
- REF CURSOR
- BULK COLLECT/FORALL
- PRAGMA autonomous_transaction
- DBMS_JOB/SCHEDULER
- DBMS_LOB/UTL packages
- T-SQL TRY/CATCH/XACT_STATE
- table variables/temp tables
- OUTPUT/identity retrieval
- trigger recursion/order
- dynamic EXEC/EXECUTE IMMEDIATE

## Required evidence

- Per-procedure strategy decision
- Compile result or generated app patch
- Call graph before/after
- Transaction behavior diff
- Side-effect/event diff

## Fail-closed / escalation rules

- Do not emulate unsupported transaction behavior without explicit approval.
- TiDB-like targets without stored-procedure support must default affected units to decomposition, not fake DDL.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
