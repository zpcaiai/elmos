from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _module() -> ModuleType:
    path = Path(__file__).with_name("run_generation_external_gate.py")
    spec = importlib.util.spec_from_file_location("run_generation_external_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_matrix(directory: Path, module: ModuleType, *, verifier: str = "verifier-b") -> None:
    logs = directory / "logs"
    logs.mkdir()
    observed = "2026-09-13T00:00:00+00:00"
    engine_sha = module.source_identity(module.ENGINE_ROOT)["sha256"]
    checks = {name: "PASSED" for name in module.REQUIRED_CHECKS}
    for language in module.SUPPORTED_LANGUAGES:
        for auth_mode in module.AUTH_MODES:
            evidence_path = logs / f"{language}-{auth_mode}.log"
            evidence_path.write_text(f"external runtime {language}/{auth_mode}\n", encoding="utf-8")
            receipt = {
                "kind": "elmos.project-synthesis.external-runtime-receipt",
                "schema_version": "1.0.0",
                "language": language,
                "auth_mode": auth_mode,
                "status": "PASSED",
                "environment_class": "EXTERNAL_HOSTED",
                "observed_at": observed,
                "executor": "executor-a",
                "verifier": verifier,
                "evidence_subject": {
                    "engine_source_sha256": engine_sha,
                    "generated_artifact_sha256": "a" * 64,
                },
                "provider": {
                    "service": "AWS_RDS",
                    "database_engine": "postgresql",
                    "database_version": "17.5",
                    "ssl_verified": True,
                    "minimum_tls": "TLSv1.3",
                    "region": "cn-test-1",
                },
                "checks": checks,
                "evidence": [
                    {
                        "path": evidence_path.relative_to(directory).as_posix(),
                        "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                    }
                ],
            }
            target = directory / f"{language}-{auth_mode}.receipt.json"
            target.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")


def test_external_gate_requires_all_real_content_addressed_profiles(tmp_path: Path) -> None:
    module = _module()
    _write_matrix(tmp_path, module)
    result = module.run_gate(tmp_path, now=dt.datetime(2026, 9, 14, tzinfo=dt.UTC))
    assert result["status"] == "PASSED_EXTERNAL"
    assert result["decision"] == "READY_FOR_INDEPENDENT_CERTIFICATION"
    assert result["validated_profile_count"] == 16
    assert result["certification_status"] == "NOT_CERTIFIED"


def test_external_gate_fails_closed_without_independent_verifier(tmp_path: Path) -> None:
    module = _module()
    _write_matrix(tmp_path, module, verifier="executor-a")
    result = module.run_gate(tmp_path, now=dt.datetime(2026, 9, 14, tzinfo=dt.UTC))
    assert result["status"] == "BLOCKED"
    assert result["decision"] == "NOT_CERTIFIED"
    assert all(
        "INDEPENDENT_VERIFIER_REQUIRED" in receipt["reasons"]
        for receipt in result["receipts"]
    )


def test_external_gate_does_not_treat_an_empty_directory_as_execution(tmp_path: Path) -> None:
    result = _module().run_gate(tmp_path, now=dt.datetime(2026, 9, 14, tzinfo=dt.UTC))
    assert result["status"] == "BLOCKED"
    assert len(result["missing_profiles"]) == 16
