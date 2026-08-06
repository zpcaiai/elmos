"""Batch 46 runnable-smoke pack tests.

Runs with either `pytest tests/batch46` or
`python -m unittest discover -s tests/batch46 -p 'test_*.py'`.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts" / "batch46"
sys.path.insert(0, str(SCRIPTS))

import derive_minimal_data  # noqa: E402
import detect_project_profile  # noqa: E402
import emit_one_click_runner  # noqa: E402
import scaffold_smoke_pack  # noqa: E402
import synthesize_seed_data  # noqa: E402
import validate_smoke_pack  # noqa: E402
from smoke_common import SEED_KEY_BASE  # noqa: E402

SCHEMA_SQL = """
CREATE TABLE customers (
  id SERIAL PRIMARY KEY,
  email VARCHAR(200) NOT NULL UNIQUE,
  display_name VARCHAR(100) NOT NULL,
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE orders (
  id SERIAL PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  total_amount DECIMAL(12,2) NOT NULL,
  status VARCHAR(20) NOT NULL,
  note TEXT
);
"""

APP_PY = '''
import json, os, sqlite3
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
                con = sqlite3.connect(DB)
                cur = con.execute("SELECT id, email FROM customers")
                rows = [{"id": r[0], "email": r[1]} for r in cur.fetchall()]
                con.close()
            return self._send(200, {"items": rows})
        return self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
'''

OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "demo", "version": "1"},
    "paths": {
        "/health": {"get": {"operationId": "health"}},
        "/customers": {"get": {"operationId": "listCustomers"}},
    },
}


def make_project(root: Path, *, engine: str = "postgres", with_start: bool = True) -> Path:
    (root / "db").mkdir(parents=True, exist_ok=True)
    (root / "db" / "schema.sql").write_text(SCHEMA_SQL, encoding="utf-8")
    (root / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    dsn = {
        "postgres": "postgresql://user:pass@localhost:5432/demo",
        "oracle": "jdbc:oracle:thin:@localhost:1521/demo",
    }[engine]
    (root / ".env.example").write_text(
        f"APP_NAME=demo\nDATABASE_URL={dsn}\nAPI_TOKEN=changeme\n", encoding="utf-8"
    )
    (root / "openapi.json").write_text(json.dumps(OPENAPI), encoding="utf-8")
    if with_start:
        (root / "app.py").write_text(APP_PY, encoding="utf-8")
    return root


def scaffold_args(**overrides) -> argparse.Namespace:
    base = dict(
        write=True, seed=None, sample=None, sample_authorization=None,
        accept_scan_findings=False, corpus=None, corpus_max_files=20,
        tools_source=str(SCRIPTS),
    )
    base.update(overrides)
    return argparse.Namespace(**base)


class SmokePackTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="b46-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.project = make_project(self.tmp / "demo")

    # ------------------------------------------------------------ detection
    def test_detects_python_stack_and_datastore(self) -> None:
        profile = detect_project_profile.detect(self.project)
        self.assertEqual(["python"], [s["language"] for s in profile["stacks"]])
        self.assertEqual("flask", profile["stacks"][0]["framework"])
        self.assertEqual(5000, profile["stacks"][0]["default_port"])
        self.assertEqual(["postgres"], [d["engine"] for d in profile["datastores"]])
        self.assertEqual([], profile["unknown"])

    def test_missing_start_command_is_reported_as_unknown(self) -> None:
        project = make_project(self.tmp / "nostart", with_start=False)
        profile = detect_project_profile.detect(project)
        self.assertTrue(any("start command" in item["item"] for item in profile["unknown"]))

    # ---------------------------------------------------------- requirements
    def test_minimal_data_orders_tables_by_dependency(self) -> None:
        profile = detect_project_profile.detect(self.project)
        requirements = derive_minimal_data.derive(self.project, profile)
        order = [d["table"] for d in requirements["datasets"]]
        self.assertLess(order.index("customers"), order.index("orders"))

    def test_nullable_columns_are_not_required(self) -> None:
        profile = detect_project_profile.detect(self.project)
        requirements = derive_minimal_data.derive(self.project, profile)
        orders = next(d for d in requirements["datasets"] if d["table"] == "orders")
        self.assertNotIn("note", orders["required_columns"])
        self.assertIn("status", orders["required_columns"])

    def test_environment_secrets_are_flagged(self) -> None:
        profile = detect_project_profile.detect(self.project)
        requirements = derive_minimal_data.derive(self.project, profile)
        token = next(e for e in requirements["environment"] if e["name"] == "API_TOKEN")
        self.assertTrue(token["secret"])
        self.assertEqual("throwaway-secret", token["smoke_value_strategy"])

    # ------------------------------------------------------------- seed data
    def test_seed_uses_reserved_key_range_and_resolves_foreign_keys(self) -> None:
        scaffold_smoke_pack.scaffold(self.project, scaffold_args())
        sql = (self.project / "smoke" / "seed" / "seed.sql").read_text(encoding="utf-8")
        customer_id = int(sql.split("INSERT INTO customers (id,")[1].split("VALUES (")[1].split(",")[0])
        self.assertGreaterEqual(customer_id, SEED_KEY_BASE)
        self.assertIn(f"VALUES ({customer_id},", sql.split("INSERT INTO orders")[1])

    def test_seed_values_are_obviously_fake(self) -> None:
        scaffold_smoke_pack.scaffold(self.project, scaffold_args())
        sql = (self.project / "smoke" / "seed" / "seed.sql").read_text(encoding="utf-8")
        self.assertIn("SMOKE-", sql)
        self.assertIn("@smoke.invalid", sql)

    def test_seed_manifest_records_provenance_and_no_production_data(self) -> None:
        scaffold_smoke_pack.scaffold(self.project, scaffold_args())
        manifest = json.loads((self.project / "smoke" / "seed-manifest.json").read_text())
        self.assertFalse(manifest["production_data_used"])
        self.assertEqual("ephemeral-disposable", manifest["classification"])
        self.assertEqual({"synthetic-from-contract"},
                         {p["data_source"] for p in manifest["provenance"]})

    def test_sample_source_requires_authorization(self) -> None:
        sample = self.tmp / "sample.json"
        sample.write_text('{"name": "SMOKE-ABC"}', encoding="utf-8")
        detect_project_profile_write(self.project)
        with self.assertRaises(SystemExit):
            synthesize_seed_data.synthesize(
                self.project, scaffold_args(sample=str(sample), sample_authorization=None)
            )

    def test_sample_with_sensitive_values_is_refused(self) -> None:
        sample = self.tmp / "sample.json"
        sample.write_text('{"email": "real.person@bank.example.org", "ssn": "123-45-6789"}', encoding="utf-8")
        detect_project_profile_write(self.project)
        with self.assertRaises(SystemExit):
            synthesize_seed_data.synthesize(
                self.project, scaffold_args(sample=str(sample), sample_authorization="DPA-1")
            )

    def test_sensitive_scan_allows_smoke_shaped_values(self) -> None:
        self.assertEqual([], synthesize_seed_data.scan_sensitive("smoke-abcd1234@smoke.invalid"))
        self.assertTrue(synthesize_seed_data.scan_sensitive("someone@real-company.example.org"))

    # ---------------------------------------------------------------- runner
    def test_entries_are_emitted_with_explicit_availability(self) -> None:
        pack = scaffold_smoke_pack.scaffold(self.project, scaffold_args())
        self.assertEqual("available", pack["entries"]["script"])
        self.assertEqual("available", pack["entries"]["zero-dep"])
        self.assertTrue((self.project / "run-smoke.sh").is_file())
        self.assertTrue(os.access(self.project / "run-smoke.sh", os.X_OK))
        self.assertTrue((self.project / "Makefile.smoke").is_file())
        self.assertTrue((self.project / "smoke" / "tools" / "run_smoke.py").is_file())

    def test_zero_dep_is_unavailable_without_an_approved_substitute(self) -> None:
        project = make_project(self.tmp / "oracle-demo", engine="oracle")
        pack = scaffold_smoke_pack.scaffold(project, scaffold_args())
        self.assertEqual("unavailable", pack["entries"]["zero-dep"])
        runner = json.loads((project / "smoke" / "runner-manifest.json").read_text())
        self.assertIn("oracle", runner["entries"]["zero-dep"]["reason"])

    def test_functional_check_prefers_a_non_readiness_endpoint(self) -> None:
        scaffold_smoke_pack.scaffold(self.project, scaffold_args())
        assertions = json.loads((self.project / "smoke" / "assertions.json").read_text())
        functional = next(c for c in assertions["checks"] if c["id"] == "http-functional")
        self.assertEqual("/customers", functional["path"])

    def test_lease_policy_is_ten_free_minutes_without_auto_renew(self) -> None:
        scaffold_smoke_pack.scaffold(self.project, scaffold_args())
        runner = json.loads((self.project / "smoke" / "runner-manifest.json").read_text())
        policy = runner["lease_policy"]
        self.assertEqual(600, policy["free_quota_seconds"])
        self.assertFalse(policy["auto_renew"])
        self.assertEqual("explicit-only", policy["extend_policy"])

    # ------------------------------------------------------------ validation
    def test_validation_passes_for_a_scaffolded_pack(self) -> None:
        scaffold_smoke_pack.scaffold(self.project, scaffold_args())
        self.assertEqual([], validate_smoke_pack.validate(self.project))

    def test_validation_detects_a_tampered_digest(self) -> None:
        scaffold_smoke_pack.scaffold(self.project, scaffold_args())
        path = self.project / "smoke" / "pack.json"
        pack = json.loads(path.read_text())
        pack["digests"]["profile"] = "sha256:0000"
        path.write_text(json.dumps(pack), encoding="utf-8")
        failures = validate_smoke_pack.validate(self.project)
        self.assertTrue(any("profile digest" in f for f in failures))

    def test_validation_detects_a_missing_seed_artifact(self) -> None:
        scaffold_smoke_pack.scaffold(self.project, scaffold_args())
        (self.project / "smoke" / "seed" / "seed.sql").unlink()
        failures = validate_smoke_pack.validate(self.project)
        self.assertTrue(any("seed.sql" in f for f in failures))

    # ------------------------------------------------------------------ gate
    def test_gate_blocks_when_no_run_has_happened(self) -> None:
        scaffold_smoke_pack.scaffold(self.project, scaffold_args())
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_smoke_gate.py"), str(self.project)],
            capture_output=True, text=True,
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn("blocked", completed.stdout)
        gate = json.loads((self.project / "smoke" / "runtime" / "gate-result.json").read_text())
        self.assertTrue(any("no executed smoke result" in f for f in gate["failures"]))


class LeaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="b46-lease-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_extension_requires_reason_and_actor(self) -> None:
        import smoke_lease

        smoke_lease.new_lease(self.tmp, ttl_seconds=600)
        with self.assertRaises(SystemExit):
            smoke_lease.extend(self.tmp, 60, "", "ethan")
        with self.assertRaises(SystemExit):
            smoke_lease.extend(self.tmp, 60, "debugging", "")

    def test_extension_beyond_free_quota_is_metered(self) -> None:
        import smoke_lease

        smoke_lease.new_lease(self.tmp, ttl_seconds=600)
        lease = smoke_lease.extend(self.tmp, 300, "manual debugging", "ethan")
        self.assertEqual(900, lease["ttl_seconds"])
        self.assertEqual(300, lease["billable_seconds"])
        self.assertTrue(lease["extensions"][-1]["beyond_free_quota"])

    def test_teardown_deletes_tracked_paths_and_is_idempotent(self) -> None:
        import smoke_lease

        lease = smoke_lease.new_lease(self.tmp, ttl_seconds=600)
        watchdog = smoke_lease.LeaseWatchdog(self.tmp, lease, log=lambda _m: None)
        victim = self.tmp / "ephemeral.sqlite"
        victim.write_text("data", encoding="utf-8")
        watchdog.track_path(victim)
        first = watchdog.teardown("expired")
        self.assertFalse(victim.exists())
        self.assertEqual([], first["errors"])
        self.assertIs(first, watchdog.teardown("expired"))
        result = json.loads((self.tmp / "smoke" / "runtime" / "lease-result.json").read_text())
        self.assertEqual("expired", result["state"])
        self.assertTrue(result["teardown_complete"])


@unittest.skipIf(os.environ.get("B46_SKIP_RUNTIME") == "1", "runtime execution disabled")
class RuntimeTestCase(unittest.TestCase):
    """Executes a real one-click run; the whole point of the batch."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="b46-run-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.project = make_project(self.tmp / "demo")
        scaffold_smoke_pack.scaffold(self.project, scaffold_args())

    def _run(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.project / "smoke" / "tools" / "run_smoke.py"),
             "--project", str(self.project), "--no-install", *extra],
            capture_output=True, text=True, timeout=300,
        )

    def test_zero_dep_run_passes_and_reclaims_everything(self) -> None:
        completed = self._run("--entry", "zero-dep", "--ttl", "3")
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        result = json.loads((self.project / "smoke" / "runtime" / "result.json").read_text())
        self.assertEqual("PASS", result["overall"])
        self.assertEqual("expired", result["lease"]["end_reason"])
        self.assertTrue(result["lease"]["teardown_complete"])
        by_id = {c["id"]: c for c in result["checks"]}
        self.assertEqual("PASS", by_id["seed-visible"]["status"])
        self.assertEqual("PASS", by_id["graceful-shutdown"]["status"])
        self.assertEqual("PASS", by_id["lease-teardown"]["status"])
        self.assertFalse((self.project / "smoke" / "runtime" / "smoke.sqlite").exists())

    def test_gate_reports_limited_for_the_zero_dep_entry(self) -> None:
        self._run("--entry", "zero-dep", "--ttl", "3")
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_smoke_gate.py"), str(self.project)],
            capture_output=True, text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        gate = json.loads((self.project / "smoke" / "runtime" / "gate-result.json").read_text())
        self.assertEqual("limited", gate["status"])
        self.assertTrue(any("zero-dependency" in limit for limit in gate["limitations"]))

    def test_edited_evidence_is_rejected_by_the_gate(self) -> None:
        self._run("--entry", "zero-dep", "--ttl", "3")
        path = self.project / "smoke" / "runtime" / "result.json"
        result = json.loads(path.read_text())
        result["required_passed"] = 999
        path.write_text(json.dumps(result), encoding="utf-8")
        subprocess.run([sys.executable, str(SCRIPTS / "run_smoke_gate.py"), str(self.project)],
                       capture_output=True, text=True)
        gate = json.loads((self.project / "smoke" / "runtime" / "gate-result.json").read_text())
        self.assertEqual("blocked", gate["status"])
        self.assertTrue(any("digest does not match" in f for f in gate["failures"]))


def detect_project_profile_write(project: Path) -> None:
    """Materialise profile + requirements so seed synthesis can run standalone."""
    from smoke_common import write_json

    profile = detect_project_profile.detect(project)
    write_json(project / "smoke" / "profile.json", profile)
    write_json(project / "smoke" / "minimal-data-requirements.json",
               derive_minimal_data.derive(project, profile))


if __name__ == "__main__":
    unittest.main()
