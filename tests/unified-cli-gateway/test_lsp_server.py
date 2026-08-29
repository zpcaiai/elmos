"""Unit and integration tests for ELMOS LSP (Language Server Protocol) Gateway."""

from __future__ import annotations

import io
import json
import unittest

from elmos_cli.lsp_server import ElmosLanguageServer, run_lsp_server


class ElmosLspServerTests(unittest.TestCase):
    """Test JSON-RPC 2.0 LSP server request handling and lifecycle."""

    def setUp(self) -> None:
        self.server = ElmosLanguageServer()

    def test_json_rpc_framing_read_write(self) -> None:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        raw = json.dumps(payload).encode("utf-8")
        stream_in = io.BytesIO(f"Content-Length: {len(raw)}\r\n\r\n".encode("utf-8") + raw)
        
        msg = self.server.read_message(stream_in)
        self.assertIsNotNone(msg)
        self.assertEqual(msg["method"], "initialize")
        self.assertEqual(msg["id"], 1)

        stream_out = io.BytesIO()
        self.server.send_message({"jsonrpc": "2.0", "id": 1, "result": "OK"}, stream=stream_out)
        output_bytes = stream_out.getvalue()
        self.assertTrue(output_bytes.startswith(b"Content-Length:"))
        self.assertIn(b'"result": "OK"', output_bytes)

    def test_initialize_and_capabilities(self) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": 100,
            "method": "initialize",
            "params": {"capabilities": {"workspace": {}}},
        }
        resp = self.server.handle_request(req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp["id"], 100)
        caps = resp["result"]["capabilities"]
        self.assertTrue(caps["hoverProvider"])
        self.assertTrue(caps["codeActionProvider"])
        self.assertIn("elmos.modernize.csharp", caps["executeCommandProvider"]["commands"])

    def test_text_document_hover_and_invariants(self) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": 101,
            "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": "file:///workspace/OrderService.java"},
                "position": {"line": 15, "character": 4},
            },
        }
        resp = self.server.handle_request(req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp["id"], 101)
        contents = resp["result"]["contents"]
        self.assertEqual(contents["kind"], "markdown")
        self.assertIn("ELMOS Autonomous Intelligence", contents["value"])
        self.assertIn("Line**: `16`", contents["value"])

    def test_text_document_code_actions(self) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": 102,
            "method": "textDocument/codeAction",
            "params": {
                "textDocument": {"uri": "file:///workspace/LegacyService.java"},
                "range": {"start": {"line": 0, "character": 0}, "end": {"line": 1, "character": 0}},
                "context": {"diagnostics": []},
            },
        }
        resp = self.server.handle_request(req)
        self.assertIsNotNone(resp)
        actions = resp["result"]
        self.assertGreaterEqual(len(actions), 3)
        titles = [a["title"] for a in actions]
        self.assertTrue(any("Modernize file to C#" in t for t in titles))
        self.assertTrue(any("Synthesize Lean 4" in t for t in titles))

    def test_custom_elmos_transform_snippet(self) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": 103,
            "method": "elmos/transform",
            "params": {
                "source_code": 'public void log() { System.out.println("Hello"); }',
                "source_lang": "java",
                "target_lang": "csharp",
            },
        }
        resp = self.server.handle_request(req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp["result"]["status"], "VERIFIED_PASS")
        self.assertIn("Console.WriteLine", resp["result"]["transformed_code"])

    def test_diagnostics_on_legacy_patterns(self) -> None:
        out_stream = io.BytesIO()
        server = ElmosLanguageServer(out_stream=out_stream)
        legacy_code = "Vector v = new Vector();\ngoto error_handler;\n"
        server.handle_notification({
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": "file:///workspace/Legacy.java",
                    "text": legacy_code,
                }
            }
        })
        out = out_stream.getvalue()
        self.assertIn(b"textDocument/publishDiagnostics", out)
        self.assertIn(b"Legacy synchronized collection", out)
        self.assertIn(b"Unstructured control flow", out)


if __name__ == "__main__":
    unittest.main()
