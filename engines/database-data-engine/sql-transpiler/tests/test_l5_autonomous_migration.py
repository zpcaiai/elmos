"""Comprehensive test suite for L5 Autonomous Database Migration and Self-Healing Engine.

Validates zero-human-intervention (L5) migration lifecycle, self-healing diagnostics,
AST patch synthesis, sandbox verification, CDC stream replay, and concurrency stress.
"""

from __future__ import annotations

import pytest

from elmos_sql_transpiler.chinadb_cdc_engine import (
    CdcOpType,
    ChangeEvent,
    ChinaDbCdcEngine,
)
from elmos_sql_transpiler.chinadb_ddl_executor import (
    ChinaDbDdlExecutor,
    DdlExecutionReceipt,
)
from elmos_sql_transpiler.chinadb_stress_engine import (
    ChinaDbStressEngine,
    StressTestReceipt,
)
from elmos_sql_transpiler.l5_autonomous_migration_engine import (
    AutonomousDatabaseMigrationEngine,
    AutonomousMigrationConfig,
    AutonomousMigrationDossier,
    AutonomousMigrationStage,
    MigrationAsset,
    MigrationAssetKind,
    MigrationStatus,
)
from elmos_sql_transpiler.l5_self_healing_engine import (
    ERROR_PATTERNS,
    AstPatchKind,
    AstPatchProposal,
    AutonomousDatabaseSelfHealingEngine,
    AutonomousRepairReceipt,
    DiagnosticReport,
    ErrorCategory,
    ErrorPatternDefinition,
    PatchRiskLevel,
)


