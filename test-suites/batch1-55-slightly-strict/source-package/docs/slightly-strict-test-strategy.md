# Slightly Strict Test Strategy

## Intent

This pack is stricter than a normal regression suite, but intentionally below a
full formal or regulatory certification regime.

## Required gates

- **PR gate:** affected P0/P1 unit, contract, security and migration tests.
- **Nightly gate:** property, fuzz, mutation, provider reconciliation, performance and chaos subsets.
- **Release gate:** representative workload, holdout, migration/rollback, security, performance, restore/DR and evidence certification.

## Thresholds

- P0: 100% pass.
- Critical P1: 100% pass or approved time-bounded waiver.
- Ordinary P1: at least 98% pass.
- Critical mutation score: at least 80%.
- Ordinary core mutation score: at least 70%.
- Critical property tests: at least 10,000 generated examples where applicable.
- P95 latency: no more than 10% regression unless approved.
- Flaky rate: below 1%; quarantine expires within seven days.
- Cross-tenant, secret leakage, unbalanced money, clinical safety, industrial safety,
  irreversible data loss and duplicate payment findings are non-waivable by default.

## Evidence

Every gate binds source snapshot, test-data digest, environment versions, commands,
raw output, findings, waivers and final decision.
