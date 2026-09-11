import json
import io
import unittest
from unittest.mock import patch, MagicMock

from elmos_cli.lsp_server import ElmosLanguageServer, run_lsp_server

class TestLSPServer(unittest.TestCase):
    def setUp(self):
        self.in_stream = io.BytesIO()
        self.out_stream = io.BytesIO()
        self.server = ElmosLanguageServer(in_stream=self.in_stream, out_stream=self.out_stream)

    def test_send_message(self):
        self.server.send_message({"test": "ok"})
        out = self.out_stream.getvalue().decode("utf-8")
        self.assertIn("Content-Length:", out)
        self.assertIn('{"test": "ok"}', out)

    def test_send_response_result(self):
        self.server.send_response(1, result="success")
        out = json.loads(self.out_stream.getvalue().decode("utf-8").split("\r\n\r\n")[1])
        self.assertEqual(out["id"], 1)
        self.assertEqual(out["result"], "success")
        self.assertNotIn("error", out)

    def test_send_response_error(self):
        self.server.send_response(2, error="bad")
        out = json.loads(self.out_stream.getvalue().decode("utf-8").split("\r\n\r\n")[1])
        self.assertEqual(out["id"], 2)
        self.assertEqual(out["error"], "bad")
        self.assertNotIn("result", out)

    def test_send_notification(self):
        self.server.send_notification("test/notif", {"a": 1})
        out = json.loads(self.out_stream.getvalue().decode("utf-8").split("\r\n\r\n")[1])
        self.assertEqual(out["method"], "test/notif")
        self.assertEqual(out["params"]["a"], 1)

    def test_handle_request_initialize(self):
        req = {"id": 1, "method": "initialize", "params": {"capabilities": {"cap": True}}}
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 1)
        self.assertIn("capabilities", res["result"])
        self.assertEqual(self.server.client_capabilities["cap"], True)

    def test_handle_request_shutdown(self):
        req = {"id": 2, "method": "shutdown"}
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 2)
        self.assertIsNone(res["result"])
        self.assertFalse(self.server.is_running)

    def test_handle_request_hover(self):
        req = {"id": 3, "method": "textDocument/hover", "params": {"textDocument": {"uri": "file://test.java"}}}
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 3)
        self.assertEqual(res["result"]["contents"]["kind"], "markdown")
        self.assertIn("file://test.java", res["result"]["contents"]["value"])

    def test_handle_request_code_action(self):
        req = {"id": 4, "method": "textDocument/codeAction", "params": {"textDocument": {"uri": "file://test.java"}}}
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 4)
        self.assertGreater(len(res["result"]), 0)

    def test_handle_request_execute_command(self):
        req = {"id": 5, "method": "workspace/executeCommand", "params": {"command": "cmd", "arguments": ["uri"]}}
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 5)
        self.assertEqual(res["result"]["command"], "cmd")
        self.assertEqual(res["result"]["uri"], "uri")

    def test_handle_request_transform(self):
        req = {"id": 6, "method": "elmos/transform", "params": {"source_code": "System.out.println", "source_lang": "java", "target_lang": "csharp"}}
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 6)
        self.assertIn("Console.WriteLine", res["result"]["transformed_code"])

    def test_handle_request_unknown(self):
        req = {"id": 7, "method": "unknown"}
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 7)
        self.assertEqual(res["error"]["code"], -32601)

    def test_handle_notification_did_open(self):
        msg = {"method": "textDocument/didOpen", "params": {"textDocument": {"uri": "file1", "text": "test"}}}
        self.server.handle_notification(msg)
        self.assertEqual(self.server.documents["file1"], "test")

    def test_handle_notification_did_change(self):
        msg = {"method": "textDocument/didChange", "params": {"textDocument": {"uri": "file1"}, "contentChanges": [{"text": "new text"}]}}
        self.server.handle_notification(msg)
        self.assertEqual(self.server.documents["file1"], "new text")

    def test_handle_notification_did_close(self):
        self.server.documents["file1"] = "test"
        msg = {"method": "textDocument/didClose", "params": {"textDocument": {"uri": "file1"}}}
        self.server.handle_notification(msg)
        self.assertNotIn("file1", self.server.documents)

    def test_handle_notification_exit(self):
        msg = {"method": "exit"}
        self.server.handle_notification(msg)
        self.assertFalse(self.server.is_running)

    def test_publish_diagnostics(self):
        self.server.publish_diagnostics("file1", "Vector v = new Vector();\ngoto label;\n")
        out = json.loads(self.out_stream.getvalue().decode("utf-8").split("\r\n\r\n")[1])
        self.assertEqual(out["method"], "textDocument/publishDiagnostics")
        self.assertEqual(out["params"]["uri"], "file1")
        self.assertEqual(len(out["params"]["diagnostics"]), 2)
        
    @patch("elmos_cli.lsp_server.ElmosLanguageServer.serve_stdio")
    def test_run_lsp_server(self, mock_serve):
        res = run_lsp_server()
        self.assertEqual(res, 0)
        mock_serve.assert_called_once()

    def test_read_message_empty(self):
        self.assertIsNone(self.server.read_message())
