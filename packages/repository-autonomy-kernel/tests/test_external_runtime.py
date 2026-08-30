"""Qualification tests for content-addressed external command transports."""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest

from elmos_repository_autonomy.cli import main
from elmos_repository_autonomy.errors import KernelError
from elmos_repository_autonomy.external import PROVIDER_PROFILES
from elmos_repository_autonomy.external_runtime import (
    CommandBinding,
    CommandIndependentVerifierTransport,
    CommandKubernetesTransport,
    CommandPostgresTransport,
    CommandProviderTransport,
    CommandS3Transport,
    CommandSecretsBrokerTransport,
    ExternalQualificationPreflight,
    JsonCommandRunner,
)
from elmos_repository_autonomy.models import bytes_digest, canonical_json


ADAPTER_BODY = r"""
import base64
import json
import sys
import time

envelope = json.load(sys.stdin)
request = envelope["request"]
mode = request.get("mode", "ok")
if mode == "timeout":
    time.sleep(2)
elif mode == "overflow":
    sys.stdout.write("x" * 8192)
    sys.stdout.flush()
    raise SystemExit(0)
elif mode == "malformed":
    sys.stdout.write("{")
    raise SystemExit(0)
elif mode == "secret-leak":
    json.dump(
        {
            "status": "SUCCEEDED",
            "result": {},
            "raw_evidence": {"secret_value": "must-not-escape"},
        },
        sys.stdout,
    )
    raise SystemExit(0)
elif mode == "verifier-escalation":
    json.dump(
        {
            "status": "SUCCEEDED",
            "result": {"p05": {"issued": True}},
            "raw_evidence": {"fixture": "invalid-authority-escalation"},
        },
        sys.stdout,
    )
    raise SystemExit(0)

if envelope["protocol"] == "elmos.secrets-broker.v2":
    if request["operation"] == "lease":
        result = {
            "native_lease_id": "native-lease-1",
            "secret_value": base64.b64encode(b"top-secret").decode("ascii"),
        }
    else:
        result = {"revoked": True}
elif mode == "binary":
    binary = request["content"]
    result = {
        "binary_encoding": binary["$elmos_binary"],
        "binary_hash": binary["content_sha256"],
        "binary_size": binary["size_bytes"],
    }
else:
    result = {"protocol": envelope["protocol"], "binding_id": envelope["binding_id"]}

json.dump(
    {
        "status": "SUCCEEDED",
        "result": result,
        "raw_evidence": {"fixture": "digest-bound-sidecar"},
        "side_effect_performed": False,
    },
    sys.stdout,
)
"""


