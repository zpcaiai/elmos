"""Tests for elmos_cli.dispatcher — properly mocking all external dependencies."""

import sys
import unittest
from unittest.mock import patch, MagicMock

# ── Pre-import mocks for external modules that dispatcher lazily imports ──────
_EXTERNAL_MODS = [
    'yaml',
    'elmos_polyglot_compiler', 'elmos_polyglot_compiler.service',
    'elmos_polyglot_compiler.self_healing',
    'elmos_formal_assurance', 'elmos_formal_assurance.lean_bridge',
    'elmos_sql_dialect', 'elmos_sql_dialect.sql_transpiler_gateway',
    'elmos_security_engine', 'elmos_security_engine.iam_policy_transpiler',
]
for _mod in _EXTERNAL_MODS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from elmos_cli.dispatcher import main, _get_global_status


class TestDispatcher(unittest.TestCase):
    """Verify CLI dispatcher routing and subcommand handling."""

    def setUp(self):
        self.patches = [
            patch('elmos_cli.composite_pipeline.run_composite_pipeline', return_value={}),
            patch('elmos_cli.interactive.run_interactive_wizard', return_value=0),
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

    # ── SQL (requires mocked elmos_sql_dialect) ───────────────────────────

    def test_sql_dialects(self):
        self.assertEqual(self.call_main(['sql', 'dialects']), 0)

    def test_sql_transpile(self):
        self.assertEqual(self.call_main(['sql', 'transpile']), 0)

    def test_sql_diff_ddl(self):
        self.assertEqual(self.call_main(['sql', 'diff-ddl']), 0)

    # ── Security (requires mocked elmos_security_engine) ──────────────────

    def test_security_transpile_policy(self):
        self.assertEqual(self.call_main(['security', 'transpile-policy']), 0)

    # ── Pipeline / Config / Interactive ───────────────────────────────────

    def test_pipeline(self):
        self.assertEqual(self.call_main(['pipeline']), 0)

    def test_config_show(self):
        self.assertEqual(self.call_main(['config', 'show']), 0)

    def test_config_init(self):
        self.assertEqual(self.call_main(['config', 'init']), 0)

    def test_interactive(self):
        self.assertEqual(self.call_main(['interactive']), 0)

    # ── Completion (default is bash, positional arg for shell) ──────────

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

