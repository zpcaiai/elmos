"""Safety and receipt contracts for local PostgreSQL qualification."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from types import ModuleType

import jsonschema
import pytest

from elmos_build_cache import schemas
from elmos_build_cache.errors import SchemaInvalid

ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "qualify_local_postgres.py"
SCHEMA_NAME = "local-postgres-qualification-receipt"
SCHEMA_PATH = ROOT / "schemas" / f"{SCHEMA_NAME}.schema.json"
PACKAGED_SCHEMA_PATH = ROOT / "src" / "elmos_build_cache" / "_data" / "schemas" / f"{SCHEMA_NAME}.schema.json"


def _load_tool() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "elmos_build_cache_local_postgres_qualification",
        TOOL_PATH,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _arguments(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "expected_source_revision": None,
        "executor_id": "local-executor",
        "authorization_ref": "local-disposable-authorization",
        "confirm_disposable": "I_CONFIRM_DISPOSABLE_LOCAL_POSTGRES_ONLY",
        "postgres_bin": Path("/opt/homebrew/opt/postgresql@17/bin"),
        "output_parent": Path("/tmp"),
        "metadata_selector": [],
        "slo_selector": [],
        "timeout_seconds": 900,
        "print_plan": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _receipt() -> dict[str, object]:
    digest_a = "sha256:" + "a" * 64
    digest_b = "sha256:" + "b" * 64
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.build-cache.local-postgres-qualification-receipt/v1",
        "receipt_id": "elmos-bc-pg-qualification-example",
        "evidence_class": "LOCAL_EXECUTED_SELF_ATTESTED",
        "status": "PASSED_LOCAL_METADATA_ONLY",
        "started_at": "2026-08-26T00:00:00Z",
        "finished_at": "2026-08-26T00:00:02Z",
        "source": {
            "revision_source": "git-rev-parse-head",
            "revision": "a" * 40,
            "expected_revision": None,
            "dirty": True,
            "manifest_sha256_before": digest_a,
            "manifest_sha256_after": digest_a,
            "stable": True,
        },
        "environment": {
            "os": "darwin",
            "os_release": "25.0",
            "architecture": "arm64",
            "python": "3.12.12",
            "uv": "uv 0.11.16",
            "pytest": "8.4.1",
            "psycopg": "3.3.4",
            "postgres_server_binary": "postgres (PostgreSQL) 17.5",
            "postgres_client": "psql (PostgreSQL) 17.5",
            "postgres_runtime_observed": True,
            "server_version_num": "170005",
            "server_version": "17.5",
            "server_encoding": "UTF8",
            "lc_collate": "C",
            "lc_ctype": "C",
            "timezone": "GMT",
            "fsync": "on",
            "synchronous_commit": "on",
            "listen_addresses": "",
            "extensions": ["plpgsql=1.0"],
            "socket_only": True,
            "data_class": "SYNTHETIC_TEST_FIXTURES",
            "production_database": False,
        },
        "safety": {
            "authorization_ref": "local-disposable-authorization",
            "disposable_confirmation": True,
            "temp_root_kind": "mkdtemp-under-/tmp",
            "socket_only": True,
            "external_dsn_accepted": False,
            "dsn_recorded": False,
            "secrets_recorded": False,
            "production_database": False,
            "production_writes": False,
            "durability_weakened": False,
        },
        "test_runs": [
            {
                "name": "metadata-store",
                "selectors": ["tests/test_metadata_store_contract.py"],
                "argv": ["python", "-m", "pytest", "tests/test_metadata_store_contract.py"],
                "status": "PASSED",
                "exit_code": 0,
                "counts": {
                    "passed": 65,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                    "xfailed": 0,
                    "xpassed": 0,
                    "collected": 65,
                },
                "raw_log_role": "pytest-metadata-store",
                "raw_log_path": "pytest-metadata-store.log",
            }
        ],
        "tests": {
            "metadata_store_live_postgres": "PASSED",
            "slo_service_live_postgres": "NOT_RUN",
        },
        "database": {
            "migration_ledger_sha256": digest_a,
            "schema_introspection_sha256": digest_b,
        },
        "raw_evidence": [
            {
                "role": "pytest-metadata-store",
                "path": "pytest-metadata-store.log",
                "media_type": "text/plain",
                "size_bytes": 42,
                "sha256": digest_b,
            }
        ],
        "executor": {"identity": "local-executor", "role": "executor"},
        "independent_verifier": {"state": "NOT_RUN"},
        "external_states": {
            "ci": "NOT_RUN",
            "production": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
        "limitations": [
            "SLO_SERVICE_LIVE_POSTGRES_NOT_RUN",
            "SELF_ATTESTED_LOCAL_ENGINEERING_EVIDENCE",
        ],
        "failure": {"state": "NOT_APPLICABLE", "error_code": None},
        "teardown": {
            "status": "COMPLETE",
            "postgres_stopped": True,
            "stop_exit_code": 0,
            "data_directory_removed": True,
            "socket_directory_removed": True,
            "temporary_home_removed": True,
        },
        "exit_code": 0,
        "receipt_sha256": digest_a,
    }


def test_qualification_receipt_schema_is_exact_packaged_and_meta_schema_valid() -> None:
    assert SCHEMA_PATH.read_bytes() == PACKAGED_SCHEMA_PATH.read_bytes()
    jsonschema.Draft202012Validator.check_schema(schemas.load_schema(SCHEMA_NAME))


def test_metadata_only_receipt_preserves_the_unrun_slo_and_external_boundaries() -> None:
    receipt = _receipt()

    schemas.validate(SCHEMA_NAME, receipt)

    assert receipt["tests"] == {
        "metadata_store_live_postgres": "PASSED",
        "slo_service_live_postgres": "NOT_RUN",
    }
    assert receipt["external_states"] == {
        "ci": "NOT_RUN",
        "production": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def test_receipt_digest_is_recomputable_and_the_tool_self_validates_schema() -> None:
    tool = _load_tool()
    receipt = _receipt()
    receipt["receipt_sha256"] = tool._receipt_digest(receipt)

    tool._validate_receipt(receipt)
    assert receipt["receipt_sha256"] == tool._receipt_digest(receipt)

    receipt["limitations"].append("MUTATED_AFTER_DIGEST")
    with pytest.raises(RuntimeError, match="DIGEST_INVALID"):
        tool._validate_receipt(receipt)


def test_receipt_rejects_dsn_fields_and_false_safety_claims() -> None:
    with_dsn = copy.deepcopy(_receipt())
    with_dsn["dsn"] = "postgresql://must-not-be-recorded"
    with pytest.raises(SchemaInvalid):
        schemas.validate(SCHEMA_NAME, with_dsn)

    unsafe = copy.deepcopy(_receipt())
    assert isinstance(unsafe["safety"], dict)
    unsafe["safety"]["dsn_recorded"] = True
    with pytest.raises(SchemaInvalid):
        schemas.validate(SCHEMA_NAME, unsafe)


def test_qualification_plan_is_socket_only_durable_and_metadata_only_by_default() -> None:
    tool = _load_tool()

    plan = tool._plan(_arguments())

    assert plan["metadata_selectors"] == ["tests/test_metadata_store_contract.py"]
    assert plan["slo_selectors"] == []
    assert plan["slo_service_live_postgres"] == "NOT_RUN"
    assert plan["socket_only"] is True
    assert plan["external_dsn_accepted"] is False
    assert plan["dsn_recorded"] is False
    assert plan["secrets_recorded"] is False
    assert plan["fsync"] == "on"
    assert plan["synchronous_commit"] == "on"


def test_qualification_plan_accepts_only_the_exact_test_file_for_each_group() -> None:
    tool = _load_tool()
    slo_node = "tests/test_slo_service.py::test_live_postgres_contract"

    plan = tool._plan(_arguments(slo_selector=[slo_node]))
    assert plan["slo_selectors"] == [slo_node]
    assert plan["slo_service_live_postgres"] == "PLANNED"

    with pytest.raises(ValueError, match="test_metadata_store_contract.py"):
        tool._plan(_arguments(metadata_selector=[slo_node]))
    with pytest.raises(ValueError, match="test_slo_service.py"):
        tool._plan(_arguments(slo_selector=["tests/test_metadata_store_contract.py::test_example"]))
    with pytest.raises(ValueError, match="identifier-safe"):
        tool._plan(
            _arguments(slo_selector=["tests/test_slo_service.py::test_live_postgres_contract[postgresql://secret]"])
        )
    with pytest.raises(ValueError, match="secret-like"):
        tool._plan(_arguments(authorization_ref="secret-material"))


def test_plan_rejects_an_external_output_parent() -> None:
    tool = _load_tool()

    with pytest.raises(ValueError, match="below /tmp"):
        tool._plan(_arguments(output_parent=Path("/Users")))


def test_print_plan_does_not_create_the_requested_output_parent(capsys: pytest.CaptureFixture[str]) -> None:
    tool = _load_tool()
    output_parent = Path("/tmp") / f"elmos-bc-print-plan-{uuid.uuid4().hex}"
    assert not output_parent.exists()

    result = tool.main(
        [
            "--executor-id",
            "local-executor",
            "--authorization-ref",
            "local-disposable-authorization",
            "--confirm-disposable",
            "I_CONFIRM_DISPOSABLE_LOCAL_POSTGRES_ONLY",
            "--output-parent",
            str(output_parent),
            "--print-plan",
        ]
    )

    assert result == 0
    assert not output_parent.exists()
    assert '"source_revision": "READ_FROM_GIT_AT_EXECUTION"' in capsys.readouterr().out


def test_safe_environment_uses_an_isolated_home_and_never_inherits_pythonpath(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _load_tool()
    isolated_home = tmp_path / "qualification-home"
    monkeypatch.setenv("HOME", "/Users/private-home")
    monkeypatch.setenv("PYTHONPATH", "/private/injected-pythonpath")
    monkeypatch.setenv("API_TOKEN", "must-not-be-inherited")

    environment = tool._safe_environment(isolated_home)

    assert environment["HOME"] == str(isolated_home.resolve())
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert "PYTHONPATH" not in environment
    assert "API_TOKEN" not in environment


def test_git_source_identity_is_observed_not_accepted_from_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _load_tool()
    calls: list[list[str]] = []

    monkeypatch.setattr(tool, "_required_command", lambda *_args, **_kwargs: Path("/usr/bin/git"))

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        output = "a" * 40 + "\n" if argv[-2:] == ["rev-parse", "HEAD"] else " M file\n"
        return subprocess.CompletedProcess(argv, 0, output, "")

    monkeypatch.setattr(tool, "_must_run", fake_run)
    state = tool._git_source_state(environment=tool._safe_environment())

    assert state == {"revision": "a" * 40, "dirty": True}
    assert any(command[-2:] == ["rev-parse", "HEAD"] for command in calls)
    parser_destinations = {action.dest for action in tool._build_parser()._actions}
    assert "source_revision" not in parser_destinations
    assert "expected_source_revision" in parser_destinations


def test_uv_version_is_actively_probed_not_read_from_an_environment_claim() -> None:
    source = TOOL_PATH.read_text(encoding="utf-8")
    assert "UV_VERSION" not in source
    assert '"uv": _command_version(' in source


def test_prestart_failure_still_emits_a_schema_valid_blocked_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _load_tool()
    fake_binaries = {name: Path("/not-used") / name for name in ("createdb", "initdb", "pg_ctl", "postgres", "psql")}
    monkeypatch.setattr(tool, "_required_binaries", lambda _path: fake_binaries)

    def unavailable_git(**_kwargs: object) -> dict[str, object]:
        raise RuntimeError("GIT_IDENTITY_UNAVAILABLE")

    monkeypatch.setattr(tool, "_git_source_state", unavailable_git)
    with tempfile.TemporaryDirectory(prefix="elmos-bc-receipt-test-", dir="/tmp") as parent:
        exit_code, evidence_root = tool.execute(_arguments(output_parent=Path(parent), print_plan=False))
        document = json.loads((evidence_root / "receipt.json").read_text(encoding="utf-8"))

        assert exit_code == 2
        assert document["status"] == "BLOCKED_PROVISIONING"
        assert document["tests"] == {
            "metadata_store_live_postgres": "NOT_RUN",
            "slo_service_live_postgres": "NOT_RUN",
        }
        assert document["teardown"]["status"] == "COMPLETE"
        jsonschema.Draft202012Validator.check_schema(schemas.load_schema(SCHEMA_NAME))
        tool._validate_receipt(document)


def test_pytest_timeout_log_redacts_dsn_socket_and_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _load_tool()
    with tempfile.TemporaryDirectory(prefix="elmos-bc-timeout-test-", dir="/tmp") as parent:
        root = Path(parent)

        class FakeCluster:
            dsn = "host=/tmp/private-socket port=6543 dbname=secret"
            socket_directory = Path("/tmp/private-socket")
            process_environment = tool._safe_environment(root / "home")

            def __init__(self) -> None:
                self.root = root

        def timeout(*_args: object, **_kwargs: object) -> None:
            raise subprocess.TimeoutExpired(
                cmd=["pytest"],
                timeout=1,
                output="host=/tmp/private-socket token=top-secret",
            )

        monkeypatch.setattr(tool, "_run", timeout)
        result = tool._run_pytest(
            name="metadata-store",
            selectors=["tests/test_metadata_store_contract.py"],
            cluster=FakeCluster(),
            timeout=1,
        )
        log = (root / "pytest-metadata-store.log").read_text(encoding="utf-8")

        assert result["status"] == "TIMED_OUT"
        assert result["exit_code"] == 124
        assert "/tmp/private-socket" not in log
        assert "top-secret" not in log
        assert "host=[REDACTED_SOCKET_DIRECTORY]" in log or "[REDACTED_LOCAL_RUNTIME]" in log


def test_tool_has_no_external_dsn_option_and_redacts_connection_material() -> None:
    tool = _load_tool()
    parser_destinations = {action.dest for action in tool._build_parser()._actions}
    assert not {"dsn", "database_url", "postgres_dsn"} & parser_destinations

    dsn = "postgresql://user:secret@127.0.0.1:5432/example"
    redacted = tool._redact(f"dsn={dsn} password=hunter2 token=abc", dsn)
    assert dsn not in redacted
    assert "hunter2" not in redacted
    assert "token=abc" not in redacted
