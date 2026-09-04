from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import elmos_sql_transpiler.production_qualification as qualification_module
from elmos_sql_transpiler.cli import main
from elmos_sql_transpiler.production_qualification import (
    REQUIRED_EXECUTION_ARTIFACT_DIGESTS,
    REQUIRED_EXECUTION_EVIDENCE_DIGESTS,
    REQUIRED_EXECUTION_INPUT_DIGESTS,
    REQUIRED_EXTERNAL_OPERATIONS,
    TRUST_DOMAIN,
    evaluate_production_qualification,
    parse_production_qualification_json,
    parse_production_trust_store_json,
    prepare_vendor_execution_request,
    production_qualification_draft,
    production_qualification_requirements,
    production_trust_store_digest,
    qualification_result_is_currently_fail_closed,
    signed_envelope,
    target_qualification_input_digest,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
_DIGEST = "sha256:" + "a" * 64


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _role_digest(target_id: str, role: str) -> str:
    value = f"{target_id}\x00{role}".encode()
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _public(private: Ed25519PrivateKey) -> str:
    raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _trust_material() -> tuple[dict[str, Any], dict[str, Ed25519PrivateKey]]:
    identities = {
        "auth-key": ("environment-authorizer", "customer-owner", "customer-org"),
        "executor-key": ("external-target-executor", "executor", "vendor-lab"),
        "verifier-key": ("independent-verifier", "verifier", "independent-lab"),
        "certifier-key": ("certification-authority", "certifier", "certification-org"),
    }
    private_keys = {key_id: Ed25519PrivateKey.generate() for key_id in identities}
    trust_store = {
        "schemaVersion": "1.0",
        "trustDomain": TRUST_DOMAIN,
        "keys": [
            {
                "keyId": key_id,
                "role": role,
                "actorId": actor,
                "organizationId": organization,
                "publicKey": _public(private_keys[key_id]),
                "notBefore": "2026-01-01T00:00:00Z",
                "notAfter": "2027-12-31T23:59:59Z",
                "revoked": False,
            }
            for key_id, (role, actor, organization) in identities.items()
        ],
    }
    return trust_store, private_keys


def _draft() -> dict[str, Any]:
    return production_qualification_draft(
        tenant_id="tenant-1",
        project_id="project-1",
        actor_id="implementer",
        implementer_organization_id="elmos-engineering",
    )


def _complete_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Ed25519PrivateKey]]:
    request = _draft()
    trust_store, keys = _trust_material()
    request["trustStoreDigest"] = production_trust_store_digest(trust_store)
    adapters = {
        target["targetId"]: target["adapterId"]
        for target in production_qualification_requirements()["targets"]
    }
    for target in request["targets"]:
        target_id = target["targetId"]
        target["exactTuple"] = {
            "productId": target_id,
            "productVersion": f"1.0.0-{target_id}",
            "edition": "enterprise-exact",
            "compatibilityMode": "native-explicit",
            "deploymentTopology": "single-node-disposable",
            "provider": f"vendor-{target_id}",
            "serviceTier": "licensed-sandbox",
            "region": "cn-test-1",
            "driver": {
                "name": f"driver-{target_id}",
                "version": "1.0.0-build.1",
                "artifactDigest": _DIGEST,
            },
            "charset": "UTF-8",
            "collation": "BINARY-EXACT",
            "timeZone": "Asia/Shanghai",
            "timeZoneDataVersion": "2026b",
            "sqlMode": "native-default-explicit",
            "extensions": [],
            "runtimeArtifactDigest": _DIGEST,
        }
        target["disposableEnvironment"] = {
            "environmentId": f"sandbox-{target_id}",
            "kind": "APPROVED_LICENSED_SANDBOX",
            "endpointRef": f"endpoint-ref-{target_id}",
            "credentialRef": f"credential-ref-{target_id}",
            "providerResourceRef": f"resource-ref-{target_id}",
            "dataProfile": "SYNTHETIC",
            "productionData": False,
            "writeScope": "DISPOSABLE_ONLY",
            "expiresAt": "2026-10-01T00:00:00Z",
            "cleanupDeadline": "2026-10-02T00:00:00Z",
        }
        target["vendorTools"] = [
            {
                "toolId": f"vendor-tool-{target_id}",
                "version": "1.0.0-build.1",
                "artifactDigest": _DIGEST,
                "licenseRef": f"license-ref-{target_id}",
                "adapterId": adapters[target_id],
                "operations": list(REQUIRED_EXTERNAL_OPERATIONS),
            }
        ]
        target["independentVerifier"] = {
            "verifierId": "independent-verifier-1",
            "actorId": "verifier",
            "organizationId": "independent-lab",
            "engagementRef": f"engagement-{target_id}",
        }
    return request, trust_store, keys


