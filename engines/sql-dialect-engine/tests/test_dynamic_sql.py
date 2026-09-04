from __future__ import annotations

import pytest

from elmos_sql_dialect.dynamic_sql import (
    extract_and_transpile_dynamic_sql,
    fold_constant_sql_expression,
)
from elmos_sql_dialect.models import Dialect, DialectError
import sqlglot


def test_dynamic_sql_literal_transpilation() -> None:
    stmt = "EXECUTE IMMEDIATE 'SELECT id, created_at FROM users WHERE active = 1';"
    # Transpile to T-SQL
    tsql_out = extract_and_transpile_dynamic_sql(stmt, Dialect.POSTGRES, Dialect.TSQL)
    assert "EXEC sp_executesql N'SELECT" in tsql_out
    assert "FROM users" in tsql_out

    # Transpile to MySQL
    mysql_out = extract_and_transpile_dynamic_sql(stmt, Dialect.POSTGRES, Dialect.MYSQL)
    assert "PREPARE stmt FROM @dyn_stmt;" in mysql_out
    assert "EXECUTE stmt;" in mysql_out


def test_dynamic_sql_constant_concatenation_folding() -> None:
    expr = sqlglot.parse_one("'SELECT ' || 'count(*) ' || 'FROM orders'", read="postgres")
    folded = fold_constant_sql_expression(expr)
    assert folded == "SELECT count(*) FROM orders"


def test_dynamic_sql_non_constant_fails_closed() -> None:
    expr = sqlglot.parse_one("'SELECT * FROM ' || user_table", read="postgres")
    with pytest.raises(DialectError) as exc:
        fold_constant_sql_expression(expr)
    assert exc.value.code == "CERTIFIED_DYNAMIC_SQL_UNSAFE"
