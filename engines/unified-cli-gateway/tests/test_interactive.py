"""Tests for elmos_cli.interactive — ensuring robust REPL wizard coverage without blocking."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Pre-mock external modules
_mock_yaml = MagicMock()
_mock_yaml.safe_load.return_value = {
    "tenant_id": "test-tenant",
    "actor_id": "test-actor",
    "default_src_lang": "java",
    "default_tgt_lang": "csharp",
    "budget_limit_usd": 50.0,
}
_mock_yaml.dump.return_value = "tenant_id: test-tenant\n"
sys.modules['yaml'] = _mock_yaml

_mock_poly = MagicMock()
_mock_poly_service = MagicMock()
_mock_poly_service.check_smt_formula.return_value = {"sat": True, "model": {}}
sys.modules['elmos_polyglot_compiler'] = _mock_poly
sys.modules['elmos_polyglot_compiler.service'] = _mock_poly_service

from elmos_cli.interactive import run_interactive_wizard


class TestInteractive(unittest.TestCase):
    """Test the CLI interactive wizard."""

    @patch('builtins.input', return_value='0')
    def test_run_interactive_wizard_exit_0(self, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)

    @patch('builtins.input', side_effect=EOFError)
    def test_run_interactive_wizard_eof(self, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)

    @patch('builtins.input', side_effect=KeyboardInterrupt)
    def test_run_interactive_wizard_keyboard_interrupt(self, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)

    @patch('builtins.input', return_value='9')
    def test_run_interactive_wizard_unknown(self, mock_input):
        self.assertEqual(run_interactive_wizard(), 1)

    @patch('builtins.input', return_value='1')
    @patch('elmos_cli.dispatcher._get_global_status', return_value={"status": "HEALTHY", "total_engines": 54})
    def test_run_interactive_wizard_choice_1(self, mock_status, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)
        mock_status.assert_called_once()

    @patch('builtins.input', side_effect=['2', 'java', 'rust'])
    @patch('sys.stdin.readlines', return_value=['class A {}'])
    @patch('elmos_cli.interactive.run_composite_pipeline', return_value={'status': 'SUCCESS', 'stages': {'polyglot_transform': {'target_code': 'struct A;'}}})
    def test_run_interactive_wizard_choice_2(self, mock_pipe, mock_stdin, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)
        mock_pipe.assert_called_once()

    @patch('builtins.input', side_effect=['2', '', ''])
    @patch('sys.stdin.readlines', side_effect=RuntimeError("stdin failure"))
    @patch('elmos_cli.interactive.run_composite_pipeline', return_value={'status': 'SUCCESS', 'stages': {}})
    def test_run_interactive_wizard_choice_2_default(self, mock_pipe, mock_stdin, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)
        mock_pipe.assert_called_once()

    @patch('builtins.input', side_effect=['3', 'forall x: P(x)'])
    def test_run_interactive_wizard_choice_3(self, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)
        _mock_poly_service.check_smt_formula.assert_called()

    @patch('builtins.input', side_effect=['3', ''])
    def test_run_interactive_wizard_choice_3_default(self, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)

    @patch('builtins.input', return_value='4')
    @patch('elmos_cli.interactive.run_composite_pipeline', return_value={'status': 'SUCCESS', 'stages': {}})
    @patch('elmos_cli.interactive.generate_executive_html_report')
    def test_run_interactive_wizard_choice_4(self, mock_html, mock_pipe, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)
        mock_pipe.assert_called_once()
        mock_html.assert_called_once()

    @patch('builtins.input', return_value='5')
    @patch('elmos_cli.interactive.run_composite_pipeline', return_value={'status': 'SUCCESS', 'stages': {}})
    @patch('elmos_cli.interactive.generate_executive_html_report')
    def test_run_interactive_wizard_choice_5(self, mock_html, mock_pipe, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)
        mock_pipe.assert_called_once()
        mock_html.assert_called_once()

    @patch('builtins.input', return_value='')
    @patch('elmos_cli.interactive.run_composite_pipeline', return_value={'status': 'SUCCESS', 'stages': {}})
    @patch('elmos_cli.interactive.generate_executive_html_report')
    def test_run_interactive_wizard_default_choice_4(self, mock_html, mock_pipe, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)
        mock_pipe.assert_called_once()
        mock_html.assert_called_once()
