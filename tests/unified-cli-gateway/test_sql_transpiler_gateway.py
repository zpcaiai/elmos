"""Regression tests for the unified CLI's fail-closed SQL adapter."""

from __future__ import annotations

import io
import json
import sys
import unittest
from typing import Any

from elmos_cli.dispatcher import main
from elmos_sql_dialect.sql_transpiler_gateway import SqlTranspilerGateway, get_supported_dialects


_SOURCE_PROFILE = "oracle-26ai-ee"
_TARGET_PROFILE = "postgresql-18.4"


class TestSqlTranspilerGateway(unittest.TestCase):
    def test_dialect_catalog_does_not_claim_chinadb_renderers(self) -> None:
        dialects = get_supported_dialects()
        dialect_by_id = {item["id"]: item for item in dialects}
        self.assertEqual(dialect_by_id["oracle"]["translation_status"], "EXACT_PROFILE_REQUIRED")
        self.assertEqual(dialect_by_id["dm8"]["translation_status"], "SPEC_ONLY")
        self.assertEqual(dialect_by_id["goldendb"]["translation_status"], "SPEC_ONLY")

    def test_generic_dialect_request_fails_closed_without_target_sql(self) -> None:
        sql = "SELECT NVL(nickname, 'Anonymous'), SYSDATE FROM users WHERE ROWNUM <= 10"
        result = SqlTranspilerGateway().transpile(sql, "oracle", "postgres")
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.reason_code, "EXACT_PROFILE_REQUIRED")
        self.assertIsNone(result.target_sql)
        self.assertEqual(result.semantic_equivalence, "NOT_VERIFIED")
        self.assertNotIn("VERIFIED_SEMANTIC_EQUIVALENCE", repr(result))

    def test_standard_typed_entry_blocks_rownum_with_remaining_and_predicate(self) -> None:
        result = SqlTranspilerGateway().transpile(
            "SELECT id FROM users WHERE ROWNUM <= 10 AND active = 1",
            "oracle",
            "postgres",
            source_profile=_SOURCE_PROFILE,
            target_profile=_TARGET_PROFILE,
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.reason_code, "UNSUPPORTED_ORACLE_ROWNUM_SEMANTICS")
        self.assertIsNone(result.target_sql)
        self.assertEqual(result.verification["targetEmit"], "PASSED")
        self.assertEqual(result.verification["gatewaySemanticGuard"], "FAILED")
        self.assertEqual(result.semantic_equivalence, "NOT_VERIFIED")

    def test_standard_typed_entry_preserves_sysdate_string_literal(self) -> None:
        result = SqlTranspilerGateway().transpile(
            "SELECT 'SYSDATE' AS literal_value, SYSDATE AS now_value",
            "oracle",
            "postgres",
            source_profile=_SOURCE_PROFILE,
            target_profile=_TARGET_PROFILE,
        )
        self.assertEqual(result.status, "SYNTAX_READY")
        self.assertIsNotNone(result.target_sql)
        self.assertIn("'SYSDATE' AS literal_value", result.target_sql or "")
        self.assertIn("CURRENT_TIMESTAMP AS now_value", result.target_sql or "")
        self.assertEqual(result.semantic_equivalence, "NOT_VERIFIED")
        self.assertEqual(result.reason_code, "RUNTIME_EQUIVALENCE_NOT_RUN")
        self.assertEqual(result.verification["gatewaySemanticGuard"], "PASSED")
        self.assertEqual(result.verification["resultEquivalence"], "NOT_RUN")

    def test_standard_typed_entry_blocks_unclassified_function(self) -> None:
        result = SqlTranspilerGateway().transpile(
            "SELECT mystery_vendor_fn(value) FROM t",
            "oracle",
            "postgres",
            source_profile=_SOURCE_PROFILE,
            target_profile=_TARGET_PROFILE,
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.reason_code, "UNBOUND_FUNCTION_SEMANTICS")
        self.assertIsNone(result.target_sql)

    def test_standard_typed_entry_preserves_typed_engine_block(self) -> None:
        result = SqlTranspilerGateway().transpile(
            "SELECT /*+ INDEX(users idx_users) */ id FROM users",
            "oracle",
            "postgres",
            source_profile=_SOURCE_PROFILE,
            target_profile=_TARGET_PROFILE,
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.reason_code, "UNSUPPORTED_SEMANTICS")
        self.assertIsNone(result.target_sql)

    def test_catalog_only_chinadb_target_never_invokes_typed_renderer(self) -> None:
        called = False

        def typed_transpile(_request: Any) -> Any:
            nonlocal called
            called = True
            raise AssertionError("must not be called")

        gateway = SqlTranspilerGateway(
            typed_transpile=typed_transpile,
            request_factory=lambda **values: values,
        )
        result = gateway.transpile(
            "SELECT 1",
            "oracle",
            "dm8",
            source_profile=_SOURCE_PROFILE,
            target_profile="dm8-unbound",
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.reason_code, "EXACT_TARGET_ADAPTER_REQUIRED")
        self.assertIsNone(result.target_sql)
        self.assertFalse(called)

    def test_unknown_dialect_is_blocked(self) -> None:
        result = SqlTranspilerGateway().transpile(
            "SELECT 1",
            "unknown-database",
            "postgres",
            source_profile="unknown-1",
            target_profile=_TARGET_PROFILE,
        )
        self.assertEqual(result.reason_code, "UNSUPPORTED_DIALECT")
        self.assertIsNone(result.target_sql)

    def test_diff_schema_is_only_a_table_identity_check(self) -> None:
        result = SqlTranspilerGateway().diff_schemas(
            "CREATE TABLE users (id INT);",
            "CREATE TABLE orders (id INT);",
        )
        self.assertEqual(result["status"], "BREAKING_REMOVALS_DETECTED")
        self.assertEqual(result["semantic_equivalence"], "NOT_VERIFIED")
        self.assertEqual(result["added_tables"], ["orders"])
        self.assertEqual(result["removed_tables"], ["users"])

    def test_cli_blocked_result_has_nonzero_exit_and_null_target_sql(self) -> None:
        stdout = io.StringIO()
        original = sys.stdout
        sys.stdout = stdout
        try:
            exit_code = main(
                [
                    "sql",
                    "transpile",
                    "--src-dialect",
                    "oracle",
                    "--tgt-dialect",
                    "postgres",
                    "--sql",
                    "SELECT id FROM users WHERE ROWNUM <= 10 AND active = 1",
                    "--json",
                ]
            )
        finally:
            sys.stdout = original
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["reason_code"], "EXACT_PROFILE_REQUIRED")
        self.assertIsNone(payload["target_sql"])
        self.assertEqual(payload["semantic_equivalence"], "NOT_VERIFIED")

    def test_cli_exact_profiles_use_typed_engine_and_keep_not_verified_boundary(self) -> None:
        stdout = io.StringIO()
        original = sys.stdout
        sys.stdout = stdout
        try:
            exit_code = main(
                [
                    "sql",
                    "transpile",
                    "--src-dialect",
                    "oracle",
                    "--tgt-dialect",
                    "postgres",
                    "--src-profile",
                    _SOURCE_PROFILE,
                    "--tgt-profile",
                    _TARGET_PROFILE,
                    "--sql",
                    "SELECT 'SYSDATE' AS literal_value, SYSDATE AS now_value",
                    "--json",
                ]
            )
        finally:
            sys.stdout = original
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "SYNTAX_READY")
        self.assertEqual(payload["semantic_equivalence"], "NOT_VERIFIED")
        self.assertIn("'SYSDATE' AS literal_value", payload["target_sql"])
        self.assertEqual(payload["verification"]["resultEquivalence"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
