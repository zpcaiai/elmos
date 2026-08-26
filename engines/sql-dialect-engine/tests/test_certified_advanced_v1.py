"""Typed coverage for the database-object and routine expansion routes.

These are deliberately small semantic cores.  A positive case proves that the
object survives parsing, typed IR, target emission and target syntax checks;
unsupported provider semantics remain explicit blockers.
"""

from __future__ import annotations

import pytest

from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect
from elmos_sql_dialect.parser import parse_create_table


class _CommentCatalog:
    def __init__(self, table_sql: str) -> None:
        table = parse_create_table(table_sql, Dialect.POSTGRES)
        self.columns = {(table.schema, table.name, column.name): column for column in table.columns}

    def column_of(self, table_schema: str | None, table: str, column: str):
        return self.columns.get((table_schema, table, column))


def test_namespace_map_preserves_qualified_table_and_reference_names() -> None:
    report = translate_ddl(
        "CREATE TABLE app.users (id INT PRIMARY KEY, org_id INT, "
        "FOREIGN KEY (org_id) REFERENCES app.orgs (id))",
        "postgres",
        "mysql",
        namespace_map={"app": "tenant"},
    )
    assert report["status"] == "PASSED", report
    assert "CREATE TABLE tenant.users" in report["emitted"]
    assert "REFERENCES tenant.orgs" in report["emitted"]


def test_qualified_names_without_a_mapping_fail_closed() -> None:
    report = translate_ddl("CREATE TABLE app.users (id INT)", "postgres", "mysql")
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_DDL_NAMESPACE_MAPPING_REQUIRED"


def test_comment_on_column_keeps_the_table_scope() -> None:
    report = translate_ddl(
        "COMMENT ON COLUMN app.users.id IS 'identifier'",
        "postgres",
        "oracle",
        statement_kind="COMMENT",
        namespace_map={"app": "tenant"},
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] == "COMMENT ON COLUMN tenant.users.id IS 'identifier'"


def test_mysql_table_comment_uses_alter_table_metadata_syntax() -> None:
    report = translate_ddl(
        "COMMENT ON TABLE app.users IS 'user table'",
        "postgres",
        "mysql",
        statement_kind="COMMENT",
        namespace_map={"app": "tenant"},
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] == "ALTER TABLE tenant.users COMMENT = 'user table'"


