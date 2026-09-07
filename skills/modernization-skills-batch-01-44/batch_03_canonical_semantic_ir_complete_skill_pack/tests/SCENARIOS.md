# Batch 03 Conformance Scenarios

Mission: Batch 3：统一源码摄取、解析前端与 Canonical Semantic IR Foundation

## B03-T001 - schema-valid (P0)

Expected: valid input and output conform to schemas

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B03-T002 - schema-invalid-unknown-field (P0)

Expected: trust boundary rejects unknown input fields

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B03-T003 - missing-upstream-certificate (P0)

Expected: execution is blocked

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B03-T004 - fake-certified-status (P0)

Expected: conservative gate rejects missing evidence

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B03-T005 - cross-tenant-access (P0)

Expected: request is denied and audited

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B03-T006 - agent-modifies-tests (P0)

Expected: proposal is rejected

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B03-T007 - provider-version-drift (P1)

Expected: certificate is invalidated

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B03-T008 - duplicate-event (P1)

Expected: idempotent processing produces one effect

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B03-T009 - runner-disconnect (P1)

Expected: lease expires into reconciliation

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B03-T010 - rollback-recovery (P1)

Expected: workspace and side effects reconcile

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B03-T011 - holdout-regression (P1)

Expected: release is blocked

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.

## B03-T012 - evidence-expiry (P1)

Expected: status becomes stale and recertification starts

Executed by `tests/modernization-b01-44/test_batch_conformance.py`; the case fails if the runtime stops enforcing the rule.
