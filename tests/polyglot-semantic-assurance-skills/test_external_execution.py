"""Host-authorized external execution and evidence boundary tests."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

from elmos_polyglot_compiler.contracts import AuthorityError, ContractError, ExecutionAuthority
from elmos_polyglot_compiler.evidence import validate_evidence_receipt
from elmos_polyglot_compiler.external import (
    ExternalExecutionSpec,
    ExternalRunner,
    ProviderRegistry,
    ToolchainDescriptor,
    build_execution_receipt,
    execution_subject_digest,
)
from elmos_polyglot_compiler.catalog import load_catalog
from elmos_polyglot_compiler.runtime import SkillRuntime
from elmos_polyglot_compiler.store import SqliteExecutionStore
from elmos_polyglot_compiler.evidence import ContentAddressedArtifactStore


REVISION = "sha256:" + "a" * 64


def _request(*, skill: str, inputs: dict) -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "external-request",
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "actor_id": "actor-1",
        "revision_digest": REVISION,
        "environment_authority_id": "environment-1",
        "idempotency_key": "external-run",
        "inputs": inputs,
    }


def _authority(
    skill: str,
    *,
    effects: frozenset[str],
    providers: frozenset[str] = frozenset(),
) -> ExecutionAuthority:
    return ExecutionAuthority(
        tenant_id="tenant-1",
        project_id="project-1",
        actor_id="actor-1",
        revision_digest=REVISION,
        environment_authority_id="environment-1",
        allowed_skills=frozenset({skill}),
        allowed_effects=effects,
        allowed_providers=providers,
    )


def _runner(tmp_path: Path) -> ExternalRunner:
    executable = str(Path(sys.executable).resolve())
    descriptor = ToolchainDescriptor(
        toolchain_id="python",
        executable=executable,
        path_entries=(str(Path(executable).parent),),
    )
    return ExternalRunner(
        sandbox_root=(tmp_path / "sandboxes").resolve(),
        toolchains={"python": descriptor},
    )


def _profile(code: str, *, argument: str = "safe") -> dict:
    return {
        "toolchain_id": "python",
        "argv": ["-c", code, argument],
        "files": {"input.txt": "trusted input"},
        "stdin": "",
        "cwd": ".",
        "timeout_ms": 5_000,
        "network_policy": "disabled",
    }


def test_external_runner_executes_in_ephemeral_sandbox_without_shell(tmp_path: Path):
    runner = _runner(tmp_path)
    request_value = _request(skill="skill-1", inputs={})
    from elmos_polyglot_compiler.contracts import RuntimeRequest

    request = RuntimeRequest.parse(request_value)
    authority = _authority(
        "skill-1",
        effects=frozenset({"external-execution", "toolchain:python"}),
    )
    result = runner.run(
        _profile(
            "import pathlib,sys; print(sys.argv[1]); print(pathlib.Path('input.txt').read_text())",
            argument="$(touch SHOULD_NOT_EXIST)",
        ),
        request=request,
        authority=authority,
    )
    assert result.exit_code == 0
    assert "$(touch SHOULD_NOT_EXIST)" in result.stdout
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()
    assert not list((tmp_path / "sandboxes").glob("run-*/input.txt"))


def test_external_runner_rejects_missing_effect_and_network(tmp_path: Path):
    runner = _runner(tmp_path)
    from elmos_polyglot_compiler.contracts import RuntimeRequest

    request = RuntimeRequest.parse(_request(skill="skill-1", inputs={}))
    with pytest.raises(AuthorityError):
        runner.run(
            _profile("print('no')"),
            request=request,
            authority=_authority("skill-1", effects=frozenset()),
        )
    with pytest.raises(ContractError):
        ExternalExecutionSpec.parse({**_profile("print('no')"), "network_policy": "enabled"})


def test_external_runner_enforces_timeout_and_capture_limit(tmp_path: Path):
    runner = _runner(tmp_path)
    from elmos_polyglot_compiler.contracts import RuntimeRequest
    from elmos_polyglot_compiler.external import MAX_CAPTURE_BYTES

    request = RuntimeRequest.parse(_request(skill="skill-1", inputs={}))
    authority = _authority(
        "skill-1",
        effects=frozenset({"external-execution", "toolchain:python"}),
    )
    timeout_profile = _profile("import time; time.sleep(2)")
    timeout_profile["timeout_ms"] = 25
    timed_out = runner.run(timeout_profile, request=request, authority=authority)
    assert timed_out.timed_out is True
    assert timed_out.exit_code is None

    output_profile = _profile("print('x' * 1000000)")
    bounded = runner.run(output_profile, request=request, authority=authority)
    assert len(bounded.stdout.encode("utf-8")) <= MAX_CAPTURE_BYTES


def test_runtime_records_unverified_external_execution_without_certifying(tmp_path: Path):
    catalog = load_catalog()
    definition = next(item for item in catalog.skills if item.operation_family == "formal-assurance")
    runtime = SkillRuntime(
        state_store=SqliteExecutionStore((tmp_path / "state.sqlite3").resolve()),
        artifact_store=ContentAddressedArtifactStore((tmp_path / "artifacts").resolve()),
        catalog=catalog,
        external_runner=_runner(tmp_path),
    )
    result = runtime.execute(
        definition.name,
        _request(
            skill=definition.name,
            inputs={
                "formula": "(check-sat)",
                "assumptions": [],
                "solver": "python-probe",
                "timeout_ms": 5_000,
                "evidence_receipts": [],
                "execution_profile": _profile("print('unknown')"),
            },
        ),
        authority=_authority(
            definition.name,
            effects=frozenset({"external-execution", "toolchain:python"}),
        ),
    )
    assert result["state"] == "BLOCKED"
    assert result["external_evidence"] == "EXTERNAL_EXECUTED_UNVERIFIED"
    assert result["certification"] == "NOT_CERTIFIED"
    assert result["outputs"]["external_execution_performed"] is True
    assert result["outputs"]["execution_result"]["exit_code"] == 0


def test_execution_receipt_requires_host_minted_digest(tmp_path: Path):
    runner = _runner(tmp_path)
    from elmos_polyglot_compiler.contracts import RuntimeRequest

    request = RuntimeRequest.parse(_request(skill="skill-1", inputs={}))
    authority = _authority(
        "skill-1",
        effects=frozenset({"external-execution", "toolchain:python"}),
    )
    result = runner.run(
        _profile("print('evidence')"), request=request, authority=authority
    )
    receipt = build_execution_receipt(
        result,
        request=request,
        evidence_type="native-route-test",
        producer_id="runner-1",
        verifier_id="verifier-2",
        artifact_digest="sha256:" + "b" * 64,
        independent=True,
    )
    status, code, receipt_digest = validate_evidence_receipt(
        receipt,
        request=request,
        authority=authority,
        expected_subject_digest=execution_subject_digest(result),
    )
    assert status.value == "EXTERNAL_EXECUTED_UNVERIFIED"
    assert code == "HOST_VERIFICATION_MISSING"
    assert receipt_digest is not None
    verified_authority = ExecutionAuthority(
        **{
            **authority.__dict__,
            "verified_evidence_digests": frozenset({receipt_digest}),
        }
    )
    status, code, _ = validate_evidence_receipt(
        receipt,
        request=request,
        authority=verified_authority,
        expected_subject_digest=execution_subject_digest(result),
    )
    assert status.value == "INDEPENDENTLY_VERIFIED"
    assert code == "EVIDENCE_VERIFIED"


def test_provider_registry_requires_explicit_host_adapter_and_effect():
    class Adapter:
        provider_id = "provider-1"

        def invoke(self, request, authority, payload):
            return {"request": request.request_id, "payload": dict(payload)}

    registry = ProviderRegistry([Adapter()])
    from elmos_polyglot_compiler.contracts import RuntimeRequest

    request = RuntimeRequest.parse(_request(skill="skill-1", inputs={}))
    authority = _authority(
        "skill-1",
        effects=frozenset({"provider-call", "provider:provider-1"}),
        providers=frozenset({"provider-1"}),
    )
    assert registry.invoke("provider-1", request, authority, {"op": "probe"})["request"] == (
        "external-request"
    )


def test_runtime_provider_profile_is_observation_only(tmp_path: Path):
    class Adapter:
        provider_id = "provider-1"

        def invoke(self, request, authority, payload):
            return {"request": request.request_id, "payload": dict(payload)}

    runner = ExternalRunner(
        sandbox_root=(tmp_path / "sandboxes").resolve(),
        toolchains={},
        providers=ProviderRegistry([Adapter()]),
    )
    catalog = load_catalog()
    definition = next(item for item in catalog.skills if item.operation_family == "route-execution")
    runtime = SkillRuntime(
        state_store=SqliteExecutionStore((tmp_path / "state.sqlite3").resolve()),
        artifact_store=ContentAddressedArtifactStore((tmp_path / "artifacts").resolve()),
        catalog=catalog,
        external_runner=runner,
    )
    result = runtime.execute(
        definition.name,
        _request(
            skill=definition.name,
            inputs={
                "route_id": catalog.routes[0].route_id,
                "source_artifact": "sha256:" + "a" * 64,
                "target_profile": {"language": "python"},
                "evidence_receipts": [],
                "provider_profile": {
                    "provider_id": "provider-1",
                    "payload": {"operation": "observe"},
                },
            },
        ),
        authority=_authority(
            definition.name,
            effects=frozenset({"provider-call", "provider:provider-1"}),
            providers=frozenset({"provider-1"}),
        ),
    )
    assert result["state"] == "SUCCEEDED"
    assert result["external_evidence"] == "EXTERNAL_EXECUTED_UNVERIFIED"
    assert result["certification"] == "NOT_CERTIFIED"
    assert result["outputs"]["provider_result"]["payload"]["operation"] == "observe"