def test_mysql_column_comment_requires_a_complete_column_catalogue() -> None:
    report = translate_ddl(
        "COMMENT ON COLUMN users.id IS 'identifier'",
        "postgres",
        "mysql",
        statement_kind="COMMENT",
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_COMMENT_TARGET_COLUMN_TYPE_REQUIRED"


def test_mysql_column_comment_repeats_the_complete_catalogued_definition() -> None:
    report = translate_ddl(
        "COMMENT ON COLUMN users.id IS 'identifier'",
        "postgres",
        "mysql",
        statement_kind="COMMENT",
        comment_catalog=_CommentCatalog("CREATE TABLE users (id INT NOT NULL DEFAULT 0)"),
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] == "ALTER TABLE users MODIFY COLUMN id INT NOT NULL DEFAULT 0 COMMENT 'identifier'"


def test_mysql_column_comment_with_an_unseen_column_stays_fail_closed() -> None:
    report = translate_ddl(
        "COMMENT ON COLUMN users.missing IS 'identifier'",
        "postgres",
        "mysql",
        statement_kind="COMMENT",
        comment_catalog=_CommentCatalog("CREATE TABLE users (id INT NOT NULL DEFAULT 0)"),
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_COMMENT_TARGET_COLUMN_TYPE_REQUIRED"


@pytest.mark.parametrize(
    ("sql", "fragment"),
    [
        (
            "COMMENT ON TABLE users IS 'user table'",
            "@level1type = N'TABLE', @level1name = N'users'",
        ),
        (
            "COMMENT ON COLUMN users.id IS 'identifier'",
            "@level1type = N'TABLE', @level1name = N'users', @level2type = N'COLUMN', @level2name = N'id'",
        ),
    ],
)
def test_sql_server_comments_require_and_use_an_explicit_default_schema(sql: str, fragment: str) -> None:
    report = translate_ddl(
        sql,
        "postgres",
        "tsql",
        statement_kind="COMMENT",
        namespace_map={"": "dbo"},
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"].startswith("EXEC sys.sp_addextendedproperty")
    assert fragment in report["emitted"]
    assert "@level0name = N'dbo'" in report["emitted"]


def test_sql_server_comments_without_a_default_schema_remain_blocked() -> None:
    report = translate_ddl(
        "COMMENT ON TABLE users IS 'user table'",
        "postgres",
        "tsql",
        statement_kind="COMMENT",
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_COMMENT_TARGET_SCHEMA_REQUIRED"


def test_sql_server_comment_value_limit_is_fail_closed() -> None:
    value = "x" * 3751
    report = translate_ddl(
        f"COMMENT ON TABLE users IS '{value}'",
        "postgres",
        "tsql",
        statement_kind="COMMENT",
        namespace_map={"": "dbo"},
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_COMMENT_TARGET_VALUE_TOO_LARGE"


@pytest.mark.parametrize("kind", ["GRANT", "REVOKE"])
def test_table_privileges_are_typed_and_emitted(kind: str) -> None:
    direction = "TO" if kind == "GRANT" else "FROM"
    report = translate_ddl(
        f"{kind} SELECT, UPDATE ON TABLE users {direction} app_reader",
        "postgres",
        "mysql",
        statement_kind=kind,
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] == f"{kind} SELECT, UPDATE ON users {direction} app_reader"


def test_view_is_translated_as_a_typed_query_not_a_text_replacement() -> None:
    report = translate_ddl(
        "CREATE OR REPLACE VIEW app.adults AS SELECT id, name FROM app.users WHERE id > 18",
        "postgres",
        "mysql",
        statement_kind="VIEW",
        namespace_map={"app": "tenant"},
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] == (
        "CREATE OR REPLACE VIEW tenant.adults AS SELECT id, name FROM tenant.users WHERE id > 18"
    )


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_bounded_out_parameter_procedure_has_a_target_route(target: str) -> None:
    report = translate_ddl(
        "CREATE PROCEDURE increment(IN x INT, OUT y INT) LANGUAGE SQL "
        "AS $$ SET y = x + 1 $$",
        "postgres",
        target,
        statement_kind="PROCEDURE",
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] is not None
    assert "increment" in report["emitted"]


def test_table_function_has_an_explicit_tsql_route() -> None:
    report = translate_ddl(
        "CREATE FUNCTION active_users() RETURNS TABLE(id INT) LANGUAGE SQL "
        "AS $$ SELECT id FROM users WHERE id > 0 $$",
        "postgres",
        "tsql",
        statement_kind="FUNCTION",
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] == (
        "CREATE FUNCTION active_users() RETURNS TABLE AS RETURN "
        "(SELECT id FROM users WHERE id > 0)"
    )


def test_trigger_target_route_is_not_fabricated_for_mysql() -> None:
    report = translate_ddl(
        "CREATE TRIGGER audit_update BEFORE UPDATE ON users "
        "FOR EACH ROW EXECUTE FUNCTION audit_row()",
        "postgres",
        "mysql",
        statement_kind="TRIGGER",
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_ROUTINE_TRIGGER_TARGET_ROUTE_REQUIRED"


def test_json_array_and_binary_boundaries_are_explicit() -> None:
    json_report = translate_ddl("CREATE TABLE t (payload JSON)", "postgres", "mysql")
    assert json_report["status"] == "PASSED", json_report
    assert "payload JSON" in json_report["emitted"]

    jsonb_report = translate_ddl("CREATE TABLE t (payload JSONB)", "postgres", "mysql")
    assert jsonb_report["status"] == "BLOCKED", jsonb_report
    assert jsonb_report["reasonCode"] == "CERTIFIED_DDL_JSON_BINARY_SEMANTICS_UNSUPPORTED"

    array_report = translate_ddl("CREATE TABLE t (tags INT[])", "postgres", "mysql")
    assert array_report["status"] == "BLOCKED", array_report
    assert array_report["reasonCode"] == "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED"

    binary_report = translate_ddl("CREATE TABLE t (payload VARBINARY(32))", "mysql", "oracle")
    assert binary_report["status"] == "PASSED", binary_report
    assert "payload RAW(32)" in binary_report["emitted"]


def test_rls_is_an_explicit_blocker_and_never_a_permissive_policy() -> None:
    report = translate_ddl(
        "CREATE POLICY tenant_isolation ON users USING (tenant_id = 1)",
        "postgres",
        "mysql",
        statement_kind="POLICY",
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_RLS_TARGET_ROUTE_REQUIRED"


@pytest.mark.parametrize(
    "body",
    [
        "EXECUTE 'UPDATE users SET name = x'",
        "BEGIN; COMMIT",
    ],
)
def test_dynamic_sql_and_transaction_control_remain_fail_closed(body: str) -> None:
    report = translate_ddl(
        f"CREATE PROCEDURE unsafe(IN x INT, OUT y INT) LANGUAGE SQL AS $$ {body} $$",
        "postgres",
        "mysql",
        statement_kind="PROCEDURE",
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] in {
        "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
        "CERTIFIED_ROUTINE_UNSUPPORTED_LANGUAGE",
    }


def test_qualified_parser_model_retains_schema_for_direct_consumers() -> None:
    table = parse_create_table(
        "CREATE TABLE app.users (id INT)",
        Dialect.POSTGRES,
        namespace_map={"app": "tenant"},
    )
    assert table.schema == "tenant"