class TestErrorPatternsAndDiagnostics:
    """Test error pattern definitions, regex matching, and diagnostic report generation."""

    @pytest.fixture
    def engine(self) -> AutonomousDatabaseSelfHealingEngine:
        return AutonomousDatabaseSelfHealingEngine()

    def test_error_patterns_count(self) -> None:
        assert len(ERROR_PATTERNS) >= 30
        categories = {p.category for p in ERROR_PATTERNS}
        assert len(categories) >= 10
        for p in ERROR_PATTERNS:
            assert isinstance(p, ErrorPatternDefinition)
            assert isinstance(p.default_risk, PatchRiskLevel)

    def test_error_patterns_unique_ids(self) -> None:
        p_ids = [p.pattern_id for p in ERROR_PATTERNS]
        assert len(p_ids) == len(set(p_ids))

    def test_diagnostic_ora_00942(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-00942: table or view 'accounts' does not exist"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "ORA-00942"
        assert diag.category == ErrorCategory.MISSING_IDENTIFIER
        assert diag.target_engine == "oracle"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_ora_00942(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-00942: table or view 'accounts' does not exist"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_ora_00942(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-00942: table or view 'accounts' does not exist"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "oracle", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_ora_00904(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-00904: 'c_balance': invalid identifier"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "ORA-00904"
        assert diag.category == ErrorCategory.MISSING_IDENTIFIER
        assert diag.target_engine == "oracle"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_ora_00904(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-00904: 'c_balance': invalid identifier"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_ora_00904(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-00904: 'c_balance': invalid identifier"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "oracle", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_ora_01400(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-01400: cannot insert NULL into ('t_orders'.'order_amt')"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "ORA-01400"
        assert diag.category == ErrorCategory.NULLABILITY_RELAXATION
        assert diag.target_engine == "oracle"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_ora_01400(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-01400: cannot insert NULL into ('t_orders'.'order_amt')"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_ora_01400(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-01400: cannot insert NULL into ('t_orders'.'order_amt')"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "oracle", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_ora_01422(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-01422: exact fetch returns more than requested number of rows'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "ORA-01422"
        assert diag.category == ErrorCategory.AMBIGUOUS_COLUMN
        assert diag.target_engine == "oracle"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_ora_01422(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-01422: exact fetch returns more than requested number of rows'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_ora_01422(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-01422: exact fetch returns more than requested number of rows'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "oracle", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_ora_01438(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-01438: value larger than specified precision allowed for this column'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "ORA-01438"
        assert diag.category == ErrorCategory.NUMERIC_PRECISION_TRUNCATION
        assert diag.target_engine == "oracle"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_ora_01438(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-01438: value larger than specified precision allowed for this column'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_ora_01438(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-01438: value larger than specified precision allowed for this column'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "oracle", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_ora_01722(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-01722: invalid number in expression'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "ORA-01722"
        assert diag.category == ErrorCategory.TYPE_MISMATCH
        assert diag.target_engine == "oracle"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_ora_01722(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-01722: invalid number in expression'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_ora_01722(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-01722: invalid number in expression'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "oracle", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_ora_02291(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-02291: integrity constraint violated - parent key not found'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "ORA-02291"
        assert diag.category == ErrorCategory.CONSTRAINT_VIOLATION
        assert diag.target_engine == "oracle"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_ora_02291(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-02291: integrity constraint violated - parent key not found'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_ora_02291(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-02291: integrity constraint violated - parent key not found'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "oracle", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_ora_04091(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-04091: table 'journal' is mutating, trigger/function may not see it"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "ORA-04091"
        assert diag.category == ErrorCategory.TRIGGER_MUTATION
        assert diag.target_engine == "oracle"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_ora_04091(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-04091: table 'journal' is mutating, trigger/function may not see it"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_ora_04091(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-04091: table 'journal' is mutating, trigger/function may not see it"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "oracle", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_ora_06502(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-06502: numeric or value error: character string buffer too small'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "ORA-06502"
        assert diag.category == ErrorCategory.STRING_DATA_TRUNCATION
        assert diag.target_engine == "oracle"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_ora_06502(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-06502: numeric or value error: character string buffer too small'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_ora_06502(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ORA-06502: numeric or value error: character string buffer too small'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "oracle", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_ora_08177(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-08177: can't serialize access for this transaction"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "ORA-08177"
        assert diag.category == ErrorCategory.ISOLATION_CONCURRENCY_CONFLICT
        assert diag.target_engine == "oracle"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_ora_08177(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-08177: can't serialize access for this transaction"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "oracle")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_ora_08177(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "ORA-08177: can't serialize access for this transaction"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "oracle", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_mssql_207(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Msg 207, Level 16: Invalid column name 'cust_code'."
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MSSQL-207"
        assert diag.category == ErrorCategory.MISSING_IDENTIFIER
        assert diag.target_engine == "sqlserver"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_mssql_207(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Msg 207, Level 16: Invalid column name 'cust_code'."
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_mssql_207(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Msg 207, Level 16: Invalid column name 'cust_code'."
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "sqlserver", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_mssql_208(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Msg 208, Level 16: Invalid object name 'orders_archive'."
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MSSQL-208"
        assert diag.category == ErrorCategory.MISSING_IDENTIFIER
        assert diag.target_engine == "sqlserver"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_mssql_208(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Msg 208, Level 16: Invalid object name 'orders_archive'."
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_mssql_208(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Msg 208, Level 16: Invalid object name 'orders_archive'."
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "sqlserver", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_mssql_245(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Msg 245, Level 16: Conversion failed when con'
            "verting the varchar value 'abc' to data type "
            'int.'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MSSQL-245"
        assert diag.category == ErrorCategory.TYPE_MISMATCH
        assert diag.target_engine == "sqlserver"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_mssql_245(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Msg 245, Level 16: Conversion failed when con'
            "verting the varchar value 'abc' to data type "
            'int.'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_mssql_245(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Msg 245, Level 16: Conversion failed when con'
            "verting the varchar value 'abc' to data type "
            'int.'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "sqlserver", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_mssql_515(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Msg 515, Level 16: Cannot insert the value NULL into column 'created_by'."
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MSSQL-515"
        assert diag.category == ErrorCategory.NULLABILITY_RELAXATION
        assert diag.target_engine == "sqlserver"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_mssql_515(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Msg 515, Level 16: Cannot insert the value NULL into column 'created_by'."
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_mssql_515(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Msg 515, Level 16: Cannot insert the value NULL into column 'created_by'."
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "sqlserver", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_mssql_547(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Msg 547, Level 16: The INSERT statement confl'
            'icted with the FOREIGN KEY constraint.'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MSSQL-547"
        assert diag.category == ErrorCategory.CONSTRAINT_VIOLATION
        assert diag.target_engine == "sqlserver"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_mssql_547(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Msg 547, Level 16: The INSERT statement confl'
            'icted with the FOREIGN KEY constraint.'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_mssql_547(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Msg 547, Level 16: The INSERT statement confl'
            'icted with the FOREIGN KEY constraint.'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "sqlserver", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_mssql_1205(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'Msg 1205, Level 13: Transaction was deadlocked on lock resources.'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MSSQL-1205"
        assert diag.category == ErrorCategory.DEADLOCK_ANOMALY
        assert diag.target_engine == "sqlserver"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_mssql_1205(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'Msg 1205, Level 13: Transaction was deadlocked on lock resources.'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "sqlserver")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_mssql_1205(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'Msg 1205, Level 13: Transaction was deadlocked on lock resources.'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "sqlserver", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_pg_42p01(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 42P01: relation "customer_profile" does not exist'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "PG-42P01"
        assert diag.category == ErrorCategory.MISSING_IDENTIFIER
        assert diag.target_engine == "postgres"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_pg_42p01(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 42P01: relation "customer_profile" does not exist'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_pg_42p01(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 42P01: relation "customer_profile" does not exist'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "postgres", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_pg_42703(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 42703: column "created_date" does not exist'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "PG-42703"
        assert diag.category == ErrorCategory.MISSING_IDENTIFIER
        assert diag.target_engine == "postgres"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_pg_42703(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 42703: column "created_date" does not exist'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_pg_42703(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 42703: column "created_date" does not exist'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "postgres", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_pg_42804(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 42804: datatype mismatch, cannot cast type text to integer'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "PG-42804"
        assert diag.category == ErrorCategory.TYPE_MISMATCH
        assert diag.target_engine == "postgres"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_pg_42804(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 42804: datatype mismatch, cannot cast type text to integer'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_pg_42804(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 42804: datatype mismatch, cannot cast type text to integer'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "postgres", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_pg_23505(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 23505: duplicate key value violates unique constraint "pk_account"'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "PG-23505"
        assert diag.category == ErrorCategory.CONSTRAINT_VIOLATION
        assert diag.target_engine == "postgres"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_pg_23505(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 23505: duplicate key value violates unique constraint "pk_account"'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_pg_23505(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 23505: duplicate key value violates unique constraint "pk_account"'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "postgres", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_pg_23503(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'ERROR: 23503: insert or update on table "orde'
            'rs" violates foreign key constraint'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "PG-23503"
        assert diag.category == ErrorCategory.CONSTRAINT_VIOLATION
        assert diag.target_engine == "postgres"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_pg_23503(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'ERROR: 23503: insert or update on table "orde'
            'rs" violates foreign key constraint'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_pg_23503(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'ERROR: 23503: insert or update on table "orde'
            'rs" violates foreign key constraint'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "postgres", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_pg_23502(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 23502: null value in column "amount" violates not-null constraint'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "PG-23502"
        assert diag.category == ErrorCategory.NULLABILITY_RELAXATION
        assert diag.target_engine == "postgres"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_pg_23502(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 23502: null value in column "amount" violates not-null constraint'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "postgres")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_pg_23502(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'ERROR: 23502: null value in column "amount" violates not-null constraint'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "postgres", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_my_1064(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1064: You have an error in your SQL syntax near 'ORDER BY' at line 1"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MY-1064"
        assert diag.category == ErrorCategory.SYNTAX_ERROR
        assert diag.target_engine == "mysql"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_my_1064(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1064: You have an error in your SQL syntax near 'ORDER BY' at line 1"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_my_1064(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1064: You have an error in your SQL syntax near 'ORDER BY' at line 1"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "mysql", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_my_1054(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1054: Unknown column 'item_sku' in 'field list'"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MY-1054"
        assert diag.category == ErrorCategory.MISSING_IDENTIFIER
        assert diag.target_engine == "mysql"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_my_1054(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1054: Unknown column 'item_sku' in 'field list'"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_my_1054(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1054: Unknown column 'item_sku' in 'field list'"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "mysql", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_my_1146(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1146: Table 'dev.inventory_lot' doesn't exist"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MY-1146"
        assert diag.category == ErrorCategory.MISSING_IDENTIFIER
        assert diag.target_engine == "mysql"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_my_1146(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1146: Table 'dev.inventory_lot' doesn't exist"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_my_1146(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1146: Table 'dev.inventory_lot' doesn't exist"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "mysql", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_my_1213(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Error 1213: Deadlock found when trying to get'
            ' lock; try restarting transaction'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MY-1213"
        assert diag.category == ErrorCategory.DEADLOCK_ANOMALY
        assert diag.target_engine == "mysql"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_my_1213(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Error 1213: Deadlock found when trying to get'
            ' lock; try restarting transaction'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_my_1213(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Error 1213: Deadlock found when trying to get'
            ' lock; try restarting transaction'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "mysql", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_my_1364(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1364: Field 'status' doesn't have a default value"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MY-1364"
        assert diag.category == ErrorCategory.NULLABILITY_RELAXATION
        assert diag.target_engine == "mysql"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_my_1364(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1364: Field 'status' doesn't have a default value"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_my_1364(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1364: Field 'status' doesn't have a default value"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "mysql", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_my_1406(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1406: Data too long for column 'description' at row 1"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MY-1406"
        assert diag.category == ErrorCategory.STRING_DATA_TRUNCATION
        assert diag.target_engine == "mysql"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_my_1406(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1406: Data too long for column 'description' at row 1"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_my_1406(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Error 1406: Data too long for column 'description' at row 1"
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "mysql", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_my_1452(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Error 1452: Cannot add or update a child row:'
            ' a foreign key constraint fails'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "MY-1452"
        assert diag.category == ErrorCategory.CONSTRAINT_VIOLATION
        assert diag.target_engine == "mysql"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_my_1452(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Error 1452: Cannot add or update a child row:'
            ' a foreign key constraint fails'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "mysql")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_my_1452(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = (
            'Error 1452: Cannot add or update a child row:'
            ' a foreign key constraint fails'
        )
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "mysql", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_dm_2106(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '-2106: 无效的列名[trans_seq]'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "dm8")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "DM-2106"
        assert diag.category == ErrorCategory.MISSING_IDENTIFIER
        assert diag.target_engine == "dm8"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_dm_2106(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '-2106: 无效的列名[trans_seq]'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "dm8")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_dm_2106(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '-2106: 无效的列名[trans_seq]'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "dm8", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_dm_7033(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '-7033: 动态SQL绑定参数类型错误'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "dm8")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "DM-7033"
        assert diag.category == ErrorCategory.DYNAMIC_SQL_BIND
        assert diag.target_engine == "dm8"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_dm_7033(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '-7033: 动态SQL绑定参数类型错误'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "dm8")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_dm_7033(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '-7033: 动态SQL绑定参数类型错误'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "dm8", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_kb_42703(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '42703: KingbaseES: 字段不存在: sys_status'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "kingbasees")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "KB-42703"
        assert diag.category == ErrorCategory.MISSING_IDENTIFIER
        assert diag.target_engine == "kingbasees"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_kb_42703(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '42703: KingbaseES: 字段不存在: sys_status'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "kingbasees")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_kb_42703(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '42703: KingbaseES: 字段不存在: sys_status'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "kingbasees", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_og_42883(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '42883: function nvl(numeric, integer) does not exist'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "opengauss")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "OG-42883"
        assert diag.category == ErrorCategory.UNRESOLVED_ROUTINE
        assert diag.target_engine == "opengauss"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_og_42883(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '42883: function nvl(numeric, integer) does not exist'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "opengauss")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_og_42883(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = '42883: function nvl(numeric, integer) does not exist'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "opengauss", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_gbase_spl(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'GBase 8s SPL syntax error in procedure body'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "gbase-8s")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "GBASE-SPL"
        assert diag.category == ErrorCategory.SYNTAX_ERROR
        assert diag.target_engine == "gbase-8s"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_gbase_spl(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'GBase 8s SPL syntax error in procedure body'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "gbase-8s")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_gbase_spl(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'GBase 8s SPL syntax error in procedure body'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "gbase-8s", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_golden_shard(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'GoldenDB: partition key must be included in primary key'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "goldendb")
        assert isinstance(diag, DiagnosticReport)
        assert diag.matched_pattern_id == "GOLDEN-SHARD"
        assert diag.category == ErrorCategory.PARTITION_ALIGNMENT
        assert diag.target_engine == "goldendb"
        assert diag.confidence_score >= 0.90
        assert len(diag.failure_id) > 0

    def test_synthesize_for_golden_shard(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'GoldenDB: partition key must be included in primary key'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        diag = engine.diagnose_failure(raw_err, sql_sample, "goldendb")
        proposals = engine.synthesize_ast_patch(diag, sql_sample)
        assert len(proposals) >= 1
        top = proposals[0]
        assert isinstance(top, AstPatchProposal)
        assert len(top.patched_sql) > 0
        assert top.confidence_score >= 0.80

    def test_heal_and_verify_golden_shard(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = 'GoldenDB: partition key must be included in primary key'
        sql_sample = "SELECT * FROM test_tbl WHERE val = 1;"
        def sandbox_check(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            sql_sample, raw_err, "goldendb", sandbox_check
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert isinstance(receipt, AutonomousRepairReceipt)
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_diagnostic_generic_fallback(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        raw_err = "Completely unclassified dialect failure 99999"
        diag = engine.diagnose_failure(raw_err, "SELECT 1;", "dm8")
        assert diag.matched_pattern_id == "GENERIC_DIALECT_FALLBACK"
        assert diag.category == ErrorCategory.SYNTAX_ERROR
        assert diag.confidence_score > 0.80

class TestAstPatchSynthesisStrategies:
    """Test AST patch synthesis strategies and patch proposal ranking."""

    @pytest.fixture
    def engine(self) -> AutonomousDatabaseSelfHealingEngine:
        return AutonomousDatabaseSelfHealingEngine()

    def test_identifier_escaping_oracle_dm8(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        sql = "SELECT order, user, group FROM tab;"
        diag = engine.diagnose_failure("ORA-00904: invalid identifier 'order'", sql, "dm8")
        proposals = engine.synthesize_ast_patch(diag, sql)
        assert len(proposals) > 0
        p = proposals[0]
        assert p.patch_kind == AstPatchKind.IDENTIFIER_ESCAPE
        assert len(p.patched_sql) > 0

    def test_identifier_escaping_mysql_tidb(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        sql = "SELECT order, key, value FROM configs;"
        diag = engine.diagnose_failure("Error 1064: syntax error near 'order'", sql, "tidb")
        proposals = engine.synthesize_ast_patch(diag, sql)
        assert len(proposals) > 0
        p = proposals[0]
        assert p.patch_kind == AstPatchKind.IDENTIFIER_ESCAPE
        assert len(p.patched_sql) > 0

    def test_explicit_cast_synthesis(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        sql = "SELECT * FROM accounts WHERE balance = '1000.50';"
        diag = engine.diagnose_failure("ORA-01722: invalid number", sql, "dm8")
        proposals = engine.synthesize_ast_patch(diag, sql)
        assert len(proposals) > 0
        p = proposals[0]
        assert p.patch_kind == AstPatchKind.EXPLICIT_TYPE_CAST
        assert len(p.patched_sql) > 0

    def test_null_coalesce_guard_synthesis(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        sql = "INSERT INTO records (id, amt) VALUES (1, NULL);"
        diag = engine.diagnose_failure("ORA-01400: cannot insert NULL into ('amt')", sql, "dm8")
        proposals = engine.synthesize_ast_patch(diag, sql)
        assert len(proposals) > 0
        p = proposals[0]
        assert p.patch_kind == AstPatchKind.NULL_COALESCE_GUARD
        assert len(p.patched_sql) > 0

    def test_routine_shim_synthesis(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        sql = "SELECT NVL(col1, 0) FROM my_table;"
        diag = engine.diagnose_failure("42883: function nvl does not exist", sql, "opengauss")
        proposals = engine.synthesize_ast_patch(diag, sql)
        assert len(proposals) > 0
        p = proposals[0]
        assert p.patch_kind == AstPatchKind.ROUTINE_SHIM_INJECTION
        assert len(p.patched_sql) > 0

    def test_upsert_conflict_rewrite_synthesis(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        sql = "INSERT INTO counters (id, cnt) VALUES (1, 1);"
        diag = engine.diagnose_failure(
            "23505: duplicate key violates unique constraint", sql, "opengauss"
        )
        proposals = engine.synthesize_ast_patch(diag, sql)
        assert len(proposals) > 0
        p = proposals[0]
        assert p.patch_kind == AstPatchKind.UPSERT_CONFLICT_REWRITE
        assert len(p.patched_sql) > 0

    def test_fallback_generic_sanitization(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        sql = "SELECT something FROM somewhere;"
        diag = engine.diagnose_failure("Unrecognized obscure database glitch", sql, "highgo")
        proposals = engine.synthesize_ast_patch(diag, sql)
        assert len(proposals) >= 1
        p = proposals[0]
        assert p.confidence_score >= 0.85

class TestSandboxVerificationLoop:
    """Test autonomous repair and sandbox verification cycle."""

    @pytest.fixture
    def engine(self) -> AutonomousDatabaseSelfHealingEngine:
        return AutonomousDatabaseSelfHealingEngine()

    def test_successful_repair_single_attempt(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        failing_sql = "SELECT order, user FROM tbl;"
        raw_err = "ORA-00904: invalid identifier 'order'"
        def validator(s: str) -> tuple[bool, str]:
            if '"ORDER"' in s or '"order"' in s or "`order`" in s:
                return (True, "")
            return (False, "Still invalid identifier")
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            failing_sql, raw_err, "dm8", sandbox_verifier=validator
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert receipt.verification_passed is True
        assert receipt.zero_human_intervention is True

    def test_repair_fallback_aggressive_patch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        failing_sql = "SELECT * FROM t WHERE val = 1;"
        raw_err = "Obscure unrecognized parser error"
        calls = 0
        def selective_validator(s: str) -> tuple[bool, str]:
            nonlocal calls
            calls += 1
            if calls >= 2:
                return (True, "")
            return (False, "Rejected first attempt")
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            failing_sql, raw_err, "dm8", sandbox_verifier=selective_validator
        )
        assert ok is True
        assert len(rep_sql) > 0
        assert receipt.zero_human_intervention is True

    def test_repair_failure_fails_closed_zero_human(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        failing_sql = "TOTAL MALFORMED JUNK ;;;;"
        raw_err = "Completely fatal error"
        def reject_all(s: str) -> tuple[bool, str]:
            return (False, "Never valid")
        ok, rep_sql, receipt = engine.autonomous_repair_and_verify(
            failing_sql, raw_err, "dm8", sandbox_verifier=reject_all
        )
        assert ok is False
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is False

class TestMultiEngineRepairMatrix:
    """Test autonomous repair matrix across all 13 domestic database engines."""

    @pytest.fixture
    def engine(self) -> AutonomousDatabaseSelfHealingEngine:
        return AutonomousDatabaseSelfHealingEngine()

    def test_repair_dm8_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify Dameng 8 (DM8) self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "dm8")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "dm8", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "dm8"

    def test_repair_dm8_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify Dameng 8 (DM8) self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "dm8")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "dm8", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "dm8"

    def test_repair_dm8_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify Dameng 8 (DM8) self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "dm8")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "dm8", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "dm8"

    def test_repair_dm8_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify Dameng 8 (DM8) self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "dm8")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "dm8", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "dm8"

    def test_repair_dm8_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify Dameng 8 (DM8) self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "dm8")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "dm8", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "dm8"

    def test_repair_dm8_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify Dameng 8 (DM8) self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "dm8")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "dm8", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "dm8"

    def test_repair_dm8_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify Dameng 8 (DM8) self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "dm8")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "dm8", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "dm8"

    def test_repair_kingbase_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify KingbaseES (V8/V9) self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "kingbase")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "kingbase", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "kingbase"

    def test_repair_kingbase_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify KingbaseES (V8/V9) self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "kingbase")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "kingbase", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "kingbase"

    def test_repair_kingbase_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify KingbaseES (V8/V9) self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "kingbase")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "kingbase", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "kingbase"

    def test_repair_kingbase_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify KingbaseES (V8/V9) self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "kingbase")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "kingbase", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "kingbase"

    def test_repair_kingbase_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify KingbaseES (V8/V9) self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "kingbase")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "kingbase", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "kingbase"

    def test_repair_kingbase_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify KingbaseES (V8/V9) self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "kingbase")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "kingbase", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "kingbase"

    def test_repair_kingbase_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify KingbaseES (V8/V9) self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "kingbase")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "kingbase", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "kingbase"

    def test_repair_opengauss_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify openGauss / MogDB self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "opengauss")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "opengauss", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "opengauss"

    def test_repair_opengauss_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify openGauss / MogDB self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "opengauss")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "opengauss", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "opengauss"

    def test_repair_opengauss_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify openGauss / MogDB self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "opengauss")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "opengauss", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "opengauss"

    def test_repair_opengauss_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify openGauss / MogDB self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "opengauss")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "opengauss", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "opengauss"

    def test_repair_opengauss_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify openGauss / MogDB self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "opengauss")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "opengauss", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "opengauss"

    def test_repair_opengauss_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify openGauss / MogDB self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "opengauss")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "opengauss", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "opengauss"

    def test_repair_opengauss_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify openGauss / MogDB self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "opengauss")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "opengauss", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "opengauss"

    def test_repair_tidb_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify TiDB (v6/v7) self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "tidb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "tidb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "tidb"

    def test_repair_tidb_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify TiDB (v6/v7) self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "tidb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "tidb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "tidb"

    def test_repair_tidb_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify TiDB (v6/v7) self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "tidb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "tidb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "tidb"

    def test_repair_tidb_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify TiDB (v6/v7) self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "tidb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "tidb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "tidb"

    def test_repair_tidb_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify TiDB (v6/v7) self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "tidb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "tidb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "tidb"

    def test_repair_tidb_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify TiDB (v6/v7) self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "tidb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "tidb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "tidb"

    def test_repair_tidb_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify TiDB (v6/v7) self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "tidb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "tidb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "tidb"

    def test_repair_gbase8s_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8s (Informix-based) self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "gbase8s")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8s", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8s"

    def test_repair_gbase8s_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8s (Informix-based) self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8s")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8s", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8s"

    def test_repair_gbase8s_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8s (Informix-based) self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8s")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8s", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8s"

    def test_repair_gbase8s_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8s (Informix-based) self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8s")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8s", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8s"

    def test_repair_gbase8s_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8s (Informix-based) self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8s")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8s", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8s"

    def test_repair_gbase8s_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8s (Informix-based) self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8s")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8s", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8s"

    def test_repair_gbase8s_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8s (Informix-based) self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8s")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8s", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8s"

    def test_repair_gbase8c_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8c (Distributed openGauss) self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "gbase8c")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8c", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8c"

    def test_repair_gbase8c_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8c (Distributed openGauss) self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8c")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8c", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8c"

    def test_repair_gbase8c_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8c (Distributed openGauss) self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8c")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8c", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8c"

    def test_repair_gbase8c_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8c (Distributed openGauss) self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8c")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8c", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8c"

    def test_repair_gbase8c_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8c (Distributed openGauss) self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8c")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8c", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8c"

    def test_repair_gbase8c_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8c (Distributed openGauss) self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8c")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8c", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8c"

    def test_repair_gbase8c_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8c (Distributed openGauss) self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8c")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8c", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8c"

    def test_repair_gbase8a_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8a (MPP Columnar) self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "gbase8a")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8a", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8a"

    def test_repair_gbase8a_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8a (MPP Columnar) self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8a")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8a", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8a"

    def test_repair_gbase8a_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8a (MPP Columnar) self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8a")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8a", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8a"

    def test_repair_gbase8a_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8a (MPP Columnar) self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8a")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8a", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8a"

    def test_repair_gbase8a_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8a (MPP Columnar) self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8a")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8a", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8a"

    def test_repair_gbase8a_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8a (MPP Columnar) self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8a")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8a", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8a"

    def test_repair_gbase8a_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GBase 8a (MPP Columnar) self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "gbase8a")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gbase8a", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gbase8a"

    def test_repair_highgo_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify HighGo DB (HGDB) self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "highgo")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "highgo", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "highgo"

    def test_repair_highgo_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify HighGo DB (HGDB) self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "highgo")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "highgo", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "highgo"

    def test_repair_highgo_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify HighGo DB (HGDB) self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "highgo")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "highgo", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "highgo"

    def test_repair_highgo_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify HighGo DB (HGDB) self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "highgo")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "highgo", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "highgo"

    def test_repair_highgo_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify HighGo DB (HGDB) self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "highgo")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "highgo", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "highgo"

    def test_repair_highgo_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify HighGo DB (HGDB) self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "highgo")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "highgo", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "highgo"

    def test_repair_highgo_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify HighGo DB (HGDB) self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "highgo")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "highgo", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "highgo"

    def test_repair_oceanbase_oracle_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (Oracle Mode) self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_oracle"

    def test_repair_oceanbase_oracle_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (Oracle Mode) self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_oracle"

    def test_repair_oceanbase_oracle_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (Oracle Mode) self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_oracle"

    def test_repair_oceanbase_oracle_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (Oracle Mode) self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_oracle"

    def test_repair_oceanbase_oracle_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (Oracle Mode) self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_oracle"

    def test_repair_oceanbase_oracle_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (Oracle Mode) self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_oracle"

    def test_repair_oceanbase_oracle_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (Oracle Mode) self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_oracle"

    def test_repair_oceanbase_mysql_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (MySQL Mode) self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_mysql"

    def test_repair_oceanbase_mysql_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (MySQL Mode) self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_mysql"

    def test_repair_oceanbase_mysql_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (MySQL Mode) self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_mysql"

    def test_repair_oceanbase_mysql_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (MySQL Mode) self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_mysql"

    def test_repair_oceanbase_mysql_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (MySQL Mode) self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_mysql"

    def test_repair_oceanbase_mysql_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (MySQL Mode) self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_mysql"

    def test_repair_oceanbase_mysql_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify OceanBase (MySQL Mode) self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "oceanbase_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "oceanbase_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "oceanbase_mysql"

    def test_repair_gaussdb_oracle_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (Oracle Mode) self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_oracle"

    def test_repair_gaussdb_oracle_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (Oracle Mode) self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_oracle"

    def test_repair_gaussdb_oracle_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (Oracle Mode) self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_oracle"

    def test_repair_gaussdb_oracle_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (Oracle Mode) self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_oracle"

    def test_repair_gaussdb_oracle_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (Oracle Mode) self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_oracle"

    def test_repair_gaussdb_oracle_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (Oracle Mode) self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_oracle"

    def test_repair_gaussdb_oracle_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (Oracle Mode) self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_oracle")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_oracle", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_oracle"

    def test_repair_gaussdb_mysql_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (MySQL Mode) self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_mysql"

    def test_repair_gaussdb_mysql_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (MySQL Mode) self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_mysql"

    def test_repair_gaussdb_mysql_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (MySQL Mode) self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_mysql"

    def test_repair_gaussdb_mysql_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (MySQL Mode) self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_mysql"

    def test_repair_gaussdb_mysql_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (MySQL Mode) self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_mysql"

    def test_repair_gaussdb_mysql_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (MySQL Mode) self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_mysql"

    def test_repair_gaussdb_mysql_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify GaussDB (MySQL Mode) self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "gaussdb_mysql")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "gaussdb_mysql", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "gaussdb_mysql"

    def test_repair_goldendb_missing_id(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify ZTE GoldenDB self-healing for missing_id."""
        failing = 'SELECT status_code FROM accounts;'
        raw_err = "42703: column 'status_code' does not exist"
        diag = engine.diagnose_failure(raw_err, failing, "goldendb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "goldendb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "goldendb"

    def test_repair_goldendb_type_mismatch(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify ZTE GoldenDB self-healing for type_mismatch."""
        failing = "SELECT * FROM tab WHERE id = '100';"
        raw_err = '42804: cannot cast type text to integer'
        diag = engine.diagnose_failure(raw_err, failing, "goldendb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "goldendb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "goldendb"

    def test_repair_goldendb_null_insert(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify ZTE GoldenDB self-healing for null_insert."""
        failing = 'INSERT INTO t (id, amt) VALUES (1, NULL);'
        raw_err = '23502: null value violates not-null constraint'
        diag = engine.diagnose_failure(raw_err, failing, "goldendb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "goldendb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "goldendb"

    def test_repair_goldendb_string_trunc(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify ZTE GoldenDB self-healing for string_trunc."""
        failing = "INSERT INTO t (code) VALUES ('ABCDEFGHIJKLMNO123456');"
        raw_err = '22001: value too long'
        diag = engine.diagnose_failure(raw_err, failing, "goldendb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "goldendb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "goldendb"

    def test_repair_goldendb_unresolved_fn(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify ZTE GoldenDB self-healing for unresolved_fn."""
        failing = "SELECT NVL(col1, 'N/A') FROM t;"
        raw_err = '42883: function nvl(text, text) does not exist'
        diag = engine.diagnose_failure(raw_err, failing, "goldendb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "goldendb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "goldendb"

    def test_repair_goldendb_dup_key_conflict(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify ZTE GoldenDB self-healing for dup_key_conflict."""
        failing = 'INSERT INTO t (id, val) VALUES (1, 100);'
        raw_err = '23505: duplicate key violates unique constraint'
        diag = engine.diagnose_failure(raw_err, failing, "goldendb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "goldendb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "goldendb"

    def test_repair_goldendb_deadlock_hint(
        self, engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        """Verify ZTE GoldenDB self-healing for deadlock_hint."""
        failing = 'SELECT * FROM accounts FOR UPDATE;'
        raw_err = '40P01: deadlock detected'
        diag = engine.diagnose_failure(raw_err, failing, "goldendb")
        assert len(diag.failure_id) > 0
        def sandbox_ok(s: str) -> tuple[bool, str]:
            return (True, '')
        ok, rep, receipt = engine.autonomous_repair_and_verify(
            failing, raw_err, "goldendb", sandbox_verifier=sandbox_ok
        )
        assert ok is True
        assert len(rep) > 0
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert receipt.target_engine == "goldendb"

class TestL5AutonomousMigrationStages:
    @pytest.fixture
    def engine(self) -> AutonomousDatabaseMigrationEngine:
        cfg = AutonomousMigrationConfig(
            project_id="mig_test_autonomous_l5",
            source_engine="oracle",
            target_engine="dm8",
            concurrency_threads=8,
            zero_human_review_required=True,
        )
        eng = AutonomousDatabaseMigrationEngine(config=cfg)
        assets = [
            {
                "asset_id": "tbl_customers",
                "asset_name": "customers",
                "asset_kind": "TABLE",
                "source_ddl": (
                    "CREATE TABLE customers (id NUMBER PRIMARY KEY, name VARCHAR2(100));"
                ),
            },
            {
                "asset_id": "tbl_orders",
                "asset_name": "orders",
                "asset_kind": "TABLE",
                "source_ddl": (
                    "CREATE TABLE orders (order_id NUMBER PRIMARY KEY, cust_id NUMBER);"
                ),
            },
            {
                "asset_id": "v_cust_orders",
                "asset_name": "v_cust_orders",
                "asset_kind": "VIEW",
                "source_ddl": "CREATE VIEW v_cust_orders AS SELECT name FROM customers;",
            },
            {
                "asset_id": "sp_calc_totals",
                "asset_name": "sp_calc_totals",
                "asset_kind": "PROCEDURE",
                "source_ddl": (
                    "CREATE OR REPLACE PROCEDURE sp_calc_totals AS BEGIN NULL; END;"
                ),
            },
            {
                "asset_id": "trg_orders_audit",
                "asset_name": "trg_orders_audit",
                "asset_kind": "TRIGGER",
                "source_ddl": (
                    "CREATE OR REPLACE TRIGGER trg_orders_audit "
                    "BEFORE INSERT ON orders FOR EACH ROW BEGIN NULL; END;"
                ),
            },
            {
                "asset_id": "seq_order_id",
                "asset_name": "seq_order_id",
                "asset_kind": "SEQUENCE",
                "source_ddl": (
                    "CREATE SEQUENCE seq_order_id START WITH 1 INCREMENT BY 1;"
                ),
            },
        ]
        eng.register_source_assets(assets)
        return eng

    def test_stage_1_inventory_discovery(
        self, engine: AutonomousDatabaseMigrationEngine
    ) -> None:
        engine._run_stage_inventory_discovery()
        rec = engine.stage_records[-1]
        assert rec.stage == AutonomousMigrationStage.INVENTORY_DISCOVERY
        assert rec.success is True
        assert rec.assets_processed == 6
        assert len(engine.assets) == 6
        for a in engine.assets.values():
            assert isinstance(a, MigrationAsset)
            assert len(a.asset_id) > 0

    def test_stage_2_ast_lowering(
        self, engine: AutonomousDatabaseMigrationEngine
    ) -> None:
        engine._run_stage_inventory_discovery()
        engine._run_stage_ast_lowering()
        rec = engine.stage_records[-1]
        assert rec.stage == AutonomousMigrationStage.AST_LOWERING
        assert rec.success is True
        for a in engine.assets.values():
            assert len(a.lowered_ddl) > 0
            assert a.status == MigrationStatus.LOWERED

    def test_stage_3_invariant_extraction(
        self, engine: AutonomousDatabaseMigrationEngine
    ) -> None:
        engine._run_stage_inventory_discovery()
        engine._run_stage_ast_lowering()
        engine._run_stage_invariant_extraction()
        rec = engine.stage_records[-1]
        assert rec.stage == AutonomousMigrationStage.INVARIANT_EXTRACTION
        assert rec.success is True
        assert rec.assets_processed == 6

    def test_stage_4_autonomous_repair(
        self, engine: AutonomousDatabaseMigrationEngine
    ) -> None:
        engine._run_stage_inventory_discovery()
        engine._run_stage_ast_lowering()
        engine._run_stage_autonomous_repair()
        rec = engine.stage_records[-1]
        assert rec.stage == AutonomousMigrationStage.AUTONOMOUS_REPAIR
        assert rec.success is True

    def test_stage_5_ddl_execution(
        self, engine: AutonomousDatabaseMigrationEngine
    ) -> None:
        engine._run_stage_inventory_discovery()
        engine._run_stage_ast_lowering()
        receipt = engine._run_stage_ddl_execution()
        assert isinstance(receipt, DdlExecutionReceipt)
        assert isinstance(engine.ddl_executor, ChinaDbDdlExecutor)
        rec = engine.stage_records[-1]
        assert rec.stage == AutonomousMigrationStage.DDL_EXECUTION
        assert rec.success is True

    def test_stage_6_baseline_data_load(
        self, engine: AutonomousDatabaseMigrationEngine
    ) -> None:
        engine._run_stage_inventory_discovery()
        engine._run_stage_ast_lowering()
        engine._run_stage_baseline_data_load()
        rec = engine.stage_records[-1]
        assert rec.stage == AutonomousMigrationStage.BASELINE_DATA_LOAD
        assert rec.success is True
        tables = [a for a in engine.assets.values() if a.asset_kind == MigrationAssetKind.TABLE]
        for t in tables:
            assert t.row_count > 0
            assert len(t.checksum) > 0

    def test_stage_7_cdc_replay(
        self, engine: AutonomousDatabaseMigrationEngine
    ) -> None:
        engine._run_stage_inventory_discovery()
        events, divergences = engine._run_stage_cdc_replay()
        assert events > 0
        assert divergences == 0
        rec = engine.stage_records[-1]
        assert rec.stage == AutonomousMigrationStage.CDC_STREAM_REPLAY
        assert rec.success is True

    def test_stage_8_concurrency_stress(
        self, engine: AutonomousDatabaseMigrationEngine
    ) -> None:
        receipt = engine._run_stage_concurrency_stress()
        assert isinstance(receipt, StressTestReceipt)
        assert receipt.latency_p95_ms <= 75.0
        rec = engine.stage_records[-1]
        assert rec.stage == AutonomousMigrationStage.CONCURRENCY_STRESS
        assert rec.success is True

    def test_stage_9_cutover_certification(
        self, engine: AutonomousDatabaseMigrationEngine
    ) -> None:
        dossier = engine.execute_full_migration()
        assert isinstance(dossier, AutonomousMigrationDossier)
        assert dossier.overall_success is True
        assert dossier.autonomy_level == "L5_AUTONOMOUS_ZERO_HUMAN"
        assert dossier.human_review_backlog_count == 0
        assert len(dossier.stages) == 9

class TestEndToEndMigration13Targets:
    """End-to-end full migration scenarios across all 13 domestic databases."""

    def test_e2e_migration_dm8(self) -> None:
        """End-to-end autonomous migration to Dameng 8 (DM8)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-dm8",
            source_engine="oracle",
            target_engine="dm8",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "dm8_account",
                "asset_name": "dm8_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "dm8_v_active",
                "asset_name": "dm8_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "dm8_sp_sync",
                "asset_name": "dm8_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "dm8"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_dm8_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for Dameng 8 (DM8)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-dm8",
            source_engine="oracle",
            target_engine="dm8",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "dm8_gl",
            "asset_name": "dm8_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_kingbase(self) -> None:
        """End-to-end autonomous migration to KingbaseES (V8/V9)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-kingbase",
            source_engine="oracle",
            target_engine="kingbase",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "kingbase_account",
                "asset_name": "kingbase_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "kingbase_v_active",
                "asset_name": "kingbase_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "kingbase_sp_sync",
                "asset_name": "kingbase_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "kingbase"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_kingbase_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for KingbaseES (V8/V9)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-kingbase",
            source_engine="oracle",
            target_engine="kingbase",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "kingbase_gl",
            "asset_name": "kingbase_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_opengauss(self) -> None:
        """End-to-end autonomous migration to openGauss / MogDB."""
        config = AutonomousMigrationConfig(
            project_id="e2e-opengauss",
            source_engine="oracle",
            target_engine="opengauss",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "opengauss_account",
                "asset_name": "opengauss_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "opengauss_v_active",
                "asset_name": "opengauss_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "opengauss_sp_sync",
                "asset_name": "opengauss_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "opengauss"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_opengauss_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for openGauss / MogDB."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-opengauss",
            source_engine="oracle",
            target_engine="opengauss",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "opengauss_gl",
            "asset_name": "opengauss_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_tidb(self) -> None:
        """End-to-end autonomous migration to TiDB (v6/v7)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-tidb",
            source_engine="mysql",
            target_engine="tidb",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "tidb_account",
                "asset_name": "tidb_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "tidb_v_active",
                "asset_name": "tidb_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "tidb_sp_sync",
                "asset_name": "tidb_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "tidb"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_tidb_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for TiDB (v6/v7)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-tidb",
            source_engine="mysql",
            target_engine="tidb",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "tidb_gl",
            "asset_name": "tidb_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_gbase8s(self) -> None:
        """End-to-end autonomous migration to GBase 8s (Informix-based)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-gbase8s",
            source_engine="informix",
            target_engine="gbase8s",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "gbase8s_account",
                "asset_name": "gbase8s_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "gbase8s_v_active",
                "asset_name": "gbase8s_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "gbase8s_sp_sync",
                "asset_name": "gbase8s_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "gbase8s"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_gbase8s_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for GBase 8s (Informix-based)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-gbase8s",
            source_engine="informix",
            target_engine="gbase8s",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "gbase8s_gl",
            "asset_name": "gbase8s_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_gbase8c(self) -> None:
        """End-to-end autonomous migration to GBase 8c (Distributed openGauss)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-gbase8c",
            source_engine="postgres",
            target_engine="gbase8c",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "gbase8c_account",
                "asset_name": "gbase8c_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "gbase8c_v_active",
                "asset_name": "gbase8c_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "gbase8c_sp_sync",
                "asset_name": "gbase8c_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "gbase8c"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_gbase8c_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for GBase 8c (Distributed openGauss)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-gbase8c",
            source_engine="postgres",
            target_engine="gbase8c",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "gbase8c_gl",
            "asset_name": "gbase8c_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_gbase8a(self) -> None:
        """End-to-end autonomous migration to GBase 8a (MPP Columnar)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-gbase8a",
            source_engine="mysql",
            target_engine="gbase8a",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "gbase8a_account",
                "asset_name": "gbase8a_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "gbase8a_v_active",
                "asset_name": "gbase8a_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "gbase8a_sp_sync",
                "asset_name": "gbase8a_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "gbase8a"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_gbase8a_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for GBase 8a (MPP Columnar)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-gbase8a",
            source_engine="mysql",
            target_engine="gbase8a",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "gbase8a_gl",
            "asset_name": "gbase8a_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_highgo(self) -> None:
        """End-to-end autonomous migration to HighGo DB (HGDB)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-highgo",
            source_engine="postgres",
            target_engine="highgo",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "highgo_account",
                "asset_name": "highgo_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "highgo_v_active",
                "asset_name": "highgo_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "highgo_sp_sync",
                "asset_name": "highgo_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "highgo"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_highgo_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for HighGo DB (HGDB)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-highgo",
            source_engine="postgres",
            target_engine="highgo",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "highgo_gl",
            "asset_name": "highgo_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_oceanbase_oracle(self) -> None:
        """End-to-end autonomous migration to OceanBase (Oracle Mode)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-oceanbase_oracle",
            source_engine="oracle",
            target_engine="oceanbase_oracle",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "oceanbase_oracle_account",
                "asset_name": "oceanbase_oracle_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "oceanbase_oracle_v_active",
                "asset_name": "oceanbase_oracle_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "oceanbase_oracle_sp_sync",
                "asset_name": "oceanbase_oracle_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "oceanbase_oracle"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_oceanbase_oracle_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for OceanBase (Oracle Mode)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-oceanbase_oracle",
            source_engine="oracle",
            target_engine="oceanbase_oracle",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "oceanbase_oracle_gl",
            "asset_name": "oceanbase_oracle_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_oceanbase_mysql(self) -> None:
        """End-to-end autonomous migration to OceanBase (MySQL Mode)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-oceanbase_mysql",
            source_engine="mysql",
            target_engine="oceanbase_mysql",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "oceanbase_mysql_account",
                "asset_name": "oceanbase_mysql_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "oceanbase_mysql_v_active",
                "asset_name": "oceanbase_mysql_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "oceanbase_mysql_sp_sync",
                "asset_name": "oceanbase_mysql_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "oceanbase_mysql"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_oceanbase_mysql_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for OceanBase (MySQL Mode)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-oceanbase_mysql",
            source_engine="mysql",
            target_engine="oceanbase_mysql",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "oceanbase_mysql_gl",
            "asset_name": "oceanbase_mysql_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_gaussdb_oracle(self) -> None:
        """End-to-end autonomous migration to GaussDB (Oracle Mode)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-gaussdb_oracle",
            source_engine="oracle",
            target_engine="gaussdb_oracle",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "gaussdb_oracle_account",
                "asset_name": "gaussdb_oracle_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "gaussdb_oracle_v_active",
                "asset_name": "gaussdb_oracle_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "gaussdb_oracle_sp_sync",
                "asset_name": "gaussdb_oracle_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "gaussdb_oracle"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_gaussdb_oracle_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for GaussDB (Oracle Mode)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-gaussdb_oracle",
            source_engine="oracle",
            target_engine="gaussdb_oracle",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "gaussdb_oracle_gl",
            "asset_name": "gaussdb_oracle_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_gaussdb_mysql(self) -> None:
        """End-to-end autonomous migration to GaussDB (MySQL Mode)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-gaussdb_mysql",
            source_engine="mysql",
            target_engine="gaussdb_mysql",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "gaussdb_mysql_account",
                "asset_name": "gaussdb_mysql_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "gaussdb_mysql_v_active",
                "asset_name": "gaussdb_mysql_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "gaussdb_mysql_sp_sync",
                "asset_name": "gaussdb_mysql_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "gaussdb_mysql"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_gaussdb_mysql_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for GaussDB (MySQL Mode)."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-gaussdb_mysql",
            source_engine="mysql",
            target_engine="gaussdb_mysql",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "gaussdb_mysql_gl",
            "asset_name": "gaussdb_mysql_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

    def test_e2e_migration_goldendb(self) -> None:
        """End-to-end autonomous migration to ZTE GoldenDB."""
        config = AutonomousMigrationConfig(
            project_id="e2e-goldendb",
            source_engine="mysql",
            target_engine="goldendb",
            max_healing_attempts=3,
            stress_duration_seconds=0.2,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [
            {
                "asset_id": "goldendb_account",
                "asset_name": "goldendb_account",
                "asset_kind": "TABLE",
                "source_ddl": """
                    CREATE TABLE account_ledger (
                        acc_id BIGINT NOT NULL,
                        acc_name VARCHAR(128) NOT NULL,
                        balance DECIMAL(18, 4) NOT NULL,
                        CONSTRAINT pk_acc PRIMARY KEY (acc_id)
                    );
                """,
            },
            {
                "asset_id": "goldendb_v_active",
                "asset_name": "goldendb_v_active",
                "asset_kind": "VIEW",
                "source_ddl": """
                    CREATE VIEW v_active_ledger AS
                    SELECT acc_id, acc_name, balance FROM account_ledger WHERE balance > 0;
                """,
            },
            {
                "asset_id": "goldendb_sp_sync",
                "asset_name": "goldendb_sp_sync",
                "asset_kind": "PROCEDURE",
                "source_ddl": """
                    CREATE OR REPLACE PROCEDURE sp_sync_ledger AS
                    BEGIN
                        NULL;
                    END;
                """,
            },
        ]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.target_engine == "goldendb"
        assert dossier.total_assets == 3
        assert dossier.successful_assets == 3
        assert dossier.failed_assets == 0
        assert dossier.p95_latency_ms <= 75.0
        assert len(dossier.integrity_digest) == 64

    def test_e2e_migration_goldendb_invariant_holds(self) -> None:
        """Verify data conservation invariant holds for ZTE GoldenDB."""
        config = AutonomousMigrationConfig(
            project_id="e2e-inv-goldendb",
            source_engine="mysql",
            target_engine="goldendb",
            enforce_double_entry_conservation=True,
            stress_duration_seconds=0.2,
        )
        engine = AutonomousDatabaseMigrationEngine(config=config)
        assets = [{
            "asset_id": "goldendb_gl",
            "asset_name": "goldendb_gl",
            "asset_kind": "TABLE",
            "source_ddl": "CREATE TABLE gl (id INT PRIMARY KEY, bal DECIMAL(16,2));",
        }]
        engine.register_source_assets(assets)
        dossier = engine.execute_full_migration()
        assert dossier.asset_conservation_verified is True
        assert dossier.cdc_divergence_count == 0

class TestCdcReplicationAndDataIntegrity:
    """Test CDC change capture, event replay, and row-level hash reconciliation."""

    @pytest.fixture
    def cdc_engine(self) -> ChinaDbCdcEngine:
        return ChinaDbCdcEngine()

    def test_cdc_apply_insert_event(self, cdc_engine: ChinaDbCdcEngine) -> None:
        evt = ChangeEvent(
            table_name="accounts",
            op_type=CdcOpType.INSERT,
            after_state={"acc_id": "A100", "balance": 1500.0},
            lsn=1,
            tx_id="tx_001",
        )
        ok = cdc_engine.apply_event("dm8", evt)
        assert ok is True

    def test_cdc_apply_update_event(self, cdc_engine: ChinaDbCdcEngine) -> None:
        evt = ChangeEvent(
            table_name="accounts",
            op_type=CdcOpType.UPDATE,
            before_state={"acc_id": "A100", "balance": 1500.0},
            after_state={"acc_id": "A100", "balance": 2500.0},
            lsn=2,
            tx_id="tx_002",
        )
        ok = cdc_engine.apply_event("dm8", evt)
        assert ok is True

    def test_cdc_apply_delete_event(self, cdc_engine: ChinaDbCdcEngine) -> None:
        evt = ChangeEvent(
            table_name="accounts",
            op_type=CdcOpType.DELETE,
            before_state={"acc_id": "A100", "balance": 2500.0},
            lsn=3,
            tx_id="tx_003",
        )
        ok = cdc_engine.apply_event("dm8", evt)
        assert ok is True

    def test_cdc_apply_batch(self, cdc_engine: ChinaDbCdcEngine) -> None:
        events = [
            ChangeEvent(
                table_name="accounts",
                op_type=CdcOpType.INSERT,
                after_state={"acc_id": f"A{i:03d}", "balance": 100.0 * i},
                lsn=i,
                tx_id=f"tx_{i:03d}",
            )
            for i in range(1, 11)
        ]
        replayed = cdc_engine.apply_batch("dm8", events)
        assert replayed == 10

    def test_cdc_table_hash_reconciliation(self, cdc_engine: ChinaDbCdcEngine) -> None:
        db = cdc_engine.orchestrator.get_database("dm8")
        db.execute_sql(
            "CREATE TABLE IF NOT EXISTS accounts (id INT PRIMARY KEY, val VARCHAR(10));"
        )
        db.execute_sql("INSERT INTO accounts VALUES (1, 'X'), (2, 'Y');")
        src_rows = [{'id': 1, 'val': 'X'}, {'id': 2, 'val': 'Y'}]
        receipt = cdc_engine.reconcile_table_data(src_rows, "dm8", "accounts", ["id"])
        assert receipt.is_consistent is True
        assert receipt.matched_count == 2
        assert receipt.mismatched_count == 0
        assert receipt.source_table_digest == receipt.target_table_digest

class TestConcurrencyStressEngine:
    """Test multi-worker high-concurrency transactional stress testing."""

    @pytest.fixture
    def stress_engine(self) -> ChinaDbStressEngine:
        return ChinaDbStressEngine()

    def test_stress_benchmark_low_concurrency(self, stress_engine: ChinaDbStressEngine) -> None:
        receipt = stress_engine.run_benchmark(
            target_id="dm8",
            concurrency=4,
            transactions_per_worker=10,
            num_accounts=10,
            max_p95_latency_ms=75.0,
        )
        assert isinstance(receipt, StressTestReceipt)
        assert receipt.total_transactions == 40
        assert receipt.successful_transactions == 40
        assert receipt.failed_transactions == 0
        assert receipt.latency_p95_ms <= 75.0
        assert receipt.conservation_invariant_holds is True
        assert receipt.slo_passed is True

    def test_stress_benchmark_high_concurrency(self, stress_engine: ChinaDbStressEngine) -> None:
        receipt = stress_engine.run_benchmark(
            target_id="dm8",
            concurrency=16,
            transactions_per_worker=25,
            num_accounts=20,
            max_p95_latency_ms=75.0,
        )
        assert receipt.total_transactions == 400
        assert receipt.successful_transactions == 400
        assert receipt.tps > 0
        assert receipt.latency_p95_ms <= 75.0
        assert receipt.conservation_invariant_holds is True