def _sign_all_receipts(
    request: dict[str, Any],
    trust_store: dict[str, Any],
    keys: dict[str, Ed25519PrivateKey],
) -> None:
    baseline = evaluate_production_qualification(request, trust_store=trust_store, now=NOW)
    for target, plan in zip(request["targets"], baseline["targets"], strict=True):
        target_id = target["targetId"]
        qualification_digest = plan["qualificationInputDigest"]
        authorization_payload = {
            "schemaVersion": "1.0",
            "kind": "CHINADB_TARGET_EXECUTION_AUTHORIZATION",
            "recordId": f"authorization-{target_id}",
            "scopeDigest": baseline["scopeDigest"],
            "targetId": target_id,
            "qualificationInputDigest": qualification_digest,
            "environmentId": target["disposableEnvironment"]["environmentId"],
            "implementerActorId": request["implementer"]["actorId"],
            "implementerOrganizationId": request["implementer"]["organizationId"],
            "allowedOperations": list(REQUIRED_EXTERNAL_OPERATIONS),
            "issuedAt": "2026-08-27T00:00:00Z",
            "expiresAt": "2026-09-30T00:00:00Z",
        }
        authorization = signed_envelope(
            key_id="auth-key",
            private_key=keys["auth-key"],
            payload=authorization_payload,
        )
        execution_payload = {
            "schemaVersion": "1.0",
            "kind": "CHINADB_TARGET_EXECUTION_RECEIPT",
            "recordId": f"execution-{target_id}",
            "authorizationRecordId": authorization_payload["recordId"],
            "authorizationEnvelopeDigest": _digest(authorization),
            "scopeDigest": baseline["scopeDigest"],
            "targetId": target_id,
            "qualificationInputDigest": qualification_digest,
            "environmentId": target["disposableEnvironment"]["environmentId"],
            "exactTupleDigest": plan["exactTupleDigest"],
            "vendorToolDigests": plan["vendorToolDigests"],
            "artifactDigests": {
                field: _role_digest(target_id, f"artifact:{field}")
                for field in REQUIRED_EXECUTION_ARTIFACT_DIGESTS
            },
            "evidenceDigests": {
                field: _role_digest(target_id, f"evidence:{field}")
                for field in REQUIRED_EXECUTION_EVIDENCE_DIGESTS
            },
            "executedAt": "2026-08-28T10:00:00Z",
            "checks": {
                "capabilityProbe": "PASSED",
                "cleanup": "PASSED",
                "dataReconciliation": "PASSED",
                "performanceSecurityRollback": "PASSED",
                "schemaTypeQueryRoutineTransaction": "PASSED",
                "targetApplyIntrospection": "PASSED",
                "targetRender": "PASSED",
                "versionProbe": "PASSED",
            },
            "criticalUnknowns": 0,
            "criticalDifferences": 0,
            "testIntegrityViolations": 0,
        }
        execution = signed_envelope(
            key_id="executor-key",
            private_key=keys["executor-key"],
            payload=execution_payload,
        )
        verification_payload = {
            "schemaVersion": "1.0",
            "kind": "CHINADB_INDEPENDENT_VERIFICATION_RECEIPT",
            "recordId": f"verification-{target_id}",
            "scopeDigest": baseline["scopeDigest"],
            "targetId": target_id,
            "qualificationInputDigest": qualification_digest,
            "executionRecordId": execution_payload["recordId"],
            "executionEnvelopeDigest": _digest(execution),
            "rawEvidenceDigest": execution_payload["evidenceDigests"]["rawEvidenceDigest"],
            "holdoutCorpusDigest": execution_payload["artifactDigests"]["holdoutCorpusDigest"],
            "representativeWorkloadDigest": execution_payload["artifactDigests"][
                "representativeWorkloadDigest"
            ],
            "decision": "PASSED",
            "criticalFindings": 0,
            "verifiedAt": "2026-08-28T11:00:00Z",
        }
        verification = signed_envelope(
            key_id="verifier-key",
            private_key=keys["verifier-key"],
            payload=verification_payload,
        )
        certification_payload = {
            "schemaVersion": "1.0",
            "kind": "CHINADB_PRODUCTION_CERTIFICATION_RECEIPT",
            "recordId": f"certification-{target_id}",
            "scopeDigest": baseline["scopeDigest"],
            "targetId": target_id,
            "qualificationInputDigest": qualification_digest,
            "verificationRecordId": verification_payload["recordId"],
            "verificationEnvelopeDigest": _digest(verification),
            "decision": "CERTIFIED",
            "certifiedAt": "2026-08-28T11:30:00Z",
            "expiresAt": "2027-08-28T00:00:00Z",
        }
        certification = signed_envelope(
            key_id="certifier-key",
            private_key=keys["certifier-key"],
            payload=certification_payload,
        )
        target["receipts"] = {
            "authorization": authorization,
            "execution": execution,
            "independentVerification": verification,
            "certification": certification,
        }


