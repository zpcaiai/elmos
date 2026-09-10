"""Tests for ChinaDB Container Orchestrator, Protocol Lab, and DDL Executor across 13 domestic targets."""

from __future__ import annotations

import pytest

from elmos_sql_transpiler.chinadb_adapters import CHINADB_LOCAL_ADAPTERS
from elmos_sql_transpiler.chinadb_container_orchestrator import ChinaDbContainerOrchestrator
from elmos_sql_transpiler.chinadb_ddl_executor import ChinaDbDdlExecutor
from elmos_sql_transpiler.chinadb_protocol_lab import ChinaDbProtocolLab


def test_all_13_chinadb_targets_registered():
    lab = ChinaDbProtocolLab()
    assert len(lab.instances) == 13
    assert len(CHINADB_LOCAL_ADAPTERS) == 13

    expected_targets = {
        "dm8",
        "kingbasees",
        "opengauss",
        "tidb",
        "gbase-8s",
        "gbase-8c",
        "gbase-8a",
        "highgo-hgdb",
        "oceanbase-oracle",
        "oceanbase-mysql",
        "gaussdb-oracle",
        "gaussdb-m",
        "goldendb",
    }
    assert set(lab.instances.keys()) == expected_targets


def test_protocol_lab_basic_ddl_dml():
    lab = ChinaDbProtocolLab()
    target = "opengauss"

    # DDL
    lab.execute(target, "CREATE TABLE users (id VARCHAR(32) PRIMARY KEY, name VARCHAR(100), age INT);")
    lab.execute(target, "CREATE INDEX idx_users_name ON users (name);")

    # DML Insert
    _, _, aff1 = lab.execute(target, "INSERT INTO users (id, name, age) VALUES ('U1', 'Alice', 30);")
    _, _, aff2 = lab.execute(target, "INSERT INTO users (id, name, age) VALUES ('U2', 'Bob', 25);")
    assert aff1 == 1
    assert aff2 == 1

    # Query Select
    cols, rows, count = lab.execute(target, "SELECT id, name, age FROM users;")
    assert cols == ["id", "name", "age"]
    assert len(rows) == 2
    assert ("U1", "Alice", 30) in rows or ("U1", "Alice", "30") in rows

    # Update
    lab.execute(target, "UPDATE users SET age = 31 WHERE id = 'U1';")
    _, rows_updated, _ = lab.execute(target, "SELECT age FROM users WHERE id = 'U1';")
    assert rows_updated[0][0] in (31, "31")

    # Delete
    lab.execute(target, "DELETE FROM users WHERE id = 'U2';")
    cols, rows_del, _ = lab.execute(target, "SELECT * FROM users;")
    assert len(rows_del) == 1


def test_container_orchestrator_health_all_13_targets():
    orchestrator = ChinaDbContainerOrchestrator()
    for adapter in CHINADB_LOCAL_ADAPTERS:
        status = orchestrator.check_target_status(adapter.target_id)
        assert status.is_ready is True
        assert status.latency_ms >= 0.0
        assert status.mode in ("CONTAINER", "PROTOCOL_LAB")


def test_ddl_executor_and_reverse_introspection():
    orchestrator = ChinaDbContainerOrchestrator()
    executor = ChinaDbDdlExecutor(orchestrator)
    target = "oceanbase-oracle"

    ddl_statements = [
        "CREATE TABLE departments (dept_id VARCHAR(16) PRIMARY KEY, dept_name VARCHAR(100) NOT NULL);",
        "CREATE TABLE employees (emp_id VARCHAR(16) PRIMARY KEY, emp_name VARCHAR(100), dept_id VARCHAR(16), salary NUMERIC(12, 2));",
        "CREATE INDEX idx_emp_dept ON employees (dept_id);",
        "CREATE OR REPLACE PROCEDURE recalc_salaries(p_ratio NUMERIC) IS BEGIN UPDATE employees SET salary = salary * p_ratio; END;",
    ]

    receipt = executor.execute_ddl(target, ddl_statements)
    assert receipt.is_verified is True
    assert receipt.successful_statements == 4
    assert receipt.failed_statements == 0
    assert "departments" in receipt.verified_tables
    assert "employees" in receipt.verified_tables
    assert len(receipt.schema_digest) == 64

    # Reverse inspect table
    dept_inspect = executor.inspect_table(target, "departments")
    assert dept_inspect is not None
    assert "dept_id" in dept_inspect.columns
    assert dept_inspect.columns["dept_id"].is_primary_key is True

    emp_inspect = executor.inspect_table(target, "employees")
    assert emp_inspect is not None
    assert "idx_emp_dept" in emp_inspect.indexes
