#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"


def main() -> int:
    text = "\n".join(p.read_text(encoding="utf-8") for p in sorted(SQL_DIR.glob("V*.sql")))
    normalized = re.sub(r"\s+", " ", text.lower())
    required = {
        "task table": "create table task (",
        "three-slot table": "create table account_task_slot (",
        "slot number check": "slot_no between 1 and 3",
        "slot claim": "function claim_account_task_slot",
        "slot renewal": "function renew_account_task_slot",
        "slot release": "function release_account_task_slot",
        "lease generation": "lease_generation bigint",
        "task run": "create table task_run (",
        "task node": "create table task_node (",
        "attempt": "create table task_node_attempt (",
        "event journal": "create table task_event (",
        "checkpoint": "create table task_checkpoint (",
        "side-effect receipt": "create table task_side_effect_receipt (",
        "input archive": "create table task_input (",
        "artifact archive": "create table task_artifact (",
        "usage ledger": "create table usage_event (",
        "price book": "create table price_book_item (",
        "revenue ledger": "create table revenue_entry (",
        "revenue allocation": "create table revenue_allocation (",
        "task financial summary": "create table task_financial_summary (",
        "transactional outbox": "create table outbox_event (",
        "consumer inbox dedup": "create table inbox_event_dedup (",
        "forced RLS": "force row level security",
        "tenant context": "current_setting('app.tenant_id'",
        "account context": "current_setting('app.account_id'",
    }
    errors = [f"missing {name}" for name, marker in required.items() if marker not in normalized]

    if re.search(r"select\s+count\s*\([^)]*\).*?insert", normalized, re.DOTALL):
        errors.append("possible count-then-insert admission implementation detected")
    if "where s.account_id = p_account_id" not in normalized or "for update skip locked" not in normalized:
        errors.append("slot claim must be account-scoped and use FOR UPDATE SKIP LOCKED")
    if "uq_task_submit_idempotency" not in normalized:
        errors.append("task submission idempotency constraint missing")
    if "uq_usage_idempotency" not in normalized or "uq_revenue_idempotency" not in normalized:
        errors.append("financial ledger idempotency constraints missing")

    # Lightweight delimiter checks catch common interrupted-generation errors.
    if text.count("$$") % 2:
        errors.append("unbalanced PostgreSQL dollar-quote delimiters")
    if text.count("(") != text.count(")"):
        errors.append("unbalanced SQL parentheses")

    if errors:
        print("SQL contract validation FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("SQL contract validation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
