# Batch 04 Conformance Scenarios

Mission: Batch 4：跨语言语义映射、Transformation Rule DSL 与 Deterministic Recipe Engine

## B04-T001 - schema-valid (P0)

Expected: valid input and output conform to schemas

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B04-T002 - schema-invalid-unknown-field (P0)

Expected: trust boundary rejects unknown input fields

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B04-T003 - missing-upstream-certificate (P0)

Expected: execution is blocked

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B04-T004 - fake-certified-status (P0)

Expected: conservative gate rejects missing evidence

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B04-T005 - cross-tenant-access (P0)

Expected: request is denied and audited

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B04-T006 - agent-modifies-tests (P0)

Expected: proposal is rejected

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B04-T007 - provider-version-drift (P1)

Expected: certificate is invalidated

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B04-T008 - duplicate-event (P1)

Expected: idempotent processing produces one effect

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B04-T009 - runner-disconnect (P1)

Expected: lease expires into reconciliation

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B04-T010 - rollback-recovery (P1)

Expected: workspace and side effects reconcile

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B04-T011 - holdout-regression (P1)

Expected: release is blocked

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B04-T012 - evidence-expiry (P1)

Expected: status becomes stale and recertification starts

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.
