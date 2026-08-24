import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conftest import PROJECT_PATH, ROOT
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from elmos_execution_intelligence import provenance as provenance_module
from elmos_execution_intelligence.certifier import (
    EVIDENCE_INPUT_FILES,
    build_evidence_manifest,
    evaluate,
)
from elmos_execution_intelligence.jsonschema_lite import Validator
from elmos_execution_intelligence.provenance import attestation_payload


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _full_evidence(root: Path, calibration_samples: int = 40) -> None:
    root.mkdir()
    envelope = {
        "mean": 1.0,
        "p50": 1.0,
        "p80": 1.0,
        "p90": 1.0,
        "worst_case": 1.0,
        "minimum": 1.0,
        "maximum": 1.0,
    }
    profile = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    profile["confidence"] = 0.75
    categories = ("input", "cached_input", "cache_write", "output", "reasoning_output")
    side = {
        "counts": {category: 20 for category in categories},
        "total": 100,
        "mix": {category: 0.2 for category in categories},
    }
    values = {
        "project-forecast.json": {
            "schema_version": "1.0.0",
            "project": profile,
            "tokens": {
                **{category: envelope for category in categories},
                "total": envelope,
                "category_sum_equals_total": True,
            },
            "task_tokens": [],
            "costs": {
                "models": [{"not_for_billing": False}],
                "rankings_by_currency": {},
                "cross_currency_comparison": None,
            },
            "system_runtime": {
                "wall_clock_hours": envelope,
                "active_worker_hours": envelope,
                "critical_path_hours": envelope,
                "excludes": ["human approvals"],
            },
            "human_effort": {
                "person_hours": envelope,
                "person_days": envelope,
                "person_months": envelope,
                "calendar_weeks": envelope,
                "same_definition_of_done": True,
            },
            "comparison": {
                "definition_of_done": "same",
                "comparison": "bounded",
                "confidence": 0.75,
                "assumptions": [],
                "exclusions": [],
            },
        },
        "risk-and-gap-register.json": {
            "schema_version": "1.0.0",
            "artifact": "risk-and-gap-register",
            "gaps": [],
            "counts_by_severity": {"high": 0, "medium": 0, "low": 0},
            "rule": "No open gap is hidden.",
        },
        "calibration.json": {
            "schema_version": "1.0.0",
            "valid_samples": calibration_samples,
            "runtime_samples": calibration_samples,
            "token_samples": calibration_samples,
            "global": {
                "runtime_multiplier": envelope,
                "token_multiplier": envelope,
                "confidence": 1.0,
            },
            "groups": {},
            "rule": "Measured samples only.",
        },
        "chaos-test-report.json": {
            "schema_version": "1.0.0",
            "artifact": "chaos-test-report",
            "scenarios": [{
                "scenario": "restart",
                "passed": True,
                "assertions": [{"name": "recovered", "ok": True}],
                "narrative": "Recovered without loss.",
            }],
            "scenarios_not_run": [],
            "passed": True,
            "counts": {"run": 1, "passed": 1, "failed": 0, "not_run": 0},
            "rule": "Every declared scenario is accounted for.",
        },
        "result-manifest.json": {
            "schema_version": "1.0.0",
            "artifact": "result-manifest",
            "run_id": "run-001",
            "sealed": True,
            "artifact_count": 1,
            "artifacts": [{
                "logical_name": "result.json",
                "version": 1,
                "sha256": "0" * 64,
                "size_bytes": 2,
                "storage_uri": "file:///evidence/result.json",
            }],
            "manifest_sha256": "1" * 64,
            "verification": "digest-bound",
        },
        "model-routing-plan.json": {
            "schema_version": "1.0.0",
            "artifact": "model-routing-plan",
            "currency": "USD",
            "assignments": [],
            "unroutable_tasks": [],
            "totals": {"optimized": 0, "frontier_baseline": 0, "saving": 0},
            "optimised_within_currency_only": True,
            "caveats": ["Test fixture only."],
        },
        "token-mix-comparison.json": {
            "schema_version": "1.0.0",
            "artifact": "token-mix-comparison",
            "project_tokens_p50": 100,
            "forecast": side,
            "observed": {**side, "sessions": 25, "models": ["model-a"]},
            "by_category": [
                {
                    "category": category,
                    "forecast_share": 0.2,
                    "observed_share": 0.2,
                    "delta_share": 0.0,
                    "ratio": 1.0,
                }
                for category in categories
            ],
            "cost_restatement": [],
            "cross_currency_comparison": None,
            "sample_sufficient": True,
            "minimum_sessions": 20,
            "applied_to_forecast": False,
            "caveats": ["Test fixture only."],
        },
    }
    for name, value in values.items():
        _write_json(root / name, value)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _public_key(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _sign_evidence(
    evidence: Path,
    trust_store: Path,
    now: datetime,
    *,
    same_principal: bool = False,
    same_organization: bool = False,
    same_authority: bool = False,
    revoked_role: str | None = None,
    expired_role: str | None = None,
    min_calibration_samples: int = 20,
) -> str:
    executor_key = Ed25519PrivateKey.generate()
    verifier_key = Ed25519PrivateKey.generate()
    key_specs = [
        ("executor", "executor-key", "runner-principal", "runner-org", "runner-authority", executor_key),
        (
            "independent_verifier",
            "verifier-key",
            "runner-principal" if same_principal else "assurance-principal",
            "runner-org" if same_organization else "assurance-org",
            "runner-authority" if same_organization or same_authority else "assurance-authority",
            verifier_key,
        ),
    ]
    trust = {
        "schema_version": "1.0.0",
        "artifact": "evidence-trust-store",
        "trust_store_id": "ci-assurance-root",
        "keys": [
            {
                "key_id": key_id,
                "principal_id": principal_id,
                "organization_id": organization_id,
                "authority_id": authority_id,
                "role": role,
                "algorithm": "Ed25519",
                "public_key_base64": _public_key(private_key),
                "not_before": _timestamp(now - timedelta(days=1)),
                "expires_at": _timestamp(
                    now - timedelta(seconds=1) if role == expired_role else now + timedelta(days=1)
                ),
                "revoked": role == revoked_role,
            }
            for role, key_id, principal_id, organization_id, authority_id, private_key in key_specs
        ],
    }
    _write_json(trust_store, trust)
    files = []
    for name in sorted(name for name in EVIDENCE_INPUT_FILES if (evidence / name).is_file()):
        content = (evidence / name).read_bytes()
        files.append({
            "path": name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        })
    provenance = {
        "schema_version": "1.0.0",
        "artifact": "evidence-provenance",
        "issued_at": _timestamp(now - timedelta(minutes=1)),
        "expires_at": _timestamp(now + timedelta(hours=1)),
        "subject": {
            "evidence_set_id": "release-candidate-001",
            "policy": {
                "certifier": "elmos-execution-intelligence",
                "policy_version": "2.0.0",
                "min_calibration_samples": min_calibration_samples,
                "required_roles": ["executor", "independent_verifier"],
            },
            "files": files,
        },
        "attestations": [
            {"role": role, "key_id": key_id, "signed_at": _timestamp(now), "signature": ""}
            for role, key_id, _, _, _, _ in key_specs
        ],
    }
    for attestation, (_, _, _, _, _, private_key) in zip(
        provenance["attestations"], key_specs, strict=True
    ):
        signature = private_key.sign(attestation_payload(provenance, attestation))
        attestation["signature"] = base64.b64encode(signature).decode("ascii")
    _write_json(evidence / "evidence-provenance.json", provenance)
    return hashlib.sha256(trust_store.read_bytes()).hexdigest()


def test_valid_digest_bound_dual_signature_can_reach_release(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    trust_pin = _sign_evidence(evidence, trust_store, now)

    report = evaluate(
        evidence,
        trust_store=trust_store,
        trust_store_sha256=trust_pin,
        now=now,
    )

    assert report["decision"] == "release"
    assert report["evidence_schema"]["status"] == "VALID"
    assert report["evidence_provenance"]["status"] == "VERIFIED"
    assert {item["principal_id"] for item in report["evidence_provenance"]["signers"]} == {
        "runner-principal", "assurance-principal",
    }
    manifest = build_evidence_manifest(report, evidence)
    validator = Validator(ROOT / "schemas")
    assert validator.validate(report, "production-readiness.schema.json") == []
    assert validator.validate(manifest, "evidence-manifest.schema.json") == []
    assert manifest["provenance"]["status"] == "VERIFIED"
    assert manifest["invalid_evidence"] == []
    assert all(
        item["provenance_bound"]
        for item in manifest["files"]
        if item["path"] != "evidence-provenance.json"
    )


def test_schema_invalid_but_correctly_signed_artifact_is_an_explicit_block(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    _write_json(evidence / "project-forecast.json", {
        "tokens": [],
        "project": [],
        "system_runtime": [],
        "costs": {"models": [None]},
    })
    trust_pin = _sign_evidence(evidence, trust_store, now)

    report = evaluate(
        evidence,
        trust_store=trust_store,
        trust_store_sha256=trust_pin,
        now=now,
    )

    schema_gate = next(item for item in report["gates"] if item["id"] == "evidence-schema-valid")
    assert report["decision"] == "block"
    assert schema_gate["status"] == "FAIL"
    assert "project-forecast.json" in schema_gate["detail"]
    assert report["evidence_provenance"]["status"] == "VERIFIED"


def test_tampering_after_signature_blocks(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    trust_pin = _sign_evidence(evidence, trust_store, now)
    _write_json(evidence / "calibration.json", {
        "valid_samples": 41,
        "runtime_samples": 41,
        "token_samples": 41,
    })

    report = evaluate(evidence, trust_store=trust_store, trust_store_sha256=trust_pin, now=now)

    assert report["decision"] == "block"
    assert "signed digest and size" in report["evidence_provenance"]["errors"][0]


def test_executor_and_verifier_cannot_be_the_same_principal(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    trust_pin = _sign_evidence(evidence, trust_store, now, same_principal=True)

    report = evaluate(evidence, trust_store=trust_store, trust_store_sha256=trust_pin, now=now)

    assert report["decision"] == "block"
    assert "different principal_id" in report["evidence_provenance"]["errors"][0]


def test_two_keys_from_the_same_organization_are_not_independent(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    trust_pin = _sign_evidence(evidence, trust_store, now, same_organization=True)

    report = evaluate(evidence, trust_store=trust_store, trust_store_sha256=trust_pin, now=now)

    assert report["decision"] == "block"
    assert "different organization_id" in report["evidence_provenance"]["errors"][0]


def test_two_organizations_under_the_same_authority_are_not_independent(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    trust_pin = _sign_evidence(evidence, trust_store, now, same_authority=True)

    report = evaluate(evidence, trust_store=trust_store, trust_store_sha256=trust_pin, now=now)

    assert report["decision"] == "block"
    assert "different authority_id" in report["evidence_provenance"]["errors"][0]


def test_revoked_verifier_key_blocks(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    trust_pin = _sign_evidence(
        evidence,
        trust_store,
        now,
        revoked_role="independent_verifier",
    )

    report = evaluate(evidence, trust_store=trust_store, trust_store_sha256=trust_pin, now=now)

    assert report["decision"] == "block"
    assert "revoked" in report["evidence_provenance"]["errors"][0]


def test_expired_executor_key_blocks(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    trust_pin = _sign_evidence(evidence, trust_store, now, expired_role="executor")

    report = evaluate(evidence, trust_store=trust_store, trust_store_sha256=trust_pin, now=now)

    assert report["decision"] == "block"
    assert "key validity window" in report["evidence_provenance"]["errors"][0]


def test_unpinned_or_colocated_trust_store_blocks(tmp_path):
    evidence = tmp_path / "evidence"
    external_trust = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    trust_pin = _sign_evidence(evidence, external_trust, now)

    unpinned = evaluate(evidence, trust_store=external_trust, now=now)
    assert unpinned["decision"] == "block"
    assert "pin is required" in unpinned["evidence_provenance"]["errors"][0]

    colocated = evidence / "evidence-trust-store.json"
    colocated.write_bytes(external_trust.read_bytes())
    colocated_report = evaluate(
        evidence,
        trust_store=colocated,
        trust_store_sha256=trust_pin,
        now=now,
    )
    assert colocated_report["decision"] == "block"
    assert "outside the evidence directory" in colocated_report["evidence_provenance"]["errors"][0]


def test_sample_floor_cannot_be_lowered_by_cli_value(tmp_path):
    evidence = tmp_path / "evidence"
    _full_evidence(evidence, calibration_samples=3)

    report = evaluate(evidence, min_calibration_samples=1)
    calibrated = next(item for item in report["gates"] if item["id"] == "calibrated")

    assert calibrated["status"] == "FAIL"
    assert "门槛 20" in calibrated["detail"]


def test_gate_and_signature_share_one_read_once_snapshot(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    trust_pin = _sign_evidence(evidence, trust_store, now)
    real_reader = provenance_module.read_regular_file_once
    reads: dict[Path, int] = {}

    def shifting_reader(path, max_bytes=provenance_module.MAX_EVIDENCE_FILE_BYTES):
        source = Path(path)
        reads[source] = reads.get(source, 0) + 1
        if source.name == "calibration.json" and reads[source] > 1:
            return b'{"valid_samples":0,"runtime_samples":0,"token_samples":0}'
        return real_reader(source, max_bytes=max_bytes)

    monkeypatch.setattr(provenance_module, "read_regular_file_once", shifting_reader)

    report = evaluate(evidence, trust_store=trust_store, trust_store_sha256=trust_pin, now=now)

    assert report["decision"] == "release"
    assert reads[evidence / "calibration.json"] == 1


def test_duplicate_json_keys_are_refused_before_signature_verification(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    trust_pin = _sign_evidence(evidence, trust_store, now)
    provenance = evidence / "evidence-provenance.json"
    text = provenance.read_text(encoding="utf-8")
    provenance.write_text(
        text.replace('"artifact": "evidence-provenance",',
                     '"artifact": "evidence-provenance",\n  "artifact": "evidence-provenance",'),
        encoding="utf-8",
    )

    report = evaluate(evidence, trust_store=trust_store, trust_store_sha256=trust_pin, now=now)

    assert report["decision"] == "block"
    assert "duplicate JSON key" in report["evidence_provenance"]["errors"][0]
