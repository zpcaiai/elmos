from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.cli import build_parser, main
from elmos_build_cache.db import open_store
from elmos_build_cache.environment_cache import EnvironmentKeyInputs, PlatformIdentity
from elmos_build_cache.environment_service import (
    EnvironmentLayerPayload,
    EnvironmentLayerType,
    EnvironmentSnapshotService,
)
from elmos_build_cache.parity_store import ParityMetadataRepository


def d(character: str) -> str:
    return "sha256:" + character * 64


def environment_key_inputs() -> EnvironmentKeyInputs:
    return EnvironmentKeyInputs(
        base_image_digest=d("1"),
        setup_script_digests=(d("2"),),
        maintenance_script_digests=(d("3"),),
        lockfile_digests=(("requirements.lock", d("4")),),
        package_manager_digest=d("5"),
        toolchain_digests=(("python", d("6")),),
        platform=PlatformIdentity("linux", "arm64", "glibc", d("7")),
        approved_environment_digests=(("BUILD_MODE", d("8")),),
        secret_reference_versions=((d("9"), d("a")),),
    )


def environment_inspect_argv(base: Path, snapshot_key: str) -> list[str]:
    return [
        "--base",
        str(base),
        "--project",
        "project-a",
        "environment",
        "inspect",
        snapshot_key,
        "--trust-namespace",
        "branch",
        "--transfer-ms",
        "1",
        "--decompression-ms",
        "1",
        "--verification-ms",
        "1",
        "--rebuild-ms",
        "100",
        "--minimum-savings-ms",
        "1",
        "--maximum-restore-ratio",
        "0.9",
    ]


def write_json(path: Path, document: dict[str, Any]) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def run_cli(capsys: pytest.CaptureFixture[str], *argv: str) -> dict[str, Any]:
    code = main(list(argv))
    captured = capsys.readouterr()
    assert code == 0, captured.err
    loaded = json.loads(captured.out)
    assert isinstance(loaded, dict)
    return loaded


def prompt_payload(content: str = "stable policy") -> dict[str, Any]:
    return {
        "project_id": "project-a",
        "identity": {
            "provider": "openai",
            "provider_namespace_digest": d("2"),
            "model": "model-v1",
            "effort_profile": "high",
            "tool_schema_digest": d("3"),
            "compatibility_digest": d("4"),
        },
        "segments": [
            {
                "segment_id": "policy",
                "stability": "stable",
                "ordinal": 0,
                "content": content,
            },
            {
                "segment_id": "task",
                "stability": "volatile",
                "ordinal": 0,
                "content": "change implementation",
            },
        ],
    }


def parity_payload() -> dict[str, Any]:
    return {
        "project_id": "project-a",
        "report_id": "report-a",
        "metrics": {},
        "cohorts": {},
        "scenarios": [],
        "binding": {
            "source_digest": d("1"),
            "configuration_digest": d("2"),
            "provider_profiles_digest": d("3"),
            "corpus_digest": d("4"),
            "platform_digest": d("5"),
            "generated_at": "2026-08-20T00:00:00Z",
            "executor_identity": "executor-a",
            "verifier_identity": "verifier-b",
        },
    }


def affinity_payload() -> dict[str, Any]:
    request = {
        "authorization_scope_digest": d("1"),
        "trust_namespace": "branch",
        "provider": "openai",
        "model": "model-v1",
        "effort_profile": "high",
        "tool_schema_digest": d("2"),
        "prefix_compatibility_digest": d("3"),
        "platform_digest": d("4"),
        "required_capacity": 1,
    }
    return {
        "project_id": "project-a",
        "request_id": "request-a",
        "request": request,
        "candidates": [
            {
                "target_id": "worker-a",
                "authorization_scope_digest": request["authorization_scope_digest"],
                "trust_namespace": request["trust_namespace"],
                "provider": request["provider"],
                "model": request["model"],
                "effort_profile": request["effort_profile"],
                "tool_schema_digest": request["tool_schema_digest"],
                "prefix_compatibility_digest": request["prefix_compatibility_digest"],
                "platform_digest": request["platform_digest"],
                "authorized": True,
                "available_capacity": 2,
                "health": "HEALTHY",
                "prompt_cache_value_ms": 100,
            }
        ],
    }


def test_v12_cli_groups_and_commands_are_registered() -> None:
    groups = build_parser()._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    expected = {
        "prompt": {"compile", "diff"},
        "environment": {"inspect"},
        "affinity": {"decide"},
        "parity": {"status", "evaluate", "report"},
    }
    for group, commands in expected.items():
        available = set(groups[group]._subparsers._group_actions[0].choices)  # type: ignore[attr-defined]
        assert commands <= available
    cache_commands = set(groups["cache"]._subparsers._group_actions[0].choices)  # type: ignore[attr-defined]
    assert "explain" in cache_commands


