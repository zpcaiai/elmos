# Status Semantics

## Run status

`queued`, `running`, `paused`, `cancelling`, `cancelled`, `blocked`, `failed`, `completed-with-approved-exceptions`, `completed`.

## Gate status

`not-run`, `blocked`, `fail`, `waived`, `pass`.

Run completion does not imply every optional gate passed. A required `not-run`, `blocked`, or `fail` prevents a production readiness `pass`.

## Route maturity

`profile`, `parse`, `compile`, `contract-equivalent`, `validated-sample`, `repeatable-cohort`, `verified-workload`.
