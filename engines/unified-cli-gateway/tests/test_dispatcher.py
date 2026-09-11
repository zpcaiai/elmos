"""Tests for elmos_cli.dispatcher — properly mocking all external dependencies."""

import sys
import unittest
from unittest.mock import patch, MagicMock

# ── Pre-import mocks for external modules that dispatcher lazily imports ──────
_EXTERNAL_MODS = [
    'yaml',
    'elmos_polyglot_compiler',
    'elmos_polyglot_compiler.service',
    'elmos_polyglot_compiler.self_healing',
    'elmos_formal_assurance',
    'elmos_formal_assurance.lean_bridge',
    'elmos_formal_assurance.lean_dafny_bridge',
    'elmos_formal_assurance.hermetic_environment_builder',
    'elmos_sql_dialect',
    'elmos_sql_dialect.sql_transpiler_gateway',
    'elmos_security_engine',
    'elmos_security_engine.iam_policy_transpiler',
]
for _mod in _EXTERNAL_MODS:
    sys.modules[_mod] = MagicMock()

# Setup specific return values on mock functions so dispatcher serialization works
sys.modules['elmos_formal_assurance.lean_dafny_bridge'].generate_lean4_proof.return_value = {
    "status": "SAT_PROVED",
    "obligation": "test_obligation",
    "proof_artifact": "theorem t1 : True := trivial",
}
sys.modules['elmos_polyglot_compiler.service'].get_polyglot_service_status.return_value = {
    "status": "HEALTHY",
    "supported_routes": 784,
}
sys.modules['elmos_polyglot_compiler.service'].list_active_routes.return_value = [
    {"source": "java", "target": "csharp", "certified": True}
]
sys.modules['elmos_polyglot_compiler.service'].transform_code.return_value = {
    "status": "SUCCESS",
    "target_code": "class Target {}",
}
sys.modules['elmos_polyglot_compiler.service'].check_smt_formula.return_value = {
    "sat": True,
    "model": {},
}
sys.modules['elmos_polyglot_compiler.service'].run_differential_fuzzing.return_value = {
    "status": "PASS",
    "mutants_tested": 100,
}
sys.modules['elmos_polyglot_compiler.service'].certify_language_route.return_value = {
    "verdict": "CERTIFIED",
    "route": "java->csharp",
}
sys.modules['elmos_polyglot_compiler.service'].diff_api_contracts.return_value = {
    "status": "COMPATIBLE",
    "breaking_changes": [],
}

# Mock yaml
def _yaml_dump(data, **kwargs):
    if isinstance(data, dict):
        return "\n".join(f"{k}: {v}" for k, v in data.items()) + "\n"
    if isinstance(data, list):
        return "\n".join(f"- {item}" for item in data) + "\n"
    return str(data) + "\n"

sys.modules['yaml'].dump = _yaml_dump
sys.modules['yaml'].safe_load.return_value = {"tenant_id": "test-tenant"}

# Mock sql transpiler gateway
_sql_gw = sys.modules['elmos_sql_dialect.sql_transpiler_gateway']
_sql_gw.SUPPORTED_DIALECTS = ["oracle", "postgresql", "mysql", "tsql"]
_transpile_res = MagicMock()
_transpile_res.status = "SYNTAX_READY"
_transpile_res.source_dialect = "oracle"
_transpile_res.target_dialect = "postgres"
_transpile_res.source_profile = "oracle-26ai-ee"
_transpile_res.target_profile = "postgresql-18.4"
_transpile_res.source_sql = "SELECT 1"
_transpile_res.target_sql = "SELECT 1"
_transpile_res.transformed_constructs = []
_transpile_res.warnings = []
_transpile_res.semantic_equivalence = "CERTIFIED"
_transpile_res.reason_code = "OK"
_transpile_res.reason = "OK"
_transpile_res.verification = {}
_transpile_res.merkle_receipt = "0000"
_sql_gw.SqlTranspilerGateway.return_value.transpile.return_value = _transpile_res
_sql_gw.SqlTranspilerGateway.return_value.diff_schemas.return_value = {"status": "IDENTICAL", "differences": []}