def test_prompt_compile_is_content_free_and_persistence_is_explicit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = write_json(tmp_path / "prompt.json", prompt_payload())

    observed = run_cli(
        capsys,
        "--base",
        str(tmp_path),
        "--project",
        "project-a",
        "prompt",
        "compile",
        "--input",
        str(source),
    )
    assert observed["persisted"] is False
    assert "stable policy" not in json.dumps(observed)

    assert (
        main(
            [
                "--base",
                str(tmp_path),
                "--project",
                "project-a",
                "prompt",
                "compile",
                "--input",
                str(source),
                "--persist",
            ]
        )
        == 1
    )
    assert "idempotency" in capsys.readouterr().err.lower()

    persisted = run_cli(
        capsys,
        "--base",
        str(tmp_path),
        "--project",
        "project-a",
        "prompt",
        "compile",
        "--input",
        str(source),
        "--persist",
        "--idempotency-key",
        "prompt-key",
    )
    assert persisted["persisted"] is True

    replayed = run_cli(
        capsys,
        "--base",
        str(tmp_path),
        "--project",
        "project-a",
        "prompt",
        "compile",
        "--input",
        str(source),
        "--persist",
        "--idempotency-key",
        "prompt-key",
    )
    assert replayed == persisted


def test_prompt_diff_reports_digests_not_content(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    previous = write_json(tmp_path / "previous.json", prompt_payload("policy one"))
    current = write_json(tmp_path / "current.json", prompt_payload("policy two"))

    payload = run_cli(
        capsys,
        "--base",
        str(tmp_path),
        "--project",
        "project-a",
        "prompt",
        "diff",
        "--previous",
        str(previous),
        "--current",
        str(current),
    )

    assert payload["changed"] is True
    assert payload["first_difference"]["dimension"] == "stable_segment"
    assert "policy one" not in json.dumps(payload)
    assert "policy two" not in json.dumps(payload)


def test_standalone_affinity_refuses_caller_supplied_runner_authorization(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = write_json(tmp_path / "affinity.json", affinity_payload())
    code = main(
        [
            "--base",
            str(tmp_path),
            "--project",
            "project-a",
            "affinity",
            "decide",
            "--input",
            str(source),
            "--persist",
            "--idempotency-key",
            "affinity-key",
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "server-side attested runner registry" in captured.err
    store = open_store(tmp_path / ".elmos/cache/index.sqlite")
    assert store.query_one("SELECT COUNT(*) FROM cache_affinity_decisions_v12")[0] == 0
    store.close()


def test_parity_evaluation_stays_not_run_and_roundtrips_durably(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = write_json(tmp_path / "parity.json", parity_payload())
    result = run_cli(
        capsys,
        "--base",
        str(tmp_path),
        "--project",
        "project-a",
        "parity",
        "evaluate",
        "--input",
        str(source),
        "--persist",
        "--idempotency-key",
        "parity-key",
    )
    assert result["decision"] == "NOT_RUN"
    assert result["mandatory_pass"] is False
    assert result["persisted"] is True

    stored = run_cli(
        capsys,
        "--base",
        str(tmp_path),
        "--project",
        "project-a",
        "parity",
        "report",
        "report-a",
    )
    assert stored["report_digest"] == result["report_digest"]
    assert stored["decision"] == "NOT_RUN"

    status = run_cli(
        capsys,
        "--base",
        str(tmp_path),
        "--project",
        "project-a",
        "parity",
        "status",
    )
    assert status["records"]["parity_reports"] == 1
    assert status["certification"] == "NOT_CERTIFIED"
    assert not any(status["serving"].values())
    assert set(status["wiring"]["layers"].values()) == {"NOT_WIRED"}


def test_persistent_idempotency_key_cannot_replay_across_projects(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = parity_payload()
    first_path = write_json(tmp_path / "parity-a.json", first)
    run_cli(
        capsys,
        "--base",
        str(tmp_path),
        "--project",
        "project-a",
        "parity",
        "evaluate",
        "--input",
        str(first_path),
        "--persist",
        "--idempotency-key",
        "shared-key",
    )

    second = parity_payload()
    second["project_id"] = "project-b"
    second_path = write_json(tmp_path / "parity-b.json", second)
    assert (
        main(
            [
                "--base",
                str(tmp_path),
                "--project",
                "project-b",
                "parity",
                "evaluate",
                "--input",
                str(second_path),
                "--persist",
                "--idempotency-key",
                "shared-key",
            ]
        )
        == 1
    )
    assert "idempotency" in capsys.readouterr().err.lower()

    store = open_store(tmp_path / ".elmos/cache/index.sqlite")
    assert store.query_one(
        "SELECT COUNT(*) FROM cache_parity_reports_v12 WHERE project_id=?",
        ("project-b",),
    )[0] == 0
    store.close()


def test_cli_crash_after_claim_is_pending_and_never_automatically_reexecutes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = write_json(tmp_path / "prompt-crash.json", prompt_payload())
    argv = [
        "--base",
        str(tmp_path),
        "--project",
        "project-a",
        "prompt",
        "compile",
        "--input",
        str(source),
        "--persist",
        "--idempotency-key",
        "cli-crash-key",
    ]
    original = ParityMetadataRepository.put_prompt_manifest
    calls: list[str] = []

    def crash_after_claim(self: ParityMetadataRepository, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del self, args, kwargs
        calls.append("write")
        raise RuntimeError("simulated process death before completion")

    monkeypatch.setattr(ParityMetadataRepository, "put_prompt_manifest", crash_after_claim)
    with pytest.raises(RuntimeError, match="simulated process death"):
        main(argv)
    monkeypatch.setattr(ParityMetadataRepository, "put_prompt_manifest", original)

    assert main(argv) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["code"] == "OUTCOME_UNKNOWN"
    assert calls == ["write"]

    store = open_store(tmp_path / ".elmos/cache/index.sqlite")
    try:
        assert store.query_one(
            "SELECT state FROM idempotency_records"
            " WHERE tenant_id=? AND idempotency_key=?",
            ("default", "cli-crash-key"),
        ) == ("PENDING",)
        assert store.query_one("SELECT COUNT(*) FROM prompt_prefix_manifests")[0] == 0
    finally:
        store.close()


def test_cache_explain_and_environment_inspect_are_project_scoped(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = open_store(tmp_path / ".elmos" / "cache" / "index.sqlite")
    repository = ParityMetadataRepository(store)
    repository.put_cache_outcome(
        "default",
        "project-a",
        "request-a",
        "event-a",
        {
            "schema_version": "1.2.0",
            "event_id": "event-a",
            "request_id": "request-a",
            "layer": "ACTION",
            "outcome": "NECESSARY_MISS",
            "reason_code": "COLD_NO_ENTRY",
            "eligible": True,
            "occurred_at": "2026-08-20T00:00:00Z",
        },
    )
    sealed = EnvironmentSnapshotService(
        store,
        ContentAddressableStore(tmp_path / ".elmos" / "cache"),
        repository,
    ).seal(
        "default",
        "project-a",
        "branch",
        environment_key_inputs(),
        (EnvironmentLayerPayload(EnvironmentLayerType.BASE, b"environment-layer"),),
    )
    store.close()

    explanation = run_cli(
        capsys,
        "--base",
        str(tmp_path),
        "--project",
        "project-a",
        "cache",
        "explain",
        "request-a",
    )
    assert explanation["reason_counts"] == {"COLD_NO_ENTRY": 1}

    environment = run_cli(capsys, *environment_inspect_argv(tmp_path, sealed.key.digest))
    assert environment["effective_status"] == "AVAILABLE"
    assert environment["manifest"]["snapshot_id"] == sealed.snapshot_id
    assert environment["verified_layer_digests"] == [sealed.layers[0].digest]
    assert environment["decision"]["action"] == "RESTORE"


def test_environment_inspect_requires_trust_and_economics_and_rejects_missing_binding(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "--base",
                str(tmp_path),
                "--project",
                "project-a",
                "environment",
                "inspect",
                d("a"),
            ]
        )
    capsys.readouterr()

    store = open_store(tmp_path / ".elmos" / "cache" / "index.sqlite")
    sealed = EnvironmentSnapshotService(
        store,
        ContentAddressableStore(tmp_path / ".elmos" / "cache"),
    ).seal(
        "default",
        "project-a",
        "branch",
        environment_key_inputs(),
        (EnvironmentLayerPayload(EnvironmentLayerType.BASE, b"environment-layer"),),
    )
    with store.transaction():
        store.execute(
            "DELETE FROM artifact_refs WHERE tenant_id=? AND source_kind=?"
            " AND source_id=? AND target_digest=?",
            (
                "default",
                "environment-snapshot",
                sealed.snapshot_id,
                sealed.layers[0].digest,
            ),
        )
    store.close()

    assert main(environment_inspect_argv(tmp_path, sealed.key.digest)) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["code"] == "CORRUPT_OBJECT"