def make_adapter(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    adapter = tmp_path / "adapter"
    adapter.write_text(f"#!{sys.executable}\n{ADAPTER_BODY}", encoding="utf-8")
    adapter.chmod(0o700)
    return adapter


def binding_record(
    adapter: Path,
    protocols: list[str],
    *,
    binding_id: str = "qualification-sidecar",
    environment_refs: dict[str, str] | None = None,
    timeout_seconds: int = 1,
    max_input_bytes: int = 1024 * 1024,
    max_output_bytes: int = 1024,
) -> dict[str, object]:
    return {
        "binding_id": binding_id,
        "executable": str(adapter),
        "executable_sha256": bytes_digest(adapter.read_bytes()),
        "protocols": protocols,
        "args": [],
        "environment_refs": environment_refs or {},
        "timeout_seconds": timeout_seconds,
        "max_input_bytes": max_input_bytes,
        "max_output_bytes": max_output_bytes,
    }


def runner(
    adapter: Path,
    protocols: list[str],
    *,
    environment_refs: dict[str, str] | None = None,
    environment: dict[str, str] | None = None,
    timeout_seconds: int = 5,
    max_output_bytes: int = 1024,
) -> JsonCommandRunner:
    binding = CommandBinding.from_mapping(
        binding_record(
            adapter,
            protocols,
            environment_refs=environment_refs,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )
    )
    return JsonCommandRunner(binding, environment=environment or {})


def all_protocols() -> list[str]:
    return [
        "elmos.postgresql.v2",
        "elmos.scm.v2",
        "elmos.s3.v2",
        "elmos.event-bus.v2",
        "elmos.secrets-broker.v2",
        "elmos.kubernetes.v2",
        "elmos.independent-verifier.v2",
        *(f"elmos.provider.{adapter_id}.v2" for adapter_id in PROVIDER_PROFILES),
    ]


def qualification_manifest(adapter: Path) -> dict[str, object]:
    binding = binding_record(adapter, all_protocols())
    binding_id = str(binding["binding_id"])
    credential_ref = "lease://qualification/credential"
    exact_commit = "a" * 40
    resources = {
        "postgresql": {
            "service_ref": "postgresql://service/elmos-qualification",
            "engine_version": "17.1",
            "operator_role_ref": "role://migration-operator",
            "binding_id": binding_id,
        },
        "scm": {
            "provider_instance": "github-enterprise/qualification",
            "native_repository_id": "repo-42",
            "exact_commit": exact_commit,
            "credential_lease_ref": credential_ref,
            "binding_id": binding_id,
        },
        "object-store": {
            "account_id": "account-a",
            "region": "test-1",
            "bucket": "elmos-qualification",
            "credential_lease_ref": credential_ref,
            "binding_id": binding_id,
        },
        "event-bus": {
            "provider_instance": "kafka/qualification",
            "region": "test-1",
            "topic": "elmos-qualification",
            "credential_lease_ref": credential_ref,
            "binding_id": binding_id,
        },
        "secrets-broker": {
            "broker_id": "vault/qualification",
            "role_ref": "role://elmos-qualification",
            "binding_id": binding_id,
        },
        "kubernetes": {
            "context": "isolated-qualification",
            "namespace": "elmos-qualification",
            "image_digest": "sha256:" + "b" * 64,
            "service_account": "elmos-qualification",
            "binding_id": binding_id,
        },
        "customer-repository": {
            "provider_instance": "github-enterprise/customer",
            "native_repository_id": "customer-repo-7",
            "exact_commit": exact_commit,
            "credential_lease_ref": credential_ref,
            "customer_authorization_receipt": "sha256:" + "c" * 64,
            "binding_id": binding_id,
        },
    }
    providers = {
        adapter_id: {
            "version": "pinned-test-version",
            "provider_instance": f"{adapter_id}/qualification",
            "credential_lease_ref": credential_ref,
            "binding_id": binding_id,
        }
        for adapter_id in PROVIDER_PROFILES
    }
    return {
        "schema_version": "2.0.0",
        "scope": {
            "tenant_id": "tenant-a",
            "account_id": "account-a",
            "project_id": "project-a",
            "actor_id": "qualification-operator",
            "environment_authority_id": "isolated-environment-authority",
            "idempotency_key": "qualification-run-1",
            "revision_digest": "sha256:" + "d" * 64,
            "candidate_digest": "sha256:" + "e" * 64,
            "workload_digest": "sha256:" + "f" * 64,
            "authorization_receipt": "sha256:" + "1" * 64,
        },
        "command_bindings": {binding_id: binding},
        "resources": resources,
        "providers": providers,
        "independent_verifier": {
            "verifier_id": "independent-verifier",
            "trust_store_ref": "trust://qualification",
            "public_key_digest": "sha256:" + "2" * 64,
            "authorization_receipt": "sha256:" + "3" * 64,
            "binding_id": binding_id,
        },
    }


def test_command_binding_is_digest_and_protocol_bound(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    command = runner(adapter, ["elmos.scm.v2"])

    response = command.invoke("elmos.scm.v2", {"operation": "resolve"})

    assert response["status"] == "SUCCEEDED"
    evidence = response["raw_evidence"]["command_execution"]
    assert evidence["executable_sha256"] == bytes_digest(adapter.read_bytes())
    assert evidence["stdout_sha256"].startswith("sha256:")
    assert "top-secret" not in json.dumps(evidence)
    with pytest.raises(KernelError, match="COMMAND_PROTOCOL_DENIED"):
        command.invoke("elmos.s3.v2", {"operation": "get"})


def test_command_binding_rejects_drift_and_insecure_permissions(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    command = runner(adapter, ["elmos.scm.v2"])
    adapter.write_text(adapter.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(KernelError, match="COMMAND_DIGEST_DRIFT"):
        command.invoke("elmos.scm.v2", {"operation": "resolve"})

    insecure = make_adapter(tmp_path / "insecure")
    insecure.chmod(0o720)
    with pytest.raises(KernelError, match="COMMAND_INSECURE"):
        CommandBinding.from_mapping(binding_record(insecure, ["elmos.scm.v2"]))


def test_s3_binary_payload_is_canonicalized_without_losing_digest(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    transport = CommandS3Transport(runner(adapter, ["elmos.s3.v2"]))
    content = b"\x00binary\xff"

    response = transport.invoke({"mode": "binary", "content": content})

    assert response["status"] == "SUCCEEDED"
    assert response["result"]["binary_encoding"] == "base64"
    assert response["result"]["binary_hash"] == bytes_digest(content)
    assert response["result"]["binary_size"] == len(content)


def test_missing_environment_reference_never_starts_adapter(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    command = runner(
        adapter,
        ["elmos.scm.v2"],
        environment_refs={"SCM_CREDENTIAL": "QUALIFICATION_SCM_CREDENTIAL"},
        environment={},
    )

    response = command.invoke("elmos.scm.v2", {"operation": "resolve"})

    assert response["status"] == "NOT_RUN"
    assert response["error"]["code"] == "ENVIRONMENT_REFERENCE_UNAVAILABLE"
    assert response["side_effect_performed"] is False


def test_invalid_environment_and_non_finite_input_fail_closed(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    invalid_environment = runner(
        adapter,
        ["elmos.scm.v2"],
        environment_refs={"SCM_CREDENTIAL": "QUALIFICATION_SCM_CREDENTIAL"},
        environment={"QUALIFICATION_SCM_CREDENTIAL": 7},  # type: ignore[dict-item]
    )
    response = invalid_environment.invoke("elmos.scm.v2", {"operation": "resolve"})
    assert response["status"] == "NOT_RUN"
    assert response["error"]["code"] == "ENVIRONMENT_REFERENCE_INVALID"

    command = runner(adapter, ["elmos.scm.v2"])
    with pytest.raises(KernelError, match="COMMAND_INPUT_INVALID"):
        command.invoke("elmos.scm.v2", {"score": float("nan")})


def test_timeout_is_unknown_and_requires_reconciliation(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    command = runner(adapter, ["elmos.scm.v2"], timeout_seconds=1)

    response = command.invoke("elmos.scm.v2", {"mode": "timeout"})

    assert response["status"] == "UNKNOWN"
    assert response["error"]["code"] == "ADAPTER_TIMEOUT"
    assert response["side_effect_performed"] is None
    assert response["raw_evidence"]["command_execution"]["output_complete"] is False


def test_output_flood_is_killed_at_the_bound(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    command = runner(adapter, ["elmos.scm.v2"], max_output_bytes=1024)

    response = command.invoke("elmos.scm.v2", {"mode": "overflow"})

    assert response["status"] == "UNKNOWN"
    assert response["error"]["code"] == "ADAPTER_OUTPUT_LIMIT"
    receipt = response["raw_evidence"]["command_execution"]
    assert receipt["output_complete"] is False
    assert receipt["stdout_sha256"] is None
    assert receipt["stdout_prefix_sha256"].startswith("sha256:")


@pytest.mark.parametrize("mode", ["malformed", "secret-leak"])
def test_malformed_or_secret_bearing_output_fails_closed(tmp_path: Path, mode: str):
    adapter = make_adapter(tmp_path)
    command = runner(adapter, ["elmos.scm.v2"])

    response = command.invoke("elmos.scm.v2", {"mode": mode})

    assert response["status"] == "UNKNOWN"
    assert response["error"]["code"] in {
        "ADAPTER_RESPONSE_INVALID",
        "ADAPTER_SECRET_EXPOSURE",
    }


def test_secrets_broker_returns_ephemeral_material_without_receipt_leak(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    transport = CommandSecretsBrokerTransport(runner(adapter, ["elmos.secrets-broker.v2"]))

    resolution = transport.resolve("vault://tenant-a/provider")

    assert resolution.material == b"top-secret"
    assert resolution.native_lease_id == "native-lease-1"
    persisted = canonical_json(resolution.receipt)
    assert b"top-secret" not in persisted
    assert b"dG9wLXNlY3JldA==" not in persisted
    command_receipt = resolution.receipt["raw_evidence"]["command_execution"]
    assert command_receipt["output_hash_withheld"] is True
    assert command_receipt["stdout_sha256"] is None
    revoked = transport.revoke({"native_lease_id": "native-lease-1", "lease_id": "kernel-lease-1"})
    assert revoked["status"] == "SUCCEEDED"


def test_provider_transport_has_exact_seven_profile_boundary(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    command = runner(adapter, all_protocols())
    transport = CommandProviderTransport({adapter_id: command for adapter_id in PROVIDER_PROFILES})

    response = transport.invoke(
        "openai-codex",
        {"operation": "invoke", "request_id": "provider-run-1"},
    )

    assert response["status"] == "SUCCEEDED"
    assert response["result"]["protocol"] == "elmos.provider.openai-codex.v2"
    missing = CommandProviderTransport({}).invoke(
        "openai-codex",
        {"operation": "invoke", "request_id": "provider-run-2"},
    )
    assert missing["status"] == "NOT_RUN"
    with pytest.raises(KernelError, match="ADAPTER_UNKNOWN"):
        CommandProviderTransport({"unknown": command})


def test_postgres_kubernetes_and_verifier_transports_are_explicit(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    command = runner(adapter, all_protocols())

    postgres = CommandPostgresTransport(command).invoke({"operation": "inventory"})
    kubernetes = CommandKubernetesTransport(command).invoke({"operation": "inventory"})
    verifier = CommandIndependentVerifierTransport(command)
    verified = verifier.verify({"operation": "verify", "evidence_ref": "object://evidence"})
    escalated = verifier.verify({"mode": "verifier-escalation"})

    assert postgres["result"]["protocol"] == "elmos.postgresql.v2"
    assert kubernetes["result"]["protocol"] == "elmos.kubernetes.v2"
    assert verified["result"]["protocol"] == "elmos.independent-verifier.v2"
    assert escalated["status"] == "UNKNOWN"
    assert escalated["error"]["code"] == "VERIFIER_AUTHORITY_ESCALATION"
    assert escalated["result"] == {}


def test_complete_preflight_is_ready_but_never_executes_or_certifies(tmp_path: Path):
    adapter = make_adapter(tmp_path)

    result = ExternalQualificationPreflight(environment={}).evaluate(qualification_manifest(adapter))

    assert result["ready_for_authorized_execution"] is True
    assert result["provider_count"] == 7
    assert result["provider_conformance_units"] == 84
    assert set(result["suite_readiness"]) == {f"T0{index}" for index in range(9)}
    assert result["suite_readiness"]["T06"] == "READY_FOR_AUTHORIZED_EXECUTION"
    assert result["execution_performed"] is False
    assert result["external_evidence"] == "NOT_RUN"
    assert set(result["levels"].values()) == {"NOT_RUN"}
    assert result["certification"] == "NOT_CERTIFIED"
    assert result["p05"] == {
        "issued": False,
        "decision": "P05_DEPLOYMENT_COMPLETE_NOT_ISSUED",
    }


def test_preflight_blocks_protocol_drift_and_invalid_customer_authority(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    manifest = qualification_manifest(adapter)
    binding = next(iter(manifest["command_bindings"].values()))
    binding["protocols"].remove("elmos.kubernetes.v2")
    manifest["resources"]["customer-repository"]["customer_authorization_receipt"] = "caller-claim"

    result = ExternalQualificationPreflight(environment={}).evaluate(manifest)

    assert result["ready_for_authorized_execution"] is False
    assert result["capabilities"]["kubernetes"]["reasons"] == ["COMMAND_PROTOCOL_DENIED"]
    assert "CUSTOMER_AUTHORIZATION_RECEIPT_INVALID" in result["capabilities"]["customer-repository"]["reasons"]
    assert result["p05"]["issued"] is False


def test_preflight_rejects_inline_credentials(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    manifest = qualification_manifest(adapter)
    manifest["providers"]["openrouter"]["token"] = "caller-supplied-secret"

    with pytest.raises(KernelError, match="SECRET_EXPOSURE"):
        ExternalQualificationPreflight(environment={}).evaluate(manifest)


def test_preflight_rejects_unknown_completion_claim_field(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    manifest = qualification_manifest(adapter)
    manifest["completion_claim"] = "P05_DEPLOYMENT_COMPLETE"

    with pytest.raises(KernelError, match="FIELD_UNKNOWN"):
        ExternalQualificationPreflight(environment={}).evaluate(manifest)


def test_cli_preflight_returns_machine_readable_non_certifying_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    adapter = make_adapter(tmp_path)
    manifest_path = tmp_path / "qualification-manifest.json"
    manifest_path.write_text(
        json.dumps(qualification_manifest(adapter)),
        encoding="utf-8",
    )

    assert main(["external-preflight", "--manifest", str(manifest_path)]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["ready_for_authorized_execution"] is True
    assert result["execution_performed"] is False
    assert result["certification"] == "NOT_CERTIFIED"
    assert result["p05"]["issued"] is False


def test_preflight_does_not_mutate_caller_manifest(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    manifest = qualification_manifest(adapter)
    before = copy.deepcopy(manifest)

    ExternalQualificationPreflight(environment={}).evaluate(manifest)

    assert manifest == before


def test_reserved_environment_and_symlink_are_rejected(tmp_path: Path):
    adapter = make_adapter(tmp_path)
    with pytest.raises(KernelError, match="ENVIRONMENT_REF_DENIED"):
        CommandBinding.from_mapping(
            binding_record(
                adapter,
                ["elmos.scm.v2"],
                environment_refs={"PATH": "CALLER_PATH"},
            )
        )

    symlink = tmp_path / "adapter-link"
    os.symlink(adapter, symlink)
    with pytest.raises(KernelError, match="COMMAND_PATH_INVALID"):
        CommandBinding.from_mapping(binding_record(symlink, ["elmos.scm.v2"]))


def test_external_qualification_schema_owns_exact_provider_set():
    schema_path = Path(__file__).resolve().parents[1] / "contracts" / "external-qualification-manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    providers = schema["$defs"]["providers"]

    assert providers["additionalProperties"] is False
    assert set(providers["required"]) == set(PROVIDER_PROFILES)
    assert set(providers["properties"]) == set(PROVIDER_PROFILES)