def _authorize_target(
    request: dict[str, Any],
    trust_store: dict[str, Any],
    keys: dict[str, Ed25519PrivateKey],
    target_index: int = 0,
) -> None:
    baseline = evaluate_production_qualification(request, trust_store=trust_store, now=NOW)
    target = request["targets"][target_index]
    plan = baseline["targets"][target_index]
    payload = {
        "schemaVersion": "1.0",
        "kind": "CHINADB_TARGET_EXECUTION_AUTHORIZATION",
        "recordId": f"authorization-{target['targetId']}",
        "scopeDigest": baseline["scopeDigest"],
        "targetId": target["targetId"],
        "qualificationInputDigest": plan["qualificationInputDigest"],
        "environmentId": target["disposableEnvironment"]["environmentId"],
        "implementerActorId": request["implementer"]["actorId"],
        "implementerOrganizationId": request["implementer"]["organizationId"],
        "allowedOperations": list(REQUIRED_EXTERNAL_OPERATIONS),
        "issuedAt": "2026-08-27T00:00:00Z",
        "expiresAt": "2026-09-30T00:00:00Z",
    }
    target["receipts"]["authorization"] = signed_envelope(
        key_id="auth-key", private_key=keys["auth-key"], payload=payload
    )


def test_requirements_and_draft_keep_every_production_boundary_closed() -> None:
    requirements = production_qualification_requirements()
    assert requirements["targetCount"] == 13
    assert len({item["targetId"] for item in requirements["targets"]}) == 13
    assert all(
        item["requiredArtifactDigests"] == list(REQUIRED_EXECUTION_ARTIFACT_DIGESTS)
        for item in requirements["targets"]
    )
    assert all(
        item["requiredEvidenceDigests"] == list(REQUIRED_EXECUTION_EVIDENCE_DIGESTS)
        for item in requirements["targets"]
    )
    assert requirements["productionBoundaries"] == {
        "externalExecution": "NOT_RUN",
        "independentVerification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "targetSql": None,
        "productionDefinitionOfDoneCount": 0,
    }
    result = evaluate_production_qualification(_draft(), now=NOW)
    assert qualification_result_is_currently_fail_closed(result)
    assert result["summary"] == {
        "targetCount": 13,
        "inputCompleteTargetCount": 0,
        "authorizationVerifiedTargetCount": 0,
        "externalExecutionPassedTargetCount": 0,
        "independentlyVerifiedTargetCount": 0,
        "productionDefinitionOfDoneCount": 0,
    }
    assert {target["state"] for target in result["targets"]} == {"BLOCKED_INPUT"}

    checked_in = parse_production_qualification_json(
        (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "chinadb-production-qualification-draft.json"
        ).read_bytes()
    )
    checked_in_result = evaluate_production_qualification(checked_in, now=NOW)
    assert qualification_result_is_currently_fail_closed(checked_in_result)


def test_vendor_execution_request_requires_verified_authorization() -> None:
    request, trust_store, _ = _complete_inputs()
    artifacts = {
        field: _role_digest("dm8", f"input:{field}") for field in REQUIRED_EXECUTION_INPUT_DIGESTS
    }
    with pytest.raises(ValueError, match="not READY_FOR_EXTERNAL_EXECUTION"):
        prepare_vendor_execution_request(
            request,
            trust_store=trust_store,
            target_id="dm8",
            input_artifact_digests=artifacts,
            now=NOW,
        )


