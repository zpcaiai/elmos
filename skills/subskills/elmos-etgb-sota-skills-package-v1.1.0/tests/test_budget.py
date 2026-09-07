from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from etgb.budget import BudgetExceeded, BudgetLedger, estimate_machine_eta


def test_usage_is_idempotent_and_reconciles(tmp_path: Path) -> None:
    ledger = BudgetLedger(tmp_path / "budget.json")
    ledger.reserve(run_id="r", tenant_id="t", owner_id="o", max_input_tokens=100,
                   max_output_tokens=100, max_credit_usd=1.0, max_wall_clock_ms=1000)
    first = ledger.consume(run_id="r", idempotency_key="evt-1", phase="build", input_tokens=10,
                           output_tokens=5, credit_usd=0.1, wall_clock_ms=100)
    second = ledger.consume(run_id="r", idempotency_key="evt-1", phase="build", input_tokens=99)
    assert first == second
    assert ledger.reconcile("r")["valid"]


def test_concurrent_duplicate_usage_is_counted_once(tmp_path: Path) -> None:
    ledger = BudgetLedger(tmp_path / "budget.json")
    ledger.reserve(run_id="r", tenant_id="t", owner_id="o", max_input_tokens=100,
                   max_output_tokens=100, max_credit_usd=1.0, max_wall_clock_ms=1000)
    def post(_: int) -> dict:
        return ledger.consume(run_id="r", idempotency_key="same", phase="x", input_tokens=1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(post, range(32)))
    assert ledger.reconcile("r")["recorded"]["input_tokens"] == 1


def test_budget_overrun_is_rejected_and_eta_is_machine_time(tmp_path: Path) -> None:
    ledger = BudgetLedger(tmp_path / "budget.json")
    ledger.reserve(run_id="r", tenant_id="t", owner_id="o", max_input_tokens=1,
                   max_output_tokens=1, max_credit_usd=0.01, max_wall_clock_ms=10)
    with pytest.raises(BudgetExceeded):
        ledger.consume(run_id="r", idempotency_key="evt", phase="x", input_tokens=2)
    eta = estimate_machine_eta(
        [{"id": "c1", "business_line": "sql-conversion", "coverage": {"capability_id": "x"}}],
        [{"case_id": "old", "business_line": "sql-conversion", "capability_id": "x", "status": "passed",
          "duration_ms": 1000, "cost": {"credit_usd": 0.1, "token_input": 10, "token_output": 5}}],
        concurrency=1, setup_overhead_ms=0,
    )
    assert eta["machine_eta_ms"]["p50"] == 1000
    assert "excluding human" in eta["note"]
