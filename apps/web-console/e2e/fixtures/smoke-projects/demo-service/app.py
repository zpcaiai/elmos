"""Batch 46 e2e fixture service. Standard library only: the smoke run must not
depend on network access to install anything."""
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("SMOKE_PORT") or os.environ.get("PORT") or 5000)
DB = os.environ.get("SMOKE_SQLITE_PATH")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._send(200, {"status": "ok"})
        if self.path.startswith("/customers"):
            rows = []
            if DB and os.path.exists(DB):
                connection = sqlite3.connect(DB)
                rows = [{"id": row[0], "email": row[1]}
                        for row in connection.execute("SELECT id, email FROM customers")]
                connection.close()
            return self._send(200, {"items": rows})
        return self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