def test_vendor_execution_request_is_exact_idempotent_and_secret_free() -> None:
    request, trust_store, keys = _complete_inputs()
    _authorize_target(request, trust_store, keys)
    artifacts = {
        field: _role_digest("dm8", f"input:{field}") for field in REQUIRED_EXECUTION_INPUT_DIGESTS
    }
    first = prepare_vendor_execution_request(
        request,
        trust_store=trust_store,
        target_id="dm8",
        input_artifact_digests=artifacts,
        now=NOW,
    )
    replay = prepare_vendor_execution_request(
        request,
        trust_store=trust_store,
        target_id="dm8",
        input_artifact_digests=artifacts,
        now=NOW,
    )

    assert first == replay
    assert first["kind"] == "CHINADB_VENDOR_EXECUTION_REQUEST"
    assert first["allowedOperations"] == list(REQUIRED_EXTERNAL_OPERATIONS)
    assert first["inputArtifactDigests"] == artifacts
    assert first["safety"] == {
        "productionData": False,
        "writeScope": "DISPOSABLE_ONLY",
        "secretTransport": "OPAQUE_REFERENCE_ONLY",
        "cleanupRequired": True,
        "unknownOutcomePolicy": "RECONCILE_BEFORE_RETRY",
    }
    assert first["externalExecution"] == "NOT_RUN"
    assert "password" not in json.dumps(first).casefold()


def test_complete_inputs_without_trust_do_not_manufacture_authority() -> None:
    request, _, _ = _complete_inputs()
    request["trustStoreDigest"] = None
    result = evaluate_production_qualification(request, now=NOW)
    assert result["summary"]["inputCompleteTargetCount"] == 13
    assert result["summary"]["productionDefinitionOfDoneCount"] == 0
    assert {target["state"] for target in result["targets"]} == {"BLOCKED_TRUST"}
    assert qualification_result_is_currently_fail_closed(result)


def test_trusted_inputs_without_receipts_stop_before_external_execution() -> None:
    request, trust_store, _ = _complete_inputs()
    result = evaluate_production_qualification(request, trust_store=trust_store, now=NOW)
    replay = evaluate_production_qualification(request, trust_store=trust_store, now=NOW)
    assert replay == result
    assert replay["resultDigest"] == result["resultDigest"]
    assert result["summary"]["inputCompleteTargetCount"] == 13
    assert result["summary"]["authorizationVerifiedTargetCount"] == 0
    assert {target["state"] for target in result["targets"]} == {"READY_FOR_AUTHORIZATION"}
    assert qualification_result_is_currently_fail_closed(result)


def test_all_13_targets_require_a_valid_four_envelope_chain() -> None:
    request, trust_store, keys = _complete_inputs()
    _sign_all_receipts(request, trust_store, keys)
    result = evaluate_production_qualification(request, trust_store=trust_store, now=NOW)
    assert result["summary"] == {
        "targetCount": 13,
        "inputCompleteTargetCount": 13,
        "authorizationVerifiedTargetCount": 13,
        "externalExecutionPassedTargetCount": 13,
        "independentlyVerifiedTargetCount": 13,
        "productionDefinitionOfDoneCount": 13,
    }
    assert result["externalExecution"] == "PASSED"
    assert result["independentVerification"] == "PASSED"
    assert result["certification"] == "CERTIFIED"
    assert result["targetSql"] is None
    assert result["productionDefinitionOfDoneCount"] == 13
    assert result["effects"] == {"externalCallsExecuted": []}
    assert {target["state"] for target in result["targets"]} == {"PRODUCTION_DEFINITION_OF_DONE"}


def test_capability_snapshot_drift_invalidates_the_signed_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, trust_store, keys = _complete_inputs()
    _sign_all_receipts(request, trust_store, keys)
    original_digest = target_qualification_input_digest(request, "dm8", now=NOW)
    capabilities = deepcopy(qualification_module.commercial_capabilities())
    replacement_snapshot = "sha256:" + "b" * 64
    capabilities["capabilitySnapshotDigest"] = replacement_snapshot
    monkeypatch.setattr(
        qualification_module,
        "commercial_capabilities",
        lambda: deepcopy(capabilities),
    )

    with pytest.raises(ValueError, match="capability snapshot is stale"):
        target_qualification_input_digest(request, "dm8", now=NOW)

    request["capabilitySnapshotDigest"] = replacement_snapshot
    replacement_digest = target_qualification_input_digest(request, "dm8", now=NOW)
    result = evaluate_production_qualification(request, trust_store=trust_store, now=NOW)

    assert replacement_digest != original_digest
    assert result["summary"]["authorizationVerifiedTargetCount"] == 0
    assert result["summary"]["productionDefinitionOfDoneCount"] == 0
    assert {target["state"] for target in result["targets"]} == {"BLOCKED_EVIDENCE"}
    assert all(
        target["blockers"][-1]["code"] == "AUTHORIZATION_RECEIPT_INVALID"
        for target in result["targets"]
    )


