import base64
import hashlib
import http.server
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import PROJECT_PATH, ROOT
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from elmos_execution_intelligence import provenance as provenance_module
from elmos_execution_intelligence.certifier import (
    EVIDENCE_INPUT_FILES,
    build_evidence_manifest,
    evaluate,
)
from elmos_execution_intelligence.external_trust import (
    ExternalTrustError,
    ExternalTrustOptions,
    external_trust_signature_payload,
    load_external_trust,
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


def _external_trust_options(
    trust_store: Path,
    root_path: Path,
    snapshot_path: Path,
    epoch_state: Path,
    now: datetime,
    *,
    issuer_id: str = "external-trust-governance",
    epoch: int = 42,
    unknown_key: str | None = None,
    revoked_key: str | None = None,
    authority_url: str | None = None,
    cache_path: Path | None = None,
) -> ExternalTrustOptions:
    authority_key = Ed25519PrivateKey.generate()
    authority_key_id = "external-authority-key"
    root = {
        "schema_version": "1.0.0",
        "artifact": "evidence-trust-authority-root",
        "issuer_id": issuer_id,
        "key_id": authority_key_id,
        "algorithm": "Ed25519",
        "public_key_base64": _public_key(authority_key),
        "not_before": _timestamp(now - timedelta(days=1)),
        "expires_at": _timestamp(now + timedelta(days=1)),
        "authority_url": authority_url,
        "minimum_epoch": 1,
        "max_snapshot_lifetime_seconds": 3600,
        "max_revocation_age_seconds": 900,
        "separate_from_evidence_authorities": True,
    }
    _write_json(root_path, root)
    trust = json.loads(trust_store.read_text(encoding="utf-8"))
    canonical_trust = json.dumps(
        trust,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    key_ids = sorted(str(item["key_id"]) for item in trust["keys"])
    payload = {
        "schema_version": "1.0.0",
        "artifact": "external-evidence-trust-snapshot",
        "issuer_id": issuer_id,
        "issuer_key_id": authority_key_id,
        "snapshot_id": f"snapshot-{epoch}",
        "epoch": epoch,
        "issued_at": _timestamp(now - timedelta(minutes=1)),
        "expires_at": _timestamp(now + timedelta(minutes=30)),
        "etag": f'"epoch-{epoch}"',
        "trust_store_sha256": hashlib.sha256(canonical_trust).hexdigest(),
        "trust_store": trust,
        "revocations": [
            {
                "key_id": key_id,
                "status": (
                    "UNKNOWN"
                    if key_id == unknown_key
                    else "REVOKED" if key_id == revoked_key else "GOOD"
                ),
                "checked_at": _timestamp(now - timedelta(seconds=30)),
                "next_update": _timestamp(now + timedelta(minutes=5)),
            }
            for key_id in key_ids
        ],
    }
    signature = authority_key.sign(external_trust_signature_payload(payload))
    _write_json(snapshot_path, {
        "payload": payload,
        "signature": {
            "algorithm": "Ed25519",
            "signature_base64": base64.b64encode(signature).decode("ascii"),
        },
    })
    return ExternalTrustOptions(
        authority_root_path=root_path,
        authority_root_sha256=hashlib.sha256(root_path.read_bytes()).hexdigest(),
        snapshot_path=snapshot_path if authority_url is None else None,
        source_url=authority_url,
        cache_path=cache_path,
        expected_snapshot_sha256=hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        expected_etag=f'"epoch-{epoch}"',
        epoch_state_path=epoch_state,
    )


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


def test_external_authority_snapshot_can_drive_provenance_verification(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    _sign_evidence(evidence, trust_store, now)
    options = _external_trust_options(
        trust_store,
        tmp_path / "authority-root.json",
        tmp_path / "trust-snapshot.json",
        tmp_path / "epoch-state.json",
        now,
    )

    report = evaluate(evidence, external_trust_options=options, now=now)

    assert report["decision"] == "release"
    authority = report["evidence_provenance"]["trust_authority"]
    assert authority["issuer_id"] == "external-trust-governance"
    assert authority["epoch"] == 42
    assert authority["source"] == "replay-file"
    assert authority["revocation_status_count"] == 2


def test_external_authority_unknown_revocation_fails_closed(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    _sign_evidence(evidence, trust_store, now)
    options = _external_trust_options(
        trust_store,
        tmp_path / "authority-root.json",
        tmp_path / "trust-snapshot.json",
        tmp_path / "epoch-state.json",
        now,
        unknown_key="verifier-key",
    )

    report = evaluate(evidence, external_trust_options=options, now=now)

    assert report["decision"] == "block"
    assert "returned UNKNOWN" in report["evidence_provenance"]["errors"][0]


def test_external_authority_cannot_be_the_verifier_authority(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    _sign_evidence(evidence, trust_store, now)
    options = _external_trust_options(
        trust_store,
        tmp_path / "authority-root.json",
        tmp_path / "trust-snapshot.json",
        tmp_path / "epoch-state.json",
        now,
        issuer_id="assurance-authority",
    )

    report = evaluate(evidence, external_trust_options=options, now=now)

    assert report["decision"] == "block"
    assert "separate from every evidence authority" in report["evidence_provenance"]["errors"][0]


def test_external_authority_revocation_blocks_a_valid_evidence_signature(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    _sign_evidence(evidence, trust_store, now)
    options = _external_trust_options(
        trust_store,
        tmp_path / "authority-root.json",
        tmp_path / "trust-snapshot.json",
        tmp_path / "epoch-state.json",
        now,
        revoked_key="executor-key",
    )

    report = evaluate(evidence, external_trust_options=options, now=now)

    assert report["decision"] == "block"
    assert "revoked key: executor-key" in report["evidence_provenance"]["errors"][0]


def test_online_snapshot_revalidates_and_uses_only_fresh_signed_cache(tmp_path):
    class SnapshotHandler(http.server.BaseHTTPRequestHandler):
        snapshot = b""
        etag = '"epoch-42"'

        def do_GET(self):
            if self.headers.get("If-None-Match") == self.etag:
                self.send_response(304)
                self.send_header("ETag", self.etag)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/trust+json")
            self.send_header("ETag", self.etag)
            self.send_header("Content-Length", str(len(self.snapshot)))
            self.end_headers()
            self.wfile.write(self.snapshot)

        def log_message(self, format, *args):
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SnapshotHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        evidence = tmp_path / "evidence"
        trust_store = tmp_path / "trust-store.json"
        snapshot_path = tmp_path / "trust-snapshot.json"
        cache_path = tmp_path / "trust-cache.json"
        now = datetime.now(timezone.utc).replace(microsecond=0)
        _full_evidence(evidence)
        _sign_evidence(evidence, trust_store, now)
        host, port = server.server_address
        authority_url = f"http://{host}:{port}/v1/trust-snapshot"
        options = _external_trust_options(
            trust_store,
            tmp_path / "authority-root.json",
            snapshot_path,
            tmp_path / "epoch-state.json",
            now,
            authority_url=authority_url,
            cache_path=cache_path,
        )
        SnapshotHandler.snapshot = snapshot_path.read_bytes()

        online = load_external_trust(options, now=now, forbidden_root=evidence)
        revalidated = load_external_trust(options, now=now, forbidden_root=evidence)

        assert online.receipt["source"] == "online"
        assert revalidated.receipt["source"] == "cache-revalidated"
        assert cache_path.read_bytes() == snapshot_path.read_bytes()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    cached = load_external_trust(options, now=now, forbidden_root=evidence)
    assert cached.receipt["source"] == "cache-fallback"


def test_external_trust_epoch_state_rejects_rollback(tmp_path):
    evidence = tmp_path / "evidence"
    trust_store = tmp_path / "trust-store.json"
    root_path = tmp_path / "authority-root.json"
    snapshot_path = tmp_path / "trust-snapshot.json"
    epoch_state = tmp_path / "epoch-state.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _full_evidence(evidence)
    _sign_evidence(evidence, trust_store, now)
    current = _external_trust_options(
        trust_store,
        root_path,
        snapshot_path,
        epoch_state,
        now,
        epoch=42,
    )
    load_external_trust(current, now=now, forbidden_root=evidence)
    rollback = _external_trust_options(
        trust_store,
        root_path,
        snapshot_path,
        epoch_state,
        now,
        epoch=41,
    )

    with pytest.raises(ExternalTrustError, match="epoch rollback"):
        load_external_trust(rollback, now=now, forbidden_root=evidence)
