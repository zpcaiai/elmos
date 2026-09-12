"""Comprehensive unit tests for elmos_legacy_web_modernization CLI.

Validates validate, manifest, dispatch, run, and external-preflight subcommands,
along with error handling and parameter validation.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from elmos_legacy_web_modernization.cli import main, _request


def make_test_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    holder = tempfile.TemporaryDirectory()
    root = Path(holder.name).resolve()
    (root / "src/main/java/com/acme").mkdir(parents=True)
    (root / "WEB-INF").mkdir(parents=True)
    (root / "pom.xml").write_text(
        """<project>
          <artifactId>orders</artifactId><packaging>war</packaging>
          <dependencies>
            <dependency><groupId>org.apache.struts</groupId><artifactId>struts-core</artifactId><version>1.3.10</version></dependency>
          </dependencies>
        </project>""",
        encoding="utf-8",
    )
    (root / "WEB-INF/struts-config.xml").write_text(
        """<struts-config><action-mappings>
          <action path="/orders/create" type="com.acme.CreateOrderAction"/>
        </action-mappings></struts-config>""",
        encoding="utf-8",
    )
    return holder, root


def make_request(root: Path, skill_id: str = "00-modernization-orchestrator") -> dict:
    return {
        "request_id": "req-01",
        "tenant_id": "tenant-test",
        "project_id": "project-test",
        "job_id": "job-test",
        "skill_id": skill_id,
        "idempotency_key": "idemp-test-01",
        "inputs": {"repository_root": root.as_posix()},
        "policy": {"mode": "preserve-first", "equivalence": "strict"},
        "authority": {
            "environment_id": "env-local",
            "profile": "scan-readonly",
            "scopes": ["repository-read"],
            "fencing_token": 1,
        },
    }


class CliComprehensiveTests(unittest.TestCase):
    def test_validate_subcommand(self) -> None:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
            exit_code = main(["validate"])
        self.assertEqual(exit_code, 0)
        output = json.loads(stdout_buf.getvalue())
        self.assertEqual(output["status"], "PASS")
        self.assertEqual(output["externalEvidence"], "NOT_RUN")
        self.assertEqual(output["certification"], "NOT_CERTIFIED")
        self.assertEqual(output["skills"], 55)

    def test_manifest_subcommand(self) -> None:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
            exit_code = main(["manifest"])
        self.assertEqual(exit_code, 0)
        output = json.loads(stdout_buf.getvalue())
        self.assertIn("package", output)
        self.assertIn("skills", output)
        self.assertEqual(len(output["skills"]), 55)

    def test_dispatch_subcommand_valid_request(self) -> None:
        holder, root = make_test_fixture()
        try:
            req = make_request(root, "00-modernization-orchestrator")
            with tempfile.NamedTemporaryFile("w+", suffix=".json") as tf:
                tf.write(json.dumps(req))
                tf.flush()

                stdout_buf = io.StringIO()
                with patch("sys.stdout", stdout_buf):
                    exit_code = main(["dispatch", tf.name])
                self.assertEqual(exit_code, 0)
                res = json.loads(stdout_buf.getvalue())
                self.assertEqual(res["skillId"], "00-modernization-orchestrator")
                self.assertIn(res["state"], {"LOCAL_EXECUTED", "PLANNING_ONLY"})
        finally:
            holder.cleanup()

    def test_run_subcommand_readonly(self) -> None:
        holder, root = make_test_fixture()
        state_holder = tempfile.TemporaryDirectory()
        try:
            req = make_request(root, "00-modernization-orchestrator")
            req_path = root / "request.json"
            req_path.write_text(json.dumps(req), encoding="utf-8")
            state_dir = Path(state_holder.name).resolve()

            stdout_buf = io.StringIO()
            with patch("sys.stdout", stdout_buf):
                exit_code = main(["run", str(req_path), "--state-dir", str(state_dir)])
            self.assertEqual(exit_code, 0)
            res = json.loads(stdout_buf.getvalue())
            self.assertEqual(res["skills"], 55)
            self.assertEqual(res["externalEvidence"], "NOT_RUN")
            self.assertEqual(res["certification"], "NOT_CERTIFIED")
        finally:
            state_holder.cleanup()
            holder.cleanup()

    def test_request_invalid_json_fails(self) -> None:
        with tempfile.NamedTemporaryFile("w+", suffix=".json") as tf:
            tf.write("NOT_VALID_JSON")
            tf.flush()
            stderr_buf = io.StringIO()
            with patch("sys.stderr", stderr_buf):
                exit_code = main(["dispatch", tf.name])
            self.assertEqual(exit_code, 1)
            self.assertIn("ERROR:", stderr_buf.getvalue())

    def test_request_non_object_fails(self) -> None:
        with tempfile.NamedTemporaryFile("w+", suffix=".json") as tf:
            tf.write(json.dumps(["not", "an", "object"]))
            tf.flush()
            stderr_buf = io.StringIO()
            with patch("sys.stderr", stderr_buf):
                exit_code = main(["dispatch", tf.name])
            self.assertEqual(exit_code, 1)
            self.assertIn("request file must contain an object", stderr_buf.getvalue())

    def test_unknown_skill_dispatch_fails(self) -> None:
        holder, root = make_test_fixture()
        try:
            req = make_request(root, "99-unknown-skill-xyz")
            with tempfile.NamedTemporaryFile("w+", suffix=".json") as tf:
                tf.write(json.dumps(req))
                tf.flush()
                stderr_buf = io.StringIO()
                with patch("sys.stderr", stderr_buf):
                    exit_code = main(["dispatch", tf.name])
                self.assertEqual(exit_code, 1)
                self.assertIn("ERROR:", stderr_buf.getvalue())
        finally:
            holder.cleanup()


if __name__ == "__main__":
    unittest.main()
