"""CLI contract: non-destructive defaults, explicit scope, JSON evidence output."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_build_cache.cli import build_parser, main


def run_cli(capsys: pytest.CaptureFixture[str], *argv: str) -> dict:
    code = main(list(argv))
    captured = capsys.readouterr()
    assert code == 0, captured.err
    return json.loads(captured.out)


def test_every_contract_command_is_implemented() -> None:
    parser = build_parser()
    groups = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    expected = {
        "cache": {"status", "inspect", "explain-miss", "verify", "pin", "unpin", "gc", "explain-retention"},
        "workspace": {"list", "inspect", "recover", "quarantine"},
        "run": {"resume", "pause", "cancel"},
        "artifact": {"materialize"},
        "doctor": {"cache"},
    }
    for group, commands in expected.items():
        available = set(groups[group]._subparsers._group_actions[0].choices)  # type: ignore[attr-defined]
        assert commands <= available, (group, commands - available)


def test_cache_status_on_a_fresh_repository(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    payload = run_cli(capsys, "--base", str(tmp_path), "cache", "status")
    assert payload["cas"]["object_count"] == 0
    assert payload["config"]["mode"] == "read-write"


def test_doctor_reports_healthy_and_returns_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    payload = run_cli(capsys, "--base", str(tmp_path), "doctor", "cache")
    assert payload["healthy"] is True
    names = {check["check"] for check in payload["checks"]}
    assert {"no-orphan-metadata", "no-stuck-runs", "redis-not-authoritative"} <= names


def test_gc_defaults_to_a_dry_run_plan(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    payload = run_cli(capsys, "--base", str(tmp_path), "cache", "gc")
    assert payload["dry_run"] is True
    assert payload["plan_id"].startswith("gcp_")
    assert payload["next"].startswith("elmos cache gc --apply")


def test_gc_apply_requires_an_idempotency_key(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plan = run_cli(capsys, "--base", str(tmp_path), "cache", "gc")
    code = main(["--base", str(tmp_path), "cache", "gc", "--apply", plan["plan_id"]])
    captured = capsys.readouterr()
    assert code == 1
    assert "idempotency" in captured.err.lower()


def test_pin_and_unpin_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    digest = "sha256:" + "a" * 64
    pinned = run_cli(
        capsys, "--base", str(tmp_path), "cache", "pin", digest, "--reason", "under investigation"
    )
    removed = run_cli(capsys, "--base", str(tmp_path), "cache", "unpin", pinned["pin_id"])
    assert removed["removed"] is True


def test_artifact_materialize_writes_the_bytes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from elmos_build_cache.cas import ContentAddressableStore

    cache = ContentAddressableStore(tmp_path / ".elmos" / "cache")
    digest = cache.put_bytes(b"restored artifact")
    destination = tmp_path / "out.bin"
    payload = run_cli(
        capsys, "--base", str(tmp_path), "artifact", "materialize", digest, str(destination)
    )
    assert destination.read_bytes() == b"restored artifact"
    assert payload["size"] == len(b"restored artifact")


def test_missing_action_key_is_a_typed_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--base", str(tmp_path), "cache", "inspect", "b" * 64])
    captured = capsys.readouterr()
    assert code == 1
    assert json.loads(captured.err)["error"]["code"] == "NOT_FOUND"


def test_run_mutations_require_scope_and_expected_version() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "cancel", "run-1"])  # missing --expected-version/--reason/--key
    args = parser.parse_args(
        ["run", "cancel", "run-1", "--expected-version", "3", "--idempotency-key", "k", "--reason", "stop"]
    )
    assert args.expected_version == 3 and args.reason == "stop"


def test_text_rendering_is_available(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--base", str(tmp_path), "--text", "cache", "status"]) == 0
    out = capsys.readouterr().out
    assert "cas.object_count: 0" in out


def test_verify_reports_orphans(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from elmos_build_cache.cas import ContentAddressableStore

    cache = ContentAddressableStore(tmp_path / ".elmos" / "cache")
    cache.put_bytes(b"unregistered blob")
    payload = run_cli(capsys, "--base", str(tmp_path), "cache", "verify", "--deep")
    assert payload["checked"] == 1
    assert len(payload["orphans"]["orphan_blobs"]) == 1