def test_tampered_execution_receipt_fails_one_target_without_hiding_partial_state() -> None:
    request, trust_store, keys = _complete_inputs()
    _sign_all_receipts(request, trust_store, keys)
    request["targets"][0]["receipts"]["execution"]["payload"]["criticalDifferences"] = 1
    result = evaluate_production_qualification(request, trust_store=trust_store, now=NOW)
    assert result["summary"]["productionDefinitionOfDoneCount"] == 12
    assert result["productionDefinitionOfDoneCount"] == 12
    assert result["externalExecution"] == "PARTIAL"
    assert result["certification"] == "PARTIALLY_CERTIFIED"
    assert result["targets"][0]["state"] == "BLOCKED_EVIDENCE"
    assert result["targets"][0]["externalExecution"] == "NOT_RUN"
    assert result["targets"][0]["blockers"][0]["code"] == "EXECUTION_RECEIPT_INVALID"


@pytest.mark.parametrize(
    ("digest_set", "missing_field"),
    (
        ("artifactDigests", "canonicalIrDigest"),
        ("evidenceDigests", "rollbackDigest"),
    ),
)
def test_execution_requires_every_named_evidence_digest(
    digest_set: str,
    missing_field: str,
) -> None:
    request, trust_store, keys = _complete_inputs()
    _sign_all_receipts(request, trust_store, keys)
    execution = request["targets"][0]["receipts"]["execution"]
    payload = deepcopy(execution["payload"])
    del payload[digest_set][missing_field]
    request["targets"][0]["receipts"]["execution"] = signed_envelope(
        key_id="executor-key",
        private_key=keys["executor-key"],
        payload=payload,
    )

    result = evaluate_production_qualification(request, trust_store=trust_store, now=NOW)

    assert result["summary"]["productionDefinitionOfDoneCount"] == 12
    assert result["targets"][0]["state"] == "BLOCKED_EVIDENCE"
    assert result["targets"][0]["blockers"][-1]["code"] == "EXECUTION_RECEIPT_INVALID"


@pytest.mark.parametrize("alias_scope", ("within-evidence", "across-sets"))
def test_execution_rejects_aliased_evidence_roles(alias_scope: str) -> None:
    request, trust_store, keys = _complete_inputs()
    _sign_all_receipts(request, trust_store, keys)
    execution = request["targets"][0]["receipts"]["execution"]
    payload = deepcopy(execution["payload"])
    if alias_scope == "within-evidence":
        payload["evidenceDigests"]["rollbackDigest"] = payload["evidenceDigests"]["cleanupDigest"]
    else:
        payload["evidenceDigests"]["rawEvidenceDigest"] = payload["artifactDigests"][
            "gateResultDigest"
        ]
    request["targets"][0]["receipts"]["execution"] = signed_envelope(
        key_id="executor-key",
        private_key=keys["executor-key"],
        payload=payload,
    )

    result = evaluate_production_qualification(request, trust_store=trust_store, now=NOW)

    assert result["summary"]["productionDefinitionOfDoneCount"] == 12
    assert result["targets"][0]["state"] == "BLOCKED_EVIDENCE"
    assert result["targets"][0]["blockers"][-1]["code"] == "EXECUTION_RECEIPT_INVALID"


@pytest.mark.parametrize(
    ("identity_field", "colliding_value"),
    (
        ("actorId", "verifier"),
        ("actorId", "executor"),
        ("actorId", "implementer"),
        ("organizationId", "independent-lab"),
        ("organizationId", "vendor-lab"),
        ("organizationId", "elmos-engineering"),
    ),
)
def test_certification_authority_must_be_separate_from_prior_roles(
    identity_field: str,
    colliding_value: str,
) -> None:
    request, trust_store, keys = _complete_inputs()
    _sign_all_receipts(request, trust_store, keys)
    certifier = next(key for key in trust_store["keys"] if key["keyId"] == "certifier-key")
    certifier[identity_field] = colliding_value
    request["trustStoreDigest"] = production_trust_store_digest(trust_store)

    result = evaluate_production_qualification(request, trust_store=trust_store, now=NOW)

    assert result["summary"]["productionDefinitionOfDoneCount"] == 0
    assert {target["state"] for target in result["targets"]} == {"BLOCKED_EVIDENCE"}
    assert all(
        target["blockers"][-1]["code"] == "CERTIFICATION_RECEIPT_INVALID"
        for target in result["targets"]
    )


