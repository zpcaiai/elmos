from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pytest

from elmos_spring_modernization import (
    SpringDatabaseStateComparator,
    DatabaseStateReport,
    TableDiffSummary,
    RowDiff,
    ColumnDiff,
)
from elmos_spring_modernization.cli import main as cli_main


def test_exact_match_verdict_pass() -> None:
    dataset = {
        "t_order": {
            "pk": ["id"],
            "baseline": [
                {"id": 101, "order_no": "ORD-001", "amount": 100.0, "status": "PAID"},
                {"id": 102, "order_no": "ORD-002", "amount": 250.5, "status": "PENDING"},
            ],
            "shadow": [
                {"id": 101, "order_no": "ORD-001", "amount": 100.0, "status": "PAID"},
                {"id": 102, "order_no": "ORD-002", "amount": 250.5, "status": "PENDING"},
            ],
        }
    }

    report = SpringDatabaseStateComparator.generate_report("prod_db", "shadow_db", dataset)

    assert report.verdict == "PASS"
    assert report.total_diffs == 0
    assert report.total_rows_compared == 2
    assert len(report.integrity_sha256) == 64
    assert report.table_summaries[0].matched_rows == 2
    assert report.table_summaries[0].diff_rows == 0


def test_precision_loss_and_scale_truncation() -> None:
    dataset = {
        "t_account": {
            "pk": ["account_id"],
            "baseline": [
                {"account_id": 1, "balance": "1000.5000", "interest_rate": "0.03541"},
            ],
            "shadow": [
                {"account_id": 1, "balance": "1000.50", "interest_rate": "0.035"},  # scale truncation & precision loss
            ],
        }
    }

    report = SpringDatabaseStateComparator.generate_report("prod_db", "shadow_db", dataset)

    assert report.verdict in ("FLAGGED_ANOMALIES", "FAIL_DATA_CORRUPTION")
    assert report.total_diffs == 1
    row_diff = report.row_diffs[0]
    kinds = {cd.diff_kind for cd in row_diff.column_diffs}
    assert "SCALE_TRUNCATION" in kinds
    assert "PRECISION_LOSS" in kinds


def test_timezone_shift_detection() -> None:
    dataset = {
        "t_audit_log": {
            "pk": ["log_id"],
            "baseline": [
                {"log_id": 1, "created_at": "2026-09-15T21:00:00+08:00"},
            ],
            "shadow": [
                {"log_id": 1, "created_at": "2026-09-15T13:00:00+00:00"},
            ],
        }
    }

    report = SpringDatabaseStateComparator.generate_report("prod_db", "shadow_db", dataset)

    assert report.total_diffs == 1
    col_diff = report.row_diffs[0].column_diffs[0]
    assert col_diff.diff_kind == "TIMEZONE_SHIFT"
    assert col_diff.severity == "MEDIUM"


def test_missing_and_extra_rows() -> None:
    dataset = {
        "t_payment": {
            "pk": ["pay_id"],
            "baseline": [
                {"pay_id": 1001, "amount": 50},
                {"pay_id": 1002, "amount": 80},
            ],
            "shadow": [
                {"pay_id": 1001, "amount": 50},
                {"pay_id": 1003, "amount": 90},  # 1002 is missing, 1003 is extra
            ],
        }
    }

    report = SpringDatabaseStateComparator.generate_report("prod_db", "shadow_db", dataset)

    assert report.verdict == "FAIL_DATA_CORRUPTION"
    statuses = {rd.status for rd in report.row_diffs}
    assert "MISSING_IN_SHADOW" in statuses
    assert "EXTRA_IN_SHADOW" in statuses


def test_nullability_mismatch() -> None:
    dataset = {
        "t_user": {
            "pk": ["user_id"],
            "baseline": [
                {"user_id": 5, "email": "user@example.com"},
            ],
            "shadow": [
                {"user_id": 5, "email": None},  # truncated to null
            ],
        }
    }

    report = SpringDatabaseStateComparator.generate_report("prod_db", "shadow_db", dataset)

    assert report.verdict == "FAIL_DATA_CORRUPTION"
    col_diff = report.row_diffs[0].column_diffs[0]
    assert col_diff.diff_kind == "NULLABILITY_MISMATCH"
    assert col_diff.severity == "CRITICAL"


def test_cli_compare_db(capsys: pytest.CaptureFixture[str]) -> None:
    sample_dataset = {
        "tables": {
            "t_customer": {
                "pk": ["id"],
                "baseline": [{"id": 1, "name": "Alice"}],
                "shadow": [{"id": 1, "name": "Alice"}],
            }
        }
    }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(sample_dataset, f)
        temp_path = f.name

    try:
        cli_main(["compare-db", "--baseline-db", temp_path])
        captured = capsys.readouterr()
        assert "database_state_report" in captured.out
        assert '"verdict": "PASS"' in captured.out
    finally:
        Path(temp_path).unlink(missing_ok=True)
