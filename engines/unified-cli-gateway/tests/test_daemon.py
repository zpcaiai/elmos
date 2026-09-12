import json
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch, MagicMock
import sys

class MockAnalyzer:
    @staticmethod
    def analyze_code_snippet(code, name):
        return {
            "needs_healing": True,
            "diagnostics": ["error1"],
            "patch_sha256": "abcdef",
            "git_patch": "patch_content",
            "review_markdown": "review"
        }

sys.modules['elmos_polyglot_compiler.self_healing'] = MagicMock()
sys.modules['elmos_polyglot_compiler.self_healing'].SelfHealingAnalyzer = MockAnalyzer

from elmos_cli.daemon import process_webhook_event, run_daemon, WebhookHandler

class TestDaemon(unittest.TestCase):
    def test_process_webhook_event_needs_healing(self):
        event = {
            "action": "opened",
            "pull_request": {"number": 123},
            "repository": {"full_name": "test/repo"},
            "changed_file_content": "public class Test {}",
            "changed_file_path": "Test.java"
        }
        with patch('elmos_cli.daemon.SelfHealingAnalyzer', MockAnalyzer):
            res = process_webhook_event(event)
        self.assertEqual(res["status"], "PROCESSED_WITH_HEALING")
        self.assertEqual(res["pr_number"], 123)
        self.assertEqual(res["repo"], "test/repo")
        self.assertEqual(res["auto_fix_applied"], True)

    def test_process_webhook_event_clean(self):
        event = {
            "event_type": "push",
            "pr_id": 456
        }
        mock_clean = MagicMock()
        mock_clean.analyze_code_snippet.return_value = {
            "needs_healing": False,
            "diagnostics": [],
            "patch_sha256": "",
            "git_patch": "",
            "review_markdown": ""
        }
        with patch('elmos_cli.daemon.SelfHealingAnalyzer', mock_clean):
            res = process_webhook_event(event)
        self.assertEqual(res["status"], "PROCESSED_CLEAN")
        self.assertEqual(res["pr_number"], 456)
        self.assertEqual(res["repo"], "enterprise/core-service")
        self.assertEqual(res["event_type"], "push")
        self.assertEqual(res["auto_fix_applied"], False)

    def test_run_daemon_simulate_event_not_found(self):
        res = run_daemon(simulate_event_path="/does/not/exist.json")
        self.assertEqual(res, 1)

    def test_run_daemon_simulate_event(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            json.dump({"action": "test"}, f)
            path = f.name
        try:
            with patch('elmos_cli.daemon.process_webhook_event', return_value={}):
                res = run_daemon(simulate_event_path=path)
            self.assertEqual(res, 0)
        finally:
            Path(path).unlink()

    @patch('elmos_cli.daemon.HTTPServer')
    def test_run_daemon_serve_forever(self, mock_server):
        instance = mock_server.return_value
        res = run_daemon()
        self.assertEqual(res, 0)
        instance.serve_forever.assert_called_once()

    @patch('elmos_cli.daemon.HTTPServer')
    def test_run_daemon_keyboard_interrupt(self, mock_server):
        instance = mock_server.return_value
        instance.serve_forever.side_effect = KeyboardInterrupt
        res = run_daemon()
        self.assertEqual(res, 0)

    def test_webhook_handler_get_health(self):
        handler = MagicMock()
        handler.path = "/health"
        handler.wfile = MagicMock()
        WebhookHandler.do_GET(handler)
        handler.send_response.assert_called_with(200)

    def test_webhook_handler_get_404(self):
        handler = MagicMock()
        handler.path = "/other"
        handler.wfile = MagicMock()
        WebhookHandler.do_GET(handler)
        handler.send_response.assert_called_with(404)

    def test_webhook_handler_post_webhook(self):
        handler = MagicMock()
        handler.path = "/webhook"
        handler.headers = {"Content-Length": "2"}
        handler.rfile.read.return_value = b"{}"
        handler.wfile = MagicMock()
        with patch('elmos_cli.daemon.process_webhook_event', return_value={}):
            WebhookHandler.do_POST(handler)
        handler.send_response.assert_called_with(200)

    def test_webhook_handler_post_error(self):
        handler = MagicMock()
        handler.path = "/webhook"
        handler.headers = {"Content-Length": "2"}
        handler.rfile.read.return_value = b"invalid json"
        handler.wfile = MagicMock()
        WebhookHandler.do_POST(handler)
        handler.send_response.assert_called_with(400)

    def test_webhook_handler_post_404(self):
        handler = MagicMock()
        handler.path = "/other"
        handler.headers = {"Content-Length": "2"}
        handler.wfile = MagicMock()
        WebhookHandler.do_POST(handler)
        handler.send_response.assert_called_with(404)
