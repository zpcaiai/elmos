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


def test_main_closes_metadata_store_on_success_and_typed_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from elmos_build_cache import cli as cli_module
    from elmos_build_cache.db.store import MetadataStore

    original_close = MetadataStore.close
    closed: list[MetadataStore] = []

    def tracking_close(store: MetadataStore) -> None:
        closed.append(store)
        original_close(store)

    monkeypatch.setattr(MetadataStore, "close", tracking_close)
    assert main(["--base", str(tmp_path), "cache", "status"]) == 0
    capsys.readouterr()
    assert main(["--base", str(tmp_path), "cache", "inspect", "a" * 64]) == 1
    capsys.readouterr()

    def unexpected(_context: object, _args: object) -> dict[str, object]:
        raise RuntimeError("unexpected handler failure")

    monkeypatch.setitem(cli_module.COMMANDS, ("cache", "status"), unexpected)
    with pytest.raises(RuntimeError, match="unexpected handler failure"):
        main(["--base", str(tmp_path), "cache", "status"])
    assert len(closed) == 3


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


def test_gc_apply_response_replays_and_key_reuse_with_plan_drift_conflicts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from elmos_build_cache.db import open_store

    first_plan = run_cli(capsys, "--base", str(tmp_path), "cache", "gc")
    store = open_store(tmp_path / ".elmos" / "cache" / "index.sqlite")
    with store.transaction():
        store.execute("UPDATE gc_plans SET created_at=0 WHERE plan_id=?", (first_plan["plan_id"],))
    store.close()

    argv = (
        "--base",
        str(tmp_path),
        "cache",
        "gc",
        "--apply",
        first_plan["plan_id"],
        "--idempotency-key",
        "gc-key",
    )
    first = run_cli(capsys, *argv)
    replay = run_cli(capsys, *argv)
    assert replay == first

    second_plan = run_cli(capsys, "--base", str(tmp_path), "cache", "gc")
    assert (
        main(
            [
                "--base",
                str(tmp_path),
                "cache",
                "gc",
                "--apply",
                second_plan["plan_id"],
                "--idempotency-key",
                "gc-key",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_pin_and_unpin_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    digest = "sha256:" + "a" * 64
    pinned = run_cli(capsys, "--base", str(tmp_path), "cache", "pin", digest, "--reason", "under investigation")
    removed = run_cli(capsys, "--base", str(tmp_path), "cache", "unpin", pinned["pin_id"])
    assert removed["removed"] is True


def test_artifact_materialize_writes_the_bytes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from elmos_build_cache.cas import ContentAddressableStore

    cache = ContentAddressableStore(tmp_path / ".elmos" / "cache")
    digest = cache.put_bytes(b"restored artifact")
    destination = tmp_path / "out.bin"
    payload = run_cli(capsys, "--base", str(tmp_path), "artifact", "materialize", digest, str(destination))
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


def test_verify_does_not_attribute_shared_unregistered_blobs_to_a_tenant(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from elmos_build_cache.cas import ContentAddressableStore

    cache = ContentAddressableStore(tmp_path / ".elmos" / "cache")
    cache.put_bytes(b"unregistered blob")
    payload = run_cli(capsys, "--base", str(tmp_path), "cache", "verify", "--deep")
    assert payload["checked"] == 1
    assert payload["orphans"]["orphan_blobs"] == []


def test_global_run_ids_fail_closed_before_idempotency_or_workspace_side_effects(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from elmos_build_cache.db import open_store

    database = tmp_path / ".elmos" / "cache" / "index.sqlite"
    store = open_store(database)
    with store.transaction():
        snapshot_id = store.record_snapshot(
            "foreign-tenant",
            "project-a",
            "sha256:" + "1" * 64,
            "sha256:" + "2" * 64,
            "policy-v1",
        )
        store.create_run(
            "global-run-id",
            "foreign-tenant",
            "project-a",
            snapshot_id,
            "pipeline-v1",
        )
    store.close()

    inspect_errors: list[dict[str, object]] = []
    for run_id in ("global-run-id", "missing-run-id"):
        assert (
            main(
                [
                    "--base",
                    str(tmp_path),
                    "--tenant",
                    "caller-tenant",
                    "--project",
                    "project-a",
                    "workspace",
                    "inspect",
                    run_id,
                ]
            )
            == 1
        )
        inspect_errors.append(json.loads(capsys.readouterr().err)["error"])
    assert inspect_errors[0] == inspect_errors[1]
    assert inspect_errors[0]["code"] == "NOT_FOUND"

    mutations = (
        ("resume", []),
        ("pause", ["--expected-version", "0"]),
        ("cancel", ["--expected-version", "0", "--reason", "operator stop"]),
    )
    for command, extra in mutations:
        assert (
            main(
                [
                    "--base",
                    str(tmp_path),
                    "--tenant",
                    "caller-tenant",
                    "--project",
                    "project-a",
                    "run",
                    command,
                    "global-run-id",
                    "--idempotency-key",
                    f"foreign-{command}",
                    *extra,
                ]
            )
            == 1
        )
        assert json.loads(capsys.readouterr().err)["error"]["code"] == "NOT_FOUND"

    store = open_store(database)
    assert store.get_run("global-run-id").version == 0
    assert store.get_run("global-run-id").status.value == "PENDING"
    claims = store.query_one(
        "SELECT COUNT(*) FROM idempotency_records WHERE tenant_id=?",
        ("caller-tenant",),
    )
    assert claims is not None and int(claims[0]) == 0
    store.close()
    assert not (tmp_path / ".elmos" / "workspaces" / "foreign-tenant").exists()


def test_staged_file_id_is_bound_to_the_owned_run_before_workspace_creation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from elmos_build_cache.cas import ContentAddressableStore
    from elmos_build_cache.db import open_store
    from elmos_build_cache.staging import Workspace

    database = tmp_path / ".elmos" / "cache" / "index.sqlite"
    store = open_store(database)
    with store.transaction():
        snapshot_id = store.record_snapshot(
            "tenant-a",
            "project-a",
            "sha256:" + "3" * 64,
            "sha256:" + "4" * 64,
            "policy-v1",
        )
        store.create_run("owned-run", "tenant-a", "project-a", snapshot_id, "pipeline-v1")
        store.create_run("other-run", "tenant-a", "project-a", snapshot_id, "pipeline-v1")
        store.upsert_node("other-run", "node-a", "stage-a", "1.0.0")
    other_workspace = Workspace(
        tmp_path / ".elmos" / "workspaces",
        "tenant-a",
        "project-a",
        "other-run",
        store,
        ContentAddressableStore(tmp_path / ".elmos" / "cache"),
    )
    with store.transaction():
        staged = other_workspace.reserve("node-a", 1, "generated.txt", 0)
    store.close()

    assert (
        main(
            [
                "--base",
                str(tmp_path),
                "--tenant",
                "tenant-a",
                "--project",
                "project-a",
                "workspace",
                "quarantine",
                "owned-run",
                staged.staged_file_id,
                "--reason",
                "invalid owner",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "NOT_FOUND"
    assert not (tmp_path / ".elmos" / "workspaces" / "tenant-a" / "project-a" / "owned-run").exists()


def test_context_plan_prepare_and_status_are_wired_to_the_durable_service(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from elmos_build_cache.context_ledger import ContextEventType, RepositoryContextLedger
    from elmos_build_cache.db import MetadataStore, open_store

    tenant = "tenant-context"
    project = "project-context"
    stream = "stream-context"
    branch = "refs/heads/main@abc123"
    snapshot = "sha256:" + "5" * 64
    store = open_store(tmp_path / ".elmos" / "cache" / "index.sqlite")
    ledger = RepositoryContextLedger(store, tenant, project, stream, branch, snapshot)
    ledger.append(
        ContextEventType.FILE_READ,
        {
            "logical_path": "src/main.py",
            "content_digest": "sha256:" + "6" * 64,
        },
        idempotency_key="read-main",
    )
    store.close()

    scope = (
        "--base",
        str(tmp_path),
        "--tenant",
        tenant,
        "--project",
        project,
        "context",
    )
    exact = (
        "--stream",
        stream,
        "--branch-lineage",
        branch,
        "--snapshot",
        snapshot,
        "--compatibility-group",
        "provider/model/v1",
    )
    planned = run_cli(
        capsys,
        *scope,
        "plan",
        *exact,
        "--current-tokens",
        "70",
        "--predicted-next-turn-tokens",
        "0",
        "--soft-limit-tokens",
        "80",
        "--hard-limit-tokens",
        "100",
        "--reserved-future-tokens",
        "10",
    )
    assert planned["need"] == "PLAN"
    assert planned["side_effects"] == "NONE"

    sections = {
        "task_contract": {"request": "upgrade cache", "scope": "repository"},
        "repository_state": {
            "repository_snapshot_digest": snapshot,
            "branch_lineage": branch,
            "changed_files": ["src/main.py"],
        },
        "decisions": [],
        "unresolved": [],
        "approvals": [],
        "dag_state": {"phase": "implementation", "pending_nodes": ["verification"]},
        "staged_state": {"files": []},
        "build_test_state": {"status": "NOT_RUN", "checks": []},
        "evidence_refs": [],
        "pending_side_effects": [],
        "safety_constraints": [],
    }
    input_path = tmp_path / "context-sections.json"
    input_path.write_text(json.dumps(sections), encoding="utf-8")
    prepare_argv = (
        *scope,
        "prepare",
        *exact,
        "--input",
        str(input_path),
        "--expected-sequence",
        "1",
        "--idempotency-key",
        "prepare-context-1",
    )
    prepared = run_cli(capsys, *prepare_argv)
    replay = run_cli(capsys, *prepare_argv)
    assert replay == prepared
    checkpoint = prepared["checkpoint"]
    assert checkpoint["status"] == "PREPARED"
    assert checkpoint["retained_sections"] == sorted(sections)
    assert "sections" not in checkpoint
    assert prepared["provider_execution"] == "NOT_RUN"

    status = run_cli(
        capsys,
        *scope,
        "status",
        *exact,
        "--checkpoint-id",
        checkpoint["checkpoint_id"],
    )
    assert status["requested_checkpoint"]["checkpoint_digest"] == checkpoint["checkpoint_digest"]
    assert status["side_effects"] == "NONE"

    from elmos_build_cache.canonical import digest_of
    from elmos_build_cache.cas import ContentAddressableStore
    from elmos_build_cache.context_compaction import (
        WARM_ATTESTATION_KIND,
        WARM_RESULT_KIND,
        CompactionPolicy,
        ContextCompactionService,
        Ed25519ContextWarmTrustVerifier,
        context_warm_attestation_statement,
        context_warm_ref_kind,
    )
    from elmos_build_cache.security import Ed25519ProvenanceSigner

    signer = Ed25519ProvenanceSigner.generate("cli-context-verifier-key")
    public_key = signer.public_keyset()[signer.active_key_id]
    trust_path = tmp_path / "context-trust.json"
    trust_path.write_text(
        json.dumps(
            {
                "schema_version": "1.2.0",
                "keys": [
                    {
                        "key_id": signer.active_key_id,
                        "verifier_identity": "cli-context-verifier",
                        "public_key_hex": public_key.hex(),
                    }
                ],
                "revoked_key_ids": [],
            }
        ),
        encoding="utf-8",
    )

    def open_typed_service() -> tuple[
        MetadataStore,
        ContextCompactionService,
        ContentAddressableStore,
    ]:
        typed_store = open_store(tmp_path / ".elmos" / "cache" / "index.sqlite")
        typed_ledger = RepositoryContextLedger(
            typed_store,
            tenant,
            project,
            stream,
            branch,
            snapshot,
            create_if_missing=False,
        )
        typed_cas = ContentAddressableStore(tmp_path / ".elmos" / "cache")
        verifier = Ed25519ContextWarmTrustVerifier(
            Ed25519ProvenanceSigner.verifier(signer.public_keyset()),
            {signer.active_key_id: "cli-context-verifier"},
        )
        return (
            typed_store,
            ContextCompactionService(
                typed_ledger,
                CompactionPolicy(80, 100, 10),
                cas=typed_cas,
                ownership=typed_store,
                warm_trust_verifier=verifier,
            ),
            typed_cas,
        )

    def warm_checkpoint(
        typed_store: MetadataStore,
        service: ContextCompactionService,
        typed_cas: ContentAddressableStore,
        checkpoint_id: str,
    ) -> None:
        durable = service.get(checkpoint_id)
        authorization = b'{"decision":"ALLOW","kind":"context-warm-authorization"}'
        authorization_digest = typed_cas.put_bytes(authorization)
        raw = json.dumps(
            {
                "kind": "provider-prefix-warm-observation",
                "checkpoint_id": checkpoint_id,
                "cache_write_tokens": 1024,
            },
            sort_keys=True,
        ).encode()
        raw_digest = typed_cas.put_bytes(raw)
        body = {
            "schema_version": "1.2.0",
            "kind": WARM_RESULT_KIND,
            "tenant_id": tenant,
            "project_id": project,
            "stream_id": stream,
            "checkpoint_id": durable.checkpoint_id,
            "checkpoint_digest": durable.checkpoint_digest,
            "compatibility_group": durable.compatibility_group,
            "tenant_scope_digest": digest_of({"tenant_id": tenant, "project_id": project}),
            "authorization_digest": authorization_digest,
            "executor_identity": "cli-context-executor",
            "verifier_identity": "cli-context-verifier",
            "status": "PASS",
            "raw_evidence": [
                {
                    "role": "provider-cache-observation",
                    "media_type": "application/json",
                    "digest": raw_digest,
                    "size": len(raw),
                }
            ],
            "issued_at": typed_store.now() - 1,
            "expires_at": typed_store.now() + 3600,
        }
        signed = signer.sign_statement(
            WARM_ATTESTATION_KIND,
            context_warm_attestation_statement(body),
        )
        warm_digest = typed_cas.put_document(
            {**body, "attestation": signed.to_dict()},
            artifact_kind="context-warm-result",
        )
        reference = (
            "context-warm-authorization",
            authorization_digest,
            context_warm_ref_kind(project, stream, checkpoint_id),
        )
        with typed_store.transaction():
            for artifact_digest in (authorization_digest, raw_digest, warm_digest):
                artifact = typed_cas.get_bytes(artifact_digest, verify=True)
                typed_store.register_artifact(
                    tenant,
                    artifact_digest,
                    len(artifact),
                    "application/octet-stream",
                    "context-warm-evidence",
                )
                typed_store.add_artifact_ref(
                    tenant,
                    reference[0],
                    reference[1],
                    artifact_digest,
                    reference[2],
                )
        service.mark_warmed(checkpoint_id, warm_digest)

    typed_store, typed_service, typed_cas = open_typed_service()
    warm_checkpoint(typed_store, typed_service, typed_cas, checkpoint["checkpoint_id"])
    typed_store.close()
    adopt_first_argv = (
        *scope,
        "adopt",
        *exact,
        checkpoint["checkpoint_id"],
        "--expected-active-checkpoint-id",
        "NONE",
        "--trust-store",
        str(trust_path),
        "--idempotency-key",
        "adopt-context-1",
    )
    adopted_first = run_cli(capsys, *adopt_first_argv)
    assert run_cli(capsys, *adopt_first_argv) == adopted_first
    assert adopted_first["adopted_checkpoint"]["status"] == "ACTIVE"

    typed_store, typed_service, _ = open_typed_service()
    typed_service.ledger.append(
        ContextEventType.FILE_READ,
        {
            "logical_path": "src/second.py",
            "content_digest": "sha256:" + "7" * 64,
        },
        idempotency_key="read-second",
    )
    typed_store.close()
    sections["dag_state"] = {"phase": "verification", "pending_nodes": ["release"]}
    input_path.write_text(json.dumps(sections), encoding="utf-8")
    second = run_cli(
        capsys,
        *scope,
        "prepare",
        *exact,
        "--input",
        str(input_path),
        "--expected-sequence",
        "2",
        "--idempotency-key",
        "prepare-context-2",
    )["checkpoint"]
    typed_store, typed_service, typed_cas = open_typed_service()
    warm_checkpoint(typed_store, typed_service, typed_cas, second["checkpoint_id"])
    typed_store.close()
    adopt_second = run_cli(
        capsys,
        *scope,
        "adopt",
        *exact,
        second["checkpoint_id"],
        "--expected-active-checkpoint-id",
        checkpoint["checkpoint_id"],
        "--trust-store",
        str(trust_path),
        "--idempotency-key",
        "adopt-context-2",
    )
    assert adopt_second["adopted_checkpoint"]["status"] == "ACTIVE"
    rollback_argv = (
        *scope,
        "rollback",
        *exact,
        second["checkpoint_id"],
        "--trust-store",
        str(trust_path),
        "--idempotency-key",
        "rollback-context-2",
    )
    rolled_back = run_cli(capsys, *rollback_argv)
    assert run_cli(capsys, *rollback_argv) == rolled_back
    assert rolled_back["restored_checkpoint"]["checkpoint_id"] == checkpoint["checkpoint_id"]


def test_context_cli_requires_explicit_scope_and_never_exposes_warm_evidence_creation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "--base",
                str(tmp_path),
                "--project",
                "project-a",
                "context",
                "status",
                "--stream",
                "stream-a",
                "--branch-lineage",
                "refs/heads/main@abc",
                "--snapshot",
                "sha256:" + "7" * 64,
                "--compatibility-group",
                "provider/model/v1",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "CONTRACT_VIOLATION"
    assert not (tmp_path / ".elmos").exists()

    parser = build_parser()
    groups = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    commands = set(groups["context"]._subparsers._group_actions[0].choices)  # type: ignore[attr-defined]
    assert commands == {"plan", "prepare", "status", "adopt", "rollback"}
    assert "mark-warmed" not in commands


def test_environment_seal_and_restore_use_local_files_without_execution_or_secret_values(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    key_input = {
        "schema_version": "elmos.environment-key/v1",
        "base_image_digest": "sha256:" + "1" * 64,
        "setup_script_digests": ["sha256:" + "2" * 64],
        "maintenance_script_digests": ["sha256:" + "3" * 64],
        "lockfile_digests": {"requirements.lock": "sha256:" + "4" * 64},
        "package_manager_digest": "sha256:" + "5" * 64,
        "toolchain_digests": {"python": "sha256:" + "6" * 64},
        "platform": {
            "operating_system": "linux",
            "architecture": "arm64",
            "libc": "glibc",
            "runtime_digest": "sha256:" + "7" * 64,
        },
        "approved_environment_digests": {"BUILD_MODE": "sha256:" + "8" * 64},
        "secret_reference_versions": [["sha256:" + "9" * 64, "sha256:" + "a" * 64]],
    }
    key_path = tmp_path / "environment-key.json"
    key_path.write_text(json.dumps(key_input), encoding="utf-8")
    layers = tmp_path / "layers"
    layers.mkdir()
    toolchain = layers / "toolchain.layer"
    dependencies = layers / "dependencies.layer"
    toolchain.write_bytes(b"#!/bin/sh\nprintf should-not-run > executed\n")
    dependencies.write_bytes(b"dependency archive bytes")

    scope = (
        "--base",
        str(tmp_path),
        "--tenant",
        "tenant-environment",
        "--project",
        "project-environment",
        "environment",
    )
    sealed_argv = (
        *scope,
        "seal",
        "--input",
        str(key_path),
        "--layer",
        "TOOLCHAIN=layers/toolchain.layer",
        "--layer",
        "DEPENDENCIES=layers/dependencies.layer",
        "--trust-namespace",
        "tenant/project/toolchain",
        "--idempotency-key",
        "seal-environment-1",
    )
    sealed = run_cli(capsys, *sealed_argv)
    assert run_cli(capsys, *sealed_argv) == sealed
    assert sealed["secret_scan"] == "PASSED_COMPLETE_PATTERN_SCAN"
    assert sealed["execution"] == "NONE"
    assert not (tmp_path / "executed").exists()

    restored_argv = (
        *scope,
        "restore",
        "--input",
        str(key_path),
        "--trust-namespace",
        "tenant/project/toolchain",
        "--output-dir",
        "restored/environment-1",
        "--rebuild-ms",
        "500",
        "--transfer-bytes-per-ms",
        "10000",
        "--decompression-bytes-per-ms",
        "10000",
        "--verification-bytes-per-ms",
        "10000",
        "--minimum-savings-ms",
        "1",
        "--maximum-restore-ratio",
        "0.9",
        "--idempotency-key",
        "restore-environment-1",
    )
    restored = run_cli(capsys, *restored_argv)
    assert run_cli(capsys, *restored_argv) == restored
    assert restored["decision"]["action"] == "RESTORE"
    assert restored["execution"] == "NONE"
    outputs = restored["outputs"]
    assert [Path(tmp_path / item["path"]).read_bytes() for item in outputs] == [
        toolchain.read_bytes(),
        dependencies.read_bytes(),
    ]


def test_environment_seal_rejects_secret_pattern_before_idempotency_claim(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from elmos_build_cache.db import open_store

    key_input = {
        "schema_version": "elmos.environment-key/v1",
        "base_image_digest": "sha256:" + "1" * 64,
        "setup_script_digests": [],
        "maintenance_script_digests": [],
        "lockfile_digests": {},
        "package_manager_digest": "sha256:" + "2" * 64,
        "toolchain_digests": {"python": "sha256:" + "3" * 64},
        "platform": {
            "operating_system": "linux",
            "architecture": "arm64",
            "libc": "glibc",
            "runtime_digest": "sha256:" + "4" * 64,
        },
        "approved_environment_digests": {},
        "secret_reference_versions": [],
    }
    key_path = tmp_path / "environment-key.json"
    key_path.write_text(json.dumps(key_input), encoding="utf-8")
    layer = tmp_path / "unsafe.layer"
    layer.write_text('password="supersecretvalue"\n', encoding="utf-8")
    assert (
        main(
            [
                "--base",
                str(tmp_path),
                "--tenant",
                "tenant-environment",
                "--project",
                "project-environment",
                "environment",
                "seal",
                "--input",
                str(key_path),
                "--layer",
                "TOOLCHAIN=unsafe.layer",
                "--trust-namespace",
                "tenant/project/toolchain",
                "--idempotency-key",
                "must-not-be-claimed",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "SECRET_DETECTED"
    store = open_store(tmp_path / ".elmos" / "cache" / "index.sqlite")
    row = store.query_one(
        "SELECT COUNT(*) FROM idempotency_records WHERE tenant_id=?",
        ("tenant-environment",),
    )
    assert row is not None and int(row[0]) == 0
    store.close()
