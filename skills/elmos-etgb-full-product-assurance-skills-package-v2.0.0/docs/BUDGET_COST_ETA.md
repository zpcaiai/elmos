# Budget, cost and machine ETA

## Units

ETGB reports Elmos machine wall-clock, queue delay, input/output tokens, provider credits and optional compute/storage/network cost. Human effort is outside this estimator.

## Estimate

Use capability-level history when available, then business-line history, then an explicitly labeled fallback. Report p50/p90, sample count, fallback share and concurrency. Reforecast after each phase and monitor calibration.

## Reservation and ledger

Reserve maximum tokens, credits and wall-clock before admission. Usage events are idempotent by run/case/phase/revision. A duplicate provider callback cannot duplicate a charge. At close, reconcile event sum, run totals, provider records and released reservation.

## Thresholds

Warn at 70%, checkpoint/decision at 90%, and safe-stop at 100% unless a pre-approved overage policy exists. Validation/compensation can use a small explicit reserve so safety work is not abandoned.

## Reference

Use `etgb/budget.py`, `etgb eta`, PostgreSQL budget/usage tables and budget events.
