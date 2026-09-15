"""Unit tests for KingbaseES (人大金仓) dialect lowerer."""

from __future__ import annotations

import pytest

from elmos_sql_dialect.chinadb import (
    KingbaseMode,
    lower_chinadb_sql,
    lower_kingbase_ddl,
    lower_kingbase_query,
    lower_kingbase_sequence,
    lower_kingbase_upsert,
    lower_to_kingbase,
    translate_to_kingbasees,
)


def test_kingbase_pg_mode_ddl_basic() -> None:
    source_sql = """
    CREATE TABLE users (
        id BIGSERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        bio TEXT,
        metadata JSONB,
        avatar BYTEA,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """
    lowered = lower_kingbase_ddl(source_sql, mode=KingbaseMode.PG)
    assert "BIGSERIAL" in lowered
    assert "BOOLEAN" in lowered
    assert "TEXT" in lowered
    assert "JSONB" in lowered
    assert "BYTEA" in lowered
    assert "PRIMARY KEY" in lowered


def test_kingbase_oracle_mode_ddl_types() -> None:
    source_sql = """
    CREATE TABLE orders (
        id SERIAL PRIMARY KEY,
        order_no VARCHAR(64) NOT NULL,
        amount DECIMAL(12, 2) NOT NULL,
        is_paid BOOLEAN DEFAULT FALSE,
        description TEXT,
        attachment BLOB,
        created_at DATETIME DEFAULT NOW()
    );
    """
    lowered = lower_kingbase_ddl(source_sql, mode=KingbaseMode.ORACLE)
    assert "NUMBER(10) IDENTITY(1, 1)" in lowered
    assert "NUMBER(1)" in lowered
    assert "CLOB" in lowered
    assert "BLOB" in lowered
    assert "VARCHAR2" in lowered


def test_kingbase_query_functions() -> None:
    # Test PG mode
    q_pg = "SELECT id, IFNULL(name, 'N/A'), NOW() FROM users LIMIT 10 OFFSET 5;"
    lowered_pg = lower_kingbase_query(q_pg, mode=KingbaseMode.PG)
    assert "COALESCE" in lowered_pg
    assert "CURRENT_TIMESTAMP" in lowered_pg or "NOW" in lowered_pg

    # Test Oracle mode
    q_ora = "SELECT id, IFNULL(name, 'N/A'), NOW() FROM users;"
    lowered_ora = lower_kingbase_query(q_ora, mode=KingbaseMode.ORACLE)
    assert "NVL" in lowered_ora
    assert "SYSDATE" in lowered_ora


def test_kingbase_sequence() -> None:
    seq_pg = "SELECT NEXTVAL('user_id_seq');"
    assert "user_id_seq" in lower_kingbase_sequence(seq_pg, mode=KingbaseMode.PG)

    seq_ora = "SELECT NEXTVAL('user_id_seq');"
    lowered_ora = lower_kingbase_sequence(seq_ora, mode=KingbaseMode.ORACLE)
    assert "user_id_seq.NEXTVAL" in lowered_ora


def test_kingbase_upsert() -> None:
    # PG mode ON CONFLICT
    upsert_pg = "INSERT INTO users (id, name) VALUES (1, 'alice') ON CONFLICT (id) DO UPDATE SET name = 'alice';"
    lowered_pg = lower_kingbase_upsert(upsert_pg, mode=KingbaseMode.PG)
    assert "ON CONFLICT" in lowered_pg

    # Oracle mode MERGE INTO
    insert_sql = "INSERT INTO users (id, name) VALUES (1, 'alice');"
    merge_ora = lower_kingbase_upsert(
        insert_sql,
        mode=KingbaseMode.ORACLE,
        target_table="users",
        conflict_keys=["id"],
        update_cols=["name"],
    )
    assert "MERGE INTO users" in merge_ora
    assert "WHEN MATCHED THEN UPDATE" in merge_ora
    assert "WHEN NOT MATCHED THEN INSERT" in merge_ora


def test_kingbase_chinadb_integration() -> None:
    ddl = "CREATE TABLE products (id BIGSERIAL PRIMARY KEY, details JSON);"
    res_ddl = lower_chinadb_sql(ddl, target_id="kingbasees", mode="PG")
    assert "BIGSERIAL" in res_ddl
    assert "JSONB" in res_ddl

    trans_res = translate_to_kingbasees(
        "CREATE TABLE accounts (id SERIAL PRIMARY KEY, note TEXT);",
        compatibility_mode="pg-compatible",
    )
    assert trans_res["status"] == "PASSED"
    assert trans_res["state"] == "LOCAL_EMITTED"
    assert "SERIAL" in trans_res["emitted"]