# Mock security transpiler
_sec_mod = sys.modules['elmos_security_engine.iam_policy_transpiler']
_sec_mock_inst = MagicMock()
_sec_mock_inst.transpile_policy.return_value = {"status": "SUCCESS", "policy": {}}
_sec_mod.IamPolicyTranspiler.return_value = _sec_mock_inst

from elmos_cli.dispatcher import main, _get_global_status


class TestDispatcher(unittest.TestCase):
    """Verify CLI dispatcher routing and subcommand handling."""

    def setUp(self):
        sys.modules['elmos_formal_assurance.lean_dafny_bridge'].generate_lean4_proof = MagicMock(return_value={
            "status": "SAT_PROVED",
            "obligation": "test_obligation",
            "proof_artifact": "theorem t1 : True := trivial",
        })
        self.patches = [
            patch('elmos_cli.composite_pipeline.run_composite_pipeline', return_value={"status": "SUCCESS"}),
            patch('elmos_cli.interactive.run_interactive_wizard', return_value=0),
            patch('elmos_cli.dispatcher.run_interactive_wizard', return_value=0),
            patch('elmos_cli.daemon.run_daemon', return_value=0),
            patch('elmos_cli.lsp_server.run_lsp_server', return_value=0),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def call_main(self, args):
        with patch('sys.argv', ['elmos'] + args):
            try:
                code = main()
                return code if code is not None else 0
            except SystemExit as e:
                return e.code if e.code is not None else 0

    # ── Basic routes ──────────────────────────────────────────────────────

    def test_main_no_args(self):
        self.assertEqual(self.call_main([]), 0)

    def test_status(self):
        self.assertEqual(self.call_main(['status']), 0)

    # ── Polyglot subcommands ──────────────────────────────────────────────

    def test_polyglot_status(self):
        self.assertEqual(self.call_main(['polyglot', 'status']), 0)

    def test_polyglot_routes(self):
        self.assertEqual(self.call_main(['polyglot', 'routes']), 0)

    def test_polyglot_transform(self):
        self.assertEqual(self.call_main(['polyglot', 'transform']), 0)

    def test_polyglot_formal_check(self):
        self.assertEqual(self.call_main(['polyglot', 'formal-check']), 0)

    def test_polyglot_fuzz_matrix(self):
        self.assertEqual(self.call_main(['polyglot', 'fuzz-matrix']), 0)

    def test_polyglot_certify_route(self):
        self.assertEqual(self.call_main(['polyglot', 'certify-route']), 0)

    def test_polyglot_api_diff(self):
        self.assertEqual(self.call_main(['polyglot', 'api-diff']), 0)

    # ── Commercial subcommands ────────────────────────────────────────────

    def test_commercial_status(self):
        self.assertEqual(self.call_main(['commercial', 'status']), 0)

    def test_commercial_kernels(self):
        self.assertEqual(self.call_main(['commercial', 'kernels']), 0)

    def test_commercial_pipelines(self):
        self.assertEqual(self.call_main(['commercial', 'pipelines']), 0)

    # ── Assurance subcommands ─────────────────────────────────────────────

    def test_assurance_status(self):
        self.assertEqual(self.call_main(['assurance', 'status']), 0)

    def test_assurance_layers(self):
        self.assertEqual(self.call_main(['assurance', 'layers']), 0)

    def test_assurance_lean_proof(self):
        self.assertEqual(self.call_main(['assurance', 'lean-proof']), 0)

    def test_assurance_export_hermetic_toolchain(self):
        self.assertEqual(self.call_main(['assurance', 'export-hermetic-toolchain']), 0)

    def test_assurance_sign_sbom(self):
        self.assertEqual(self.call_main(['assurance', 'sign-sbom']), 0)

    # ── Daemon / LSP / Runner ─────────────────────────────────────────────

    def test_lsp(self):
        self.assertEqual(self.call_main(['lsp']), 0)

    def test_daemon(self):
        self.assertEqual(self.call_main(['daemon']), 0)

    def test_runner_fleet_status(self):
        self.assertEqual(self.call_main(['runner', 'fleet-status']), 0)

    def test_runner_dispatch(self):
        self.assertEqual(self.call_main(['runner', 'dispatch']), 0)

    # ── QA subcommands ────────────────────────────────────────────────────

    def test_qa_status(self):
        self.assertEqual(self.call_main(['qa', 'status']), 0)

    def test_qa_consensus(self):
        self.assertEqual(self.call_main(['qa', 'consensus']), 0)

    def test_qa_mutate(self):
        self.assertEqual(self.call_main(['qa', 'mutate']), 0)

    # ── Sandbox ───────────────────────────────────────────────────────────

    def test_sandbox_inspect_policy(self):
        self.assertEqual(self.call_main(['sandbox', 'inspect-policy']), 0)

    # ── Telemetry ─────────────────────────────────────────────────────────

    def test_telemetry_export_otlp(self):
        self.assertEqual(self.call_main(['telemetry', 'export-otlp']), 0)

    def test_telemetry_metrics(self):
        self.assertEqual(self.call_main(['telemetry', 'metrics']), 0)

    # ── Cache ─────────────────────────────────────────────────────────────

    def test_cache_inspect(self):
        self.assertEqual(self.call_main(['cache', 'inspect']), 0)

    def test_cache_purge(self):
        self.assertEqual(self.call_main(['cache', 'purge']), 0)

    # ── SQL ───────────────────────────────────────────────────────────────

    def test_sql_dialects(self):
        self.assertEqual(self.call_main(['sql', 'dialects']), 0)

    def test_sql_transpile(self):
        self.assertEqual(self.call_main(['sql', 'transpile']), 0)

    def test_sql_diff_ddl(self):
        self.assertEqual(self.call_main(['sql', 'diff-ddl']), 0)

    # ── Security ──────────────────────────────────────────────────────────

    def test_security_transpile_policy(self):
        self.assertEqual(self.call_main(['security', 'transpile-policy']), 0)

    # ── Pipeline / Config / Interactive ───────────────────────────────────

    def test_pipeline(self):
        self.assertEqual(self.call_main(['pipeline']), 0)

    def test_config_show(self):
        self.assertEqual(self.call_main(['config', 'show']), 0)

    def test_config_init_force(self):
        self.assertEqual(self.call_main(['config', 'init', '--force']), 0)

    def test_interactive(self):
        self.assertEqual(self.call_main(['interactive']), 0)

    # ── Completion (positional arg for shell) ─────────────────────────────

    def test_completion_bash(self):
        self.assertEqual(self.call_main(['completion']), 0)

    def test_completion_bash_explicit(self):
        self.assertEqual(self.call_main(['completion', 'bash']), 0)

    def test_completion_zsh(self):
        self.assertEqual(self.call_main(['completion', 'zsh']), 0)

    def test_completion_fish(self):
        self.assertEqual(self.call_main(['completion', 'fish']), 0)

    # ── Global status function ────────────────────────────────────────────

    def test_get_global_status_has_version(self):
        status = _get_global_status()
        self.assertIn("version", status)

    def test_get_global_status_has_status(self):
        status = _get_global_status()
        self.assertIn("status", status)
        self.assertEqual(status["status"], "HEALTHY")

    def test_get_global_status_has_total_engines(self):
        status = _get_global_status()
        self.assertIn("total_engines", status)
        self.assertIsInstance(status["total_engines"], int)
        self.assertGreater(status["total_engines"], 0)

    def test_get_global_status_has_workspace_skills(self):
        status = _get_global_status()
        self.assertIn("workspace_skills", status)

    def test_get_global_status_has_ready_capabilities(self):
        status = _get_global_status()
        self.assertIn("ready_capabilities", status)
        self.assertIsInstance(status["ready_capabilities"], list)