def test_floating_tuple_and_non_independent_verifier_fail_closed() -> None:
    request, trust_store, _ = _complete_inputs()
    request["targets"][0]["exactTuple"]["productVersion"] = "latest"
    request["targets"][1]["independentVerifier"]["organizationId"] = "elmos-engineering"
    request["targets"][2]["exactTuple"]["productId"] = "dm8"
    result = evaluate_production_qualification(request, trust_store=trust_store, now=NOW)
    assert result["targets"][0]["state"] == "BLOCKED_INPUT"
    assert result["targets"][1]["state"] == "BLOCKED_INPUT"
    assert result["targets"][2]["state"] == "BLOCKED_INPUT"
    assert result["summary"]["inputCompleteTargetCount"] == 10
    assert result["summary"]["productionDefinitionOfDoneCount"] == 0


def test_strict_json_and_trust_binding_reject_ambiguous_or_untrusted_input() -> None:
    with pytest.raises(ValueError, match="duplicate field"):
        parse_production_qualification_json(b'{"scope":{},"scope":{}}')
    with pytest.raises(ValueError, match="inline secret"):
        parse_production_qualification_json(b'{"scope":{},"password":"bad"}')
    request, trust_store, _ = _complete_inputs()
    request["trustStoreDigest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="trust store digest binding mismatch"):
        evaluate_production_qualification(request, trust_store=trust_store, now=NOW)


def test_trust_store_parser_rejects_revoked_or_invalid_material_only_at_use() -> None:
    trust_store, _ = _trust_material()
    parsed = parse_production_trust_store_json(_canonical(trust_store))
    assert production_trust_store_digest(parsed) == production_trust_store_digest(trust_store)
    malformed = deepcopy(trust_store)
    malformed["keys"][0]["publicKey"] = "AAAA"
    with pytest.raises(ValueError, match="publicKey"):
        parse_production_trust_store_json(_canonical(malformed))


def test_cli_materializes_create_only_requirements_template_and_blocked_plan(
    tmp_path: Path,
) -> None:
    requirements_path = tmp_path / "requirements.json"
    template_path = tmp_path / "template.json"
    plan_path = tmp_path / "plan.json"
    assert main(["commercial-production-requirements", "--output", str(requirements_path)]) == 0
    assert (
        main(
            [
                "commercial-production-template",
                "--tenant-id",
                "tenant-1",
                "--project-id",
                "project-1",
                "--actor-id",
                "implementer",
                "--implementer-organization-id",
                "elmos-engineering",
                "--output",
                str(template_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "commercial-production-plan",
                str(template_path),
                "--output",
                str(plan_path),
            ]
        )
        == 3
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert qualification_result_is_currently_fail_closed(plan)
    assert main(["commercial-production-requirements", "--output", str(requirements_path)]) == 2

    complete_request, trust_store, _ = _complete_inputs()
    request_path = tmp_path / "complete-request.json"
    trust_path = tmp_path / "trust-store.json"
    trusted_plan_path = tmp_path / "trusted-plan.json"
    request_path.write_text(json.dumps(complete_request), encoding="utf-8")
    trust_path.write_text(json.dumps(trust_store), encoding="utf-8")
    assert (
        main(
            [
                "commercial-production-plan",
                str(request_path),
                "--trust-store",
                str(trust_path),
                "--trust-store-digest",
                production_trust_store_digest(trust_store),
                "--output",
                str(trusted_plan_path),
            ]
        )
        == 3
    )
    trusted_plan = json.loads(trusted_plan_path.read_text(encoding="utf-8"))
    assert trusted_plan["summary"]["inputCompleteTargetCount"] == 13
    assert trusted_plan["summary"]["productionDefinitionOfDoneCount"] == 0
    assert {target["state"] for target in trusted_plan["targets"]} == {"READY_FOR_AUTHORIZATION"}
