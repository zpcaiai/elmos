import sys
from unittest.mock import patch, MagicMock

sys.modules['elmos_polyglot_compiler'] = MagicMock()
sys.modules['elmos_polyglot_compiler.service'] = MagicMock()

import json
import unittest
from elmos_cli.interactive import run_interactive_wizard

class TestInteractive(unittest.TestCase):
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
    @patch('elmos_cli.interactive._get_global_status', create=True, return_value={"status": "ok"})
    def test_run_interactive_wizard_choice_1(self, mock_status, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)

    @patch('builtins.input', side_effect=['2', 'java', 'rust'])
    @patch('sys.stdin.readlines', return_value=['class A {}'])
    @patch('elmos_cli.interactive.run_composite_pipeline', return_value={'status': 'SUCCESS'})
    def test_run_interactive_wizard_choice_2(self, mock_pipe, mock_stdin, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)

    @patch('builtins.input', side_effect=['2', '', ''])
    @patch('sys.stdin.readlines', side_effect=Exception("error"))
    @patch('elmos_cli.interactive.run_composite_pipeline', return_value={'status': 'SUCCESS'})
    def test_run_interactive_wizard_choice_2_default(self, mock_pipe, mock_stdin, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)

    @patch('builtins.input', side_effect=['3', 'forall x'])
    def test_run_interactive_wizard_choice_3(self, mock_input):
        import elmos_polyglot_compiler.service
        elmos_polyglot_compiler.service.check_smt_formula = MagicMock(return_value={"sat": True})
        self.assertEqual(run_interactive_wizard(), 0)

    @patch('builtins.input', side_effect=['3', ''])
    def test_run_interactive_wizard_choice_3_default(self, mock_input):
        import elmos_polyglot_compiler.service
        elmos_polyglot_compiler.service.check_smt_formula = MagicMock(return_value={"sat": True})
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
    def test_run_interactive_wizard_choice_default_4(self, mock_html, mock_pipe, mock_input):
        self.assertEqual(run_interactive_wizard(), 0)
        mock_pipe.assert_called_once()
        mock_html.assert_called_once()

