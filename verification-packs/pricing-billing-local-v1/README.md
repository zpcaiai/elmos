# Pricing and billing local Batch 35 verification pack

This exact P0 pack binds the pinned pricing/billing source archive to a dependency-free local money-conservation harness. The bounded harness checks tenant- and currency-scoped ledger balance, allocation conservation, refund ceilings, idempotent-effect uniqueness, and invoice detail reconciliation using exact decimal strings.

Local engineering evidence currently consists of nine focused tests, including five stable seeded defect replays. Holdout, representative production workloads, providers, PostgreSQL, concurrency schedules, independent review, approvals, and production execution remain `NOT_RUN`. The pack is therefore `blocked` and `NOT_CERTIFIED`.

Run the bounded checks from the repository root:

```sh
cd engines/pricing-billing-engine
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_money_invariants.py
cd ../..
uv run --quiet --with jsonschema python scripts/batch35/validate_verification_pack.py verification-packs/pricing-billing-local-v1 --repository-root .
uv run --quiet --with jsonschema python scripts/batch35/run_verification_gate.py verification-packs/pricing-billing-local-v1
```

The gate is expected to pass structural evaluation while reporting certification readiness `BLOCKED` and decision `NOT_CERTIFIED`.
