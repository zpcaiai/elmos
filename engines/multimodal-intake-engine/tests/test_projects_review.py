from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from elmos_multimodal_intake.projects import (
    ProjectContractError,
    build_package_review_view,
)


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _request(inputs: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "actor_id": "actor-a",
        "inputs": inputs,
        **extra,
    }


def _trusted_snapshot(*, findings: list[dict[str, str]] | None = None) -> dict[str, Any]:
    content_digest = "sha256:" + "1" * 64
    identities = [{"path": "src/main.py", "content_digest": content_digest}]
    snapshot: dict[str, Any] = {
        "verified": True,
        "authorized": True,
        "receipt_id": "review-receipt-1",
        "registry_version": "review-registry-v1",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "package_version": "v1",
        "package_digest": "sha256:" + "2" * 64,
        "entries_digest": _digest(identities),
        "entries": [
            {
                **identities[0],
                "state": "READY",
                "classification": "SOURCE_CODE",
                "role": "SOURCE",
                "security_findings": findings or [],
            }
        ],
    }
    snapshot["snapshot_digest"] = _digest(snapshot)
    return snapshot


def _scoped_inputs(**entry_overrides: Any) -> dict[str, Any]:
    return {
        "package_version": "v1",
        "package_digest": "sha256:" + "2" * 64,
        "entries": [
            {
                "path": "src/main.py",
                "content_digest": "sha256:" + "1" * 64,
                **entry_overrides,
            }
        ],
    }


def test_input_cannot_self_attest_ready_security_or_classification() -> None:
    result = build_package_review_view(
        _request(
            _scoped_inputs(
                state="READY",
                classification="TRUSTED_SOURCE",
                role="ENTRYPOINT",
                security_findings=[{"code": "INPUT_SAYS_CLEAR", "severity": "NONE"}],
            )
        )
    )

    assert result["state"] == "PARTIAL"
    assert result["code"] == "PACKAGE_REVIEW_TRUSTED_SNAPSHOT_REQUIRED"
    assert result["outputs"]["readiness"] == "NOT_READY"
    assert result["outputs"]["review_authority"] == "NONE"
    assert result["outputs"]["external_evidence"] == "NOT_RUN"
    assert result["outputs"]["entries"] == [
        {
            "path": "src/main.py",
            "state": "PENDING",
            "classification": "UNCLASSIFIED",
            "role": "UNCLASSIFIED",
            "security_findings": [],
            "override_allowed": False,
        }
    ]


def test_exact_authorized_host_snapshot_is_the_only_ready_authority() -> None:
    snapshot = _trusted_snapshot()
    result = build_package_review_view(
        _request(
            _scoped_inputs(state="BLOCKED", classification="USER_ASSERTED"),
            capabilities={"package_review_snapshot": snapshot},
        )
    )

    assert result["state"] == "SUCCEEDED"
    assert result["code"] == "PACKAGE_REVIEW_VIEW_CREATED"
    assert result["outputs"]["readiness"] == "READY"
    assert result["outputs"]["review_authority"] == "capabilities.package_review_snapshot"
    assert result["outputs"]["review_snapshot_digest"] == snapshot["snapshot_digest"]
    assert result["outputs"]["entries"][0]["classification"] == "SOURCE_CODE"
    assert result["outputs"]["entries"][0]["state"] == "READY"


def test_wrong_scope_snapshot_cannot_raise_readiness() -> None:
    snapshot = _trusted_snapshot()
    snapshot["tenant_id"] = "tenant-b"
    snapshot["snapshot_digest"] = _digest(
        {key: value for key, value in snapshot.items() if key != "snapshot_digest"}
    )

    result = build_package_review_view(
        _request(
            _scoped_inputs(state="READY"),
            policy={"package_review_registry": {"snapshots": [snapshot]}},
        )
    )

    assert result["state"] == "PARTIAL"
    assert result["outputs"]["readiness"] == "NOT_READY"
    assert result["outputs"]["entries"][0]["state"] == "PENDING"


def test_matching_snapshot_must_be_authorized_and_digest_intact() -> None:
    unauthorized = _trusted_snapshot()
    unauthorized["authorized"] = False
    unauthorized["snapshot_digest"] = _digest(
        {key: value for key, value in unauthorized.items() if key != "snapshot_digest"}
    )
    with pytest.raises(ProjectContractError, match="not verified and authorized"):
        build_package_review_view(
            _request(
                _scoped_inputs(),
                capabilities={"package_review_snapshot": unauthorized},
            )
        )

    tampered = _trusted_snapshot()
    tampered["entries"][0]["classification"] = "TAMPERED"
    with pytest.raises(ProjectContractError, match="digest does not match"):
        build_package_review_view(
            _request(
                _scoped_inputs(),
                capabilities={"package_review_snapshot": tampered},
            )
        )


def test_security_findings_cannot_be_overridden_to_ready() -> None:
    snapshot = _trusted_snapshot(
        findings=[{"code": "MALWARE_DETECTED", "severity": "CRITICAL"}]
    )
    authorization = {
        "verified": True,
        "consent_granted": True,
        "receipt_id": "override-receipt-1",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "actor_id": "actor-a",
        "package_version": "v1",
        "package_digest": "sha256:" + "2" * 64,
        "review_snapshot_digest": snapshot["snapshot_digest"],
        "allowed_overrides": {
            "src/main.py": {"from": "BLOCKED", "to": "READY"}
        },
    }
    inputs = _scoped_inputs()
    inputs["overrides"] = {"src/main.py": "READY"}
    result = build_package_review_view(
        _request(
            inputs,
            capabilities={
                "package_review_snapshot": snapshot,
                "review_override_authorization": authorization,
            },
        )
    )

    assert result["state"] == "BLOCKED"
    assert result["outputs"]["readiness"] == "NOT_READY"
    assert result["outputs"]["rejected_overrides"] == [
        {"path": "src/main.py", "code": "SECURITY_FINDINGS_OVERRIDE_FORBIDDEN"}
    ]
