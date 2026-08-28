"""Fail-closed production qualification intake for the 13 ChinaDB targets.

This module does not execute a database, vendor tool, or migration.  It turns
the prerequisites and externally produced evidence for each exact target into
a digest-bound state machine.  A target reaches the production definition of
done only when four independently signed records form a valid chain:

* an exact disposable-environment authorization;
* a real target execution receipt;
* an independent verification receipt; and
* a certification decision.

Without an operator-pinned trust store and those records, all production
states remain ``NOT_RUN`` / ``NOT_CERTIFIED`` and target SQL is never returned.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .commercial import commercial_capabilities
from .skill_runtime import MAX_REQUEST_BYTES, parse_skill_request_json

SCHEMA_VERSION = "1.0"
PROTOCOL_VERSION = "1.1.0"
TRUST_DOMAIN = "elmos.chinadb.production-qualification.v1"
EXPECTED_TARGET_COUNT = 13

QualificationState = Literal[
    "BLOCKED_INPUT",
    "BLOCKED_TRUST",
    "BLOCKED_EVIDENCE",
    "READY_FOR_AUTHORIZATION",
    "READY_FOR_EXTERNAL_EXECUTION",
    "READY_FOR_INDEPENDENT_VERIFICATION",
    "READY_FOR_CERTIFICATION",
    "PRODUCTION_DEFINITION_OF_DONE",
]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+~-]{0,255}$")
_SCOPE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
_FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "accesstoken",
        "accesskey",
        "privatekey",
        "connectionstring",
        "dsn",
    }
)
_FLOATING = frozenset({"latest", "current", "unknown", "unspecified", "*", "x", "unset"})

REQUIRED_EXTERNAL_OPERATIONS = (
    "APPLY_SANDBOX",
    "BACKUP_RESTORE",
    "CAPABILITY_PROBE",
    "CAPTURE_PLAN",
    "CDC_RECONCILIATION",
    "CLEANUP",
    "EXECUTE_WORKLOAD",
    "INTROSPECT",
    "RENDER",
    "VERSION_PROBE",
)

_EXECUTION_CHECKS = (
    "capabilityProbe",
    "cleanup",
    "dataReconciliation",
    "performanceSecurityRollback",
    "schemaTypeQueryRoutineTransaction",
    "targetApplyIntrospection",
    "targetRender",
    "versionProbe",
)

REQUIRED_EXECUTION_ARTIFACT_DIGESTS = (
    "sourceSnapshotDigest",
    "sourceCatalogDigest",
    "sourceDataDigest",
    "sourceWorkloadDigest",
    "targetSnapshotDigest",
    "targetReleaseDigest",
    "canonicalIrDigest",
    "transformationDigest",
    "compatibilityRuntimeDigest",
    "runnerDigest",
    "toolchainDigest",
    "developmentCorpusDigest",
    "negativeCorpusDigest",
    "holdoutCorpusDigest",
    "representativeWorkloadDigest",
    "dataFixtureDigest",
    "queryPlanDigest",
    "targetSqlDigest",
    "acceptanceProfileDigest",
    "gateResultDigest",
)

REQUIRED_EXECUTION_EVIDENCE_DIGESTS = (
    "versionProbeDigest",
    "capabilityProbeDigest",
    "renderDigest",
    "targetApplyDigest",
    "introspectionDigest",
    "schemaTypeDigest",
    "queryRoutineDigest",
    "transactionDigest",
    "dataReconciliationDigest",
    "performanceDigest",
    "securityDigest",
    "backupRestoreDigest",
    "cdcDigest",
    "rollbackDigest",
    "cleanupDigest",
    "rawEvidenceDigest",
)

_ROLE_AUTHORIZER = "environment-authorizer"
_ROLE_EXECUTOR = "external-target-executor"
_ROLE_VERIFIER = "independent-verifier"
_ROLE_CERTIFIER = "certification-authority"
_TRUST_ROLES = frozenset(
    {_ROLE_AUTHORIZER, _ROLE_EXECUTOR, _ROLE_VERIFIER, _ROLE_CERTIFIER}
)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("qualification payload must be finite canonical JSON") from error


def _digest(value: Any) -> str:
    return "sha256:" + sha256(_canonical_bytes(value)).hexdigest()


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be a JSON object with string keys")
    return {str(key): child for key, child in value.items()}


def _exact_fields(value: Mapping[str, Any], fields: set[str], name: str) -> None:
    observed = set(value)
    if observed != fields:
        missing = sorted(fields - observed)
        extra = sorted(observed - fields)
        raise ValueError(f"{name} fields are not exact; missing={missing}, extra={extra}")


def _required_string(
    value: object,
    name: str,
    *,
    pattern: re.Pattern[str] = _SAFE_TOKEN,
    maximum: int = 256,
) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{name} must be a non-empty string of at most {maximum} characters")
    if pattern.fullmatch(value) is None:
        raise ValueError(f"{name} has an invalid format")
    return value


def _exact_token(value: object, name: str) -> str:
    token = _required_string(value, name)
    normalized = token.casefold()
    if (
        normalized in _FLOATING
        or normalized.endswith(".*")
        or normalized.endswith(".x")
        or "${" in token
        or "{{" in token
    ):
        raise ValueError(f"{name} must be exact and non-floating")
    return token


def _required_digest(value: object, name: str) -> str:
    return _required_string(value, name, pattern=_DIGEST, maximum=71)


def _digest_set(
    value: object,
    name: str,
    fields: tuple[str, ...],
) -> dict[str, str]:
    raw = _object(value, name)
    _exact_fields(raw, set(fields), name)
    result = {
        field: _required_digest(raw[field], f"{name}.{field}") for field in fields
    }
    if len(set(result.values())) != len(result):
        raise ValueError(f"{name} must use one role-specific digest per field")
    return result


def _timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{name} must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{name} must be an RFC3339 UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{name} must use UTC")
    return parsed


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("qualification evaluation time must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _walk_untrusted(value: object, *, key: str | None = None, depth: int = 0) -> None:
    if depth > 24:
        raise ValueError("qualification payload exceeds the maximum nesting depth")
    if key is not None:
        normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
        if normalized in _FORBIDDEN_SECRET_KEYS:
            raise ValueError(
                f"inline secret field {key!r} is prohibited; use an opaque credentialRef"
            )
    if isinstance(value, dict):
        if len(value) > 2_000:
            raise ValueError("qualification object exceeds the item limit")
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                raise ValueError("qualification object keys must be strings")
            _walk_untrusted(child, key=child_key, depth=depth + 1)
    elif isinstance(value, list):
        if len(value) > 2_000:
            raise ValueError("qualification array exceeds the item limit")
        for child in value:
            _walk_untrusted(child, depth=depth + 1)
    elif value is not None and not isinstance(value, str | int | float | bool):
        raise ValueError("qualification payload contains a non-JSON value")


def parse_production_qualification_json(
    payload: bytes,
    *,
    maximum: int = MAX_REQUEST_BYTES,
) -> dict[str, Any]:
    value = parse_skill_request_json(payload, maximum=maximum)
    _walk_untrusted(value)
    return value


def _scope(value: object) -> dict[str, str]:
    raw = _object(value, "scope")
    expected = {"tenantId", "projectId", "actorId"}
    _exact_fields(raw, expected, "scope")
    return {
        field: _required_string(raw[field], f"scope.{field}", pattern=_SCOPE_TOKEN, maximum=128)
        for field in ("tenantId", "projectId", "actorId")
    }


def _catalog_targets() -> tuple[dict[str, str], ...]:
    capabilities = commercial_capabilities()
    targets: list[dict[str, str]] = []
    for raw_target in capabilities["targets"]:
        target = _object(raw_target, "commercial target")
        targets.append(
            {
                "targetId": str(target["id"]),
                "label": str(target["label"]),
                "adapterId": str(target["adapterId"]),
            }
        )
    if len(targets) != EXPECTED_TARGET_COUNT:
        raise RuntimeError("ChinaDB production qualification requires exactly 13 targets")
    return tuple(targets)


def production_qualification_requirements() -> dict[str, Any]:
    capabilities = commercial_capabilities()
    targets = [
        {
            **target,
            "requiredOperations": list(REQUIRED_EXTERNAL_OPERATIONS),
            "requiredEvidenceChain": [
                "environment-authorization",
                "external-target-execution",
                "independent-verification",
                "certification-decision",
            ],
            "requiredArtifactDigests": list(REQUIRED_EXECUTION_ARTIFACT_DIGESTS),
            "requiredEvidenceDigests": list(REQUIRED_EXECUTION_EVIDENCE_DIGESTS),
            "currentState": "BLOCKED_EXTERNAL_INPUT",
        }
        for target in _catalog_targets()
    ]
    result: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "protocolVersion": PROTOCOL_VERSION,
        "package": "chinadb-commercial-migration-skills",
        "capabilitySnapshotDigest": capabilities["capabilitySnapshotDigest"],
        "targetCount": len(targets),
        "targets": targets,
        "trust": {
            "domain": TRUST_DOMAIN,
            "algorithm": "ed25519",
            "requiredRoles": sorted(_TRUST_ROLES),
            "operatorPinnedTrustStoreRequired": True,
        },
        "productionBoundaries": {
            "externalExecution": "NOT_RUN",
            "independentVerification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "targetSql": None,
            "productionDefinitionOfDoneCount": 0,
        },
    }
    result["requirementsDigest"] = _digest(result)
    return result


def production_qualification_draft(
    *,
    tenant_id: str,
    project_id: str,
    actor_id: str,
    implementer_organization_id: str,
) -> dict[str, Any]:
    scope = _scope(
        {"tenantId": tenant_id, "projectId": project_id, "actorId": actor_id}
    )
    implementer_org = _required_string(
        implementer_organization_id,
        "implementer.organizationId",
        pattern=_SCOPE_TOKEN,
        maximum=128,
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "scope": scope,
        "capabilitySnapshotDigest": commercial_capabilities()["capabilitySnapshotDigest"],
        "trustStoreDigest": None,
        "implementer": {"actorId": actor_id, "organizationId": implementer_org},
        "targets": [
            {
                "targetId": target["targetId"],
                "exactTuple": None,
                "disposableEnvironment": None,
                "vendorTools": [],
                "independentVerifier": None,
                "receipts": {
                    "authorization": None,
                    "execution": None,
                    "independentVerification": None,
                    "certification": None,
                },
            }
            for target in _catalog_targets()
        ],
    }


def _decode_public_key(value: object, name: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{name} must be a bounded base64 string")
    encoded = value
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"{name} must be canonical base64") from error
    if len(decoded) != 32:
        raise ValueError(f"{name} must contain one raw Ed25519 public key")
    if base64.b64encode(decoded).decode("ascii") != encoded:
        raise ValueError(f"{name} must use canonical base64")
    return decoded


def parse_production_trust_store_json(payload: bytes) -> dict[str, Any]:
    value = parse_skill_request_json(payload, maximum=MAX_REQUEST_BYTES)
    _walk_untrusted(value)
    _exact_fields(value, {"schemaVersion", "trustDomain", "keys"}, "trust store")
    if value.get("schemaVersion") != SCHEMA_VERSION or value.get("trustDomain") != TRUST_DOMAIN:
        raise ValueError("trust store identity is invalid")
    raw_keys = value.get("keys")
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ValueError("trust store keys must be a non-empty array")
    keys: list[dict[str, Any]] = []
    key_ids: set[str] = set()
    for index, raw_key in enumerate(raw_keys):
        key = _object(raw_key, f"trust store keys[{index}]")
        _exact_fields(
            key,
            {
                "keyId",
                "role",
                "actorId",
                "organizationId",
                "publicKey",
                "notBefore",
                "notAfter",
                "revoked",
            },
            f"trust store keys[{index}]",
        )
        key_id = _required_string(key["keyId"], f"trust store keys[{index}].keyId")
        if key_id in key_ids:
            raise ValueError(f"duplicate trust key id: {key_id}")
        key_ids.add(key_id)
        role = _required_string(key["role"], f"trust store keys[{index}].role")
        if role not in _TRUST_ROLES:
            raise ValueError(f"trust store keys[{index}].role is unsupported")
        not_before = _timestamp(key["notBefore"], f"trust store keys[{index}].notBefore")
        not_after = _timestamp(key["notAfter"], f"trust store keys[{index}].notAfter")
        if not_before >= not_after:
            raise ValueError(f"trust store keys[{index}] validity window is invalid")
        public_key = _decode_public_key(
            key["publicKey"], f"trust store keys[{index}].publicKey"
        )
        if not isinstance(key["revoked"], bool):
            raise ValueError(f"trust store keys[{index}].revoked must be a Boolean")
        keys.append(
            {
                "keyId": key_id,
                "role": role,
                "actorId": _required_string(
                    key["actorId"],
                    f"trust store keys[{index}].actorId",
                    pattern=_SCOPE_TOKEN,
                    maximum=128,
                ),
                "organizationId": _required_string(
                    key["organizationId"],
                    f"trust store keys[{index}].organizationId",
                    pattern=_SCOPE_TOKEN,
                    maximum=128,
                ),
                "publicKey": base64.b64encode(public_key).decode("ascii"),
                "notBefore": _utc_text(not_before),
                "notAfter": _utc_text(not_after),
                "revoked": key["revoked"],
            }
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "trustDomain": TRUST_DOMAIN,
        "keys": keys,
    }


def production_trust_store_digest(trust_store: Mapping[str, Any]) -> str:
    return _digest(_object(trust_store, "trust store"))


def _blocker(code: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": "ERROR", "message": message}


def _validate_exact_tuple(value: object, name: str, *, target_id: str) -> dict[str, Any]:
    raw = _object(value, name)
    fields = {
        "productId",
        "productVersion",
        "edition",
        "compatibilityMode",
        "deploymentTopology",
        "provider",
        "serviceTier",
        "region",
        "driver",
        "charset",
        "collation",
        "timeZone",
        "timeZoneDataVersion",
        "sqlMode",
        "extensions",
        "runtimeArtifactDigest",
    }
    _exact_fields(raw, fields, name)
    driver = _object(raw["driver"], f"{name}.driver")
    _exact_fields(driver, {"name", "version", "artifactDigest"}, f"{name}.driver")
    extensions_raw = raw["extensions"]
    if not isinstance(extensions_raw, list) or len(extensions_raw) > 128:
        raise ValueError(f"{name}.extensions must be a bounded array")
    extensions: list[dict[str, str]] = []
    names: set[str] = set()
    for index, raw_extension in enumerate(extensions_raw):
        extension = _object(raw_extension, f"{name}.extensions[{index}]")
        _exact_fields(extension, {"name", "version"}, f"{name}.extensions[{index}]")
        extension_name = _exact_token(extension["name"], f"{name}.extensions[{index}].name")
        if extension_name in names:
            raise ValueError(f"{name}.extensions contains duplicate {extension_name}")
        names.add(extension_name)
        extensions.append(
            {
                "name": extension_name,
                "version": _exact_token(
                    extension["version"], f"{name}.extensions[{index}].version"
                ),
            }
        )
    product_id = _exact_token(raw["productId"], f"{name}.productId")
    if product_id != target_id:
        raise ValueError(f"{name}.productId must match handler-bound target {target_id}")
    return {
        "productId": product_id,
        "productVersion": _exact_token(raw["productVersion"], f"{name}.productVersion"),
        "edition": _exact_token(raw["edition"], f"{name}.edition"),
        "compatibilityMode": _exact_token(
            raw["compatibilityMode"], f"{name}.compatibilityMode"
        ),
        "deploymentTopology": _exact_token(
            raw["deploymentTopology"], f"{name}.deploymentTopology"
        ),
        "provider": _exact_token(raw["provider"], f"{name}.provider"),
        "serviceTier": _exact_token(raw["serviceTier"], f"{name}.serviceTier"),
        "region": _exact_token(raw["region"], f"{name}.region"),
        "driver": {
            "name": _exact_token(driver["name"], f"{name}.driver.name"),
            "version": _exact_token(driver["version"], f"{name}.driver.version"),
            "artifactDigest": _required_digest(
                driver["artifactDigest"], f"{name}.driver.artifactDigest"
            ),
        },
        "charset": _exact_token(raw["charset"], f"{name}.charset"),
        "collation": _exact_token(raw["collation"], f"{name}.collation"),
        "timeZone": _exact_token(raw["timeZone"], f"{name}.timeZone"),
        "timeZoneDataVersion": _exact_token(
            raw["timeZoneDataVersion"], f"{name}.timeZoneDataVersion"
        ),
        "sqlMode": _exact_token(raw["sqlMode"], f"{name}.sqlMode"),
        "extensions": extensions,
        "runtimeArtifactDigest": _required_digest(
            raw["runtimeArtifactDigest"], f"{name}.runtimeArtifactDigest"
        ),
    }


def _validate_environment(value: object, name: str, now: datetime) -> dict[str, Any]:
    raw = _object(value, name)
    fields = {
        "environmentId",
        "kind",
        "endpointRef",
        "credentialRef",
        "providerResourceRef",
        "dataProfile",
        "productionData",
        "writeScope",
        "expiresAt",
        "cleanupDeadline",
    }
    _exact_fields(raw, fields, name)
    kind = _exact_token(raw["kind"], f"{name}.kind")
    if kind not in {"DISPOSABLE_INSTANCE", "DISPOSABLE_SCHEMA", "APPROVED_LICENSED_SANDBOX"}:
        raise ValueError(f"{name}.kind is not an approved disposable environment kind")
    data_profile = _exact_token(raw["dataProfile"], f"{name}.dataProfile")
    if data_profile not in {"SYNTHETIC", "MASKED", "APPROVED_SNAPSHOT"}:
        raise ValueError(f"{name}.dataProfile is invalid")
    if raw["productionData"] is not False or raw["writeScope"] != "DISPOSABLE_ONLY":
        raise ValueError(f"{name} must prohibit production data and production writes")
    expires_at = _timestamp(raw["expiresAt"], f"{name}.expiresAt")
    cleanup_deadline = _timestamp(raw["cleanupDeadline"], f"{name}.cleanupDeadline")
    if expires_at <= now or cleanup_deadline < expires_at:
        raise ValueError(f"{name} is expired or has an invalid cleanup window")
    return {
        "environmentId": _exact_token(raw["environmentId"], f"{name}.environmentId"),
        "kind": kind,
        "endpointRef": _exact_token(raw["endpointRef"], f"{name}.endpointRef"),
        "credentialRef": _exact_token(raw["credentialRef"], f"{name}.credentialRef"),
        "providerResourceRef": _exact_token(
            raw["providerResourceRef"], f"{name}.providerResourceRef"
        ),
        "dataProfile": data_profile,
        "productionData": False,
        "writeScope": "DISPOSABLE_ONLY",
        "expiresAt": _utc_text(expires_at),
        "cleanupDeadline": _utc_text(cleanup_deadline),
    }


def _validate_vendor_tools(
    value: object,
    name: str,
    *,
    adapter_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 32:
        raise ValueError(f"{name} must be a non-empty bounded array")
    tools: list[dict[str, Any]] = []
    tool_ids: set[str] = set()
    covered: set[str] = set()
    for index, raw_tool in enumerate(value):
        tool = _object(raw_tool, f"{name}[{index}]")
        _exact_fields(
            tool,
            {
                "toolId",
                "version",
                "artifactDigest",
                "licenseRef",
                "adapterId",
                "operations",
            },
            f"{name}[{index}]",
        )
        tool_id = _exact_token(tool["toolId"], f"{name}[{index}].toolId")
        if tool_id in tool_ids:
            raise ValueError(f"{name} contains duplicate tool id {tool_id}")
        tool_ids.add(tool_id)
        if tool["adapterId"] != adapter_id:
            raise ValueError(f"{name}[{index}].adapterId must match {adapter_id}")
        operations_raw = tool["operations"]
        if not isinstance(operations_raw, list) or not operations_raw:
            raise ValueError(f"{name}[{index}].operations must be non-empty")
        operations = sorted(
            {_exact_token(item, f"{name}[{index}].operations") for item in operations_raw}
        )
        if len(operations) != len(operations_raw) or not set(operations) <= set(
            REQUIRED_EXTERNAL_OPERATIONS
        ):
            raise ValueError(f"{name}[{index}].operations contains duplicates or unknown values")
        covered.update(operations)
        tools.append(
            {
                "toolId": tool_id,
                "version": _exact_token(tool["version"], f"{name}[{index}].version"),
                "artifactDigest": _required_digest(
                    tool["artifactDigest"], f"{name}[{index}].artifactDigest"
                ),
                "licenseRef": _exact_token(
                    tool["licenseRef"], f"{name}[{index}].licenseRef"
                ),
                "adapterId": adapter_id,
                "operations": operations,
            }
        )
    missing = set(REQUIRED_EXTERNAL_OPERATIONS) - covered
    if missing:
        raise ValueError(f"{name} does not cover required operations: {sorted(missing)}")
    return sorted(tools, key=lambda item: str(item["toolId"]))


def _validate_verifier(value: object, name: str, implementer: Mapping[str, str]) -> dict[str, str]:
    raw = _object(value, name)
    _exact_fields(
        raw,
        {"verifierId", "actorId", "organizationId", "engagementRef"},
        name,
    )
    result = {
        field: _required_string(raw[field], f"{name}.{field}", pattern=_SCOPE_TOKEN, maximum=128)
        for field in ("verifierId", "actorId", "organizationId", "engagementRef")
    }
    if (
        result["actorId"] == implementer["actorId"]
        or result["organizationId"] == implementer["organizationId"]
    ):
        raise ValueError(f"{name} must be independent from the implementer actor and organization")
    return result


def _trust_keys(trust_store: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if trust_store is None:
        return {}
    parsed = parse_production_trust_store_json(_canonical_bytes(trust_store))
    return {str(item["keyId"]): dict(item) for item in parsed["keys"]}


def _decode_signature(value: object, name: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{name} must be a bounded base64 string")
    encoded = value
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"{name} must be canonical base64") from error
    if len(decoded) != 64 or base64.b64encode(decoded).decode("ascii") != encoded:
        raise ValueError(f"{name} must contain one canonical Ed25519 signature")
    return decoded


def _verify_envelope(
    value: object,
    *,
    name: str,
    role: str,
    kind: str,
    trust_keys: Mapping[str, Mapping[str, Any]],
    signed_at_field: str,
) -> tuple[dict[str, Any], dict[str, str], str]:
    envelope = _object(value, name)
    _exact_fields(envelope, {"algorithm", "keyId", "payload", "signature"}, name)
    if envelope["algorithm"] != "ed25519":
        raise ValueError(f"{name}.algorithm must be ed25519")
    key_id = _required_string(envelope["keyId"], f"{name}.keyId")
    key = trust_keys.get(key_id)
    if key is None:
        raise ValueError(f"{name} key is not present in the operator-pinned trust store")
    if key["role"] != role or bool(key["revoked"]):
        raise ValueError(f"{name} key role is invalid or revoked")
    payload = _object(envelope["payload"], f"{name}.payload")
    if payload.get("schemaVersion") != SCHEMA_VERSION or payload.get("kind") != kind:
        raise ValueError(f"{name} payload identity is invalid")
    signed_at = _timestamp(payload.get(signed_at_field), f"{name}.payload.{signed_at_field}")
    if not (
        _timestamp(key["notBefore"], f"{name}.key.notBefore")
        <= signed_at
        <= _timestamp(key["notAfter"], f"{name}.key.notAfter")
    ):
        raise ValueError(f"{name} was signed outside the trusted key validity window")
    public_key = _decode_public_key(key["publicKey"], f"{name}.key.publicKey")
    signature = _decode_signature(envelope["signature"], f"{name}.signature")
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature,
            _canonical_bytes(payload),
        )
    except InvalidSignature as error:
        raise ValueError(f"{name} signature verification failed") from error
    identity = {
        "keyId": key_id,
        "actorId": str(key["actorId"]),
        "organizationId": str(key["organizationId"]),
    }
    return payload, identity, _digest(envelope)


def _target_input(
    target: Mapping[str, Any],
    *,
    index: int,
    catalog_target: Mapping[str, str],
    implementer: Mapping[str, str],
    scope_digest: str,
    capability_snapshot_digest: str,
    now: datetime,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    blockers: list[dict[str, str]] = []
    exact_tuple: dict[str, Any] | None = None
    environment: dict[str, Any] | None = None
    tools: list[dict[str, Any]] = []
    verifier: dict[str, str] | None = None
    validators = (
        (
            "exactTuple",
            lambda value: _validate_exact_tuple(
                value,
                f"targets[{index}].exactTuple",
                target_id=catalog_target["targetId"],
            ),
            "EXACT_TARGET_TUPLE_REQUIRED",
        ),
        (
            "disposableEnvironment",
            lambda value: _validate_environment(
                value, f"targets[{index}].disposableEnvironment", now
            ),
            "DISPOSABLE_ENVIRONMENT_REQUIRED",
        ),
        (
            "vendorTools",
            lambda value: _validate_vendor_tools(
                value,
                f"targets[{index}].vendorTools",
                adapter_id=catalog_target["adapterId"],
            ),
            "VENDOR_TOOLS_REQUIRED",
        ),
        (
            "independentVerifier",
            lambda value: _validate_verifier(
                value,
                f"targets[{index}].independentVerifier",
                implementer,
            ),
            "INDEPENDENT_VERIFIER_REQUIRED",
        ),
    )
    parsed: dict[str, Any] = {}
    for field, validator, code in validators:
        value = target.get(field)
        if value is None or value == []:
            blockers.append(_blocker(code, f"{catalog_target['targetId']} is missing {field}."))
            continue
        try:
            parsed[field] = validator(value)
        except ValueError as error:
            blockers.append(_blocker(code, str(error)))
    exact_tuple = parsed.get("exactTuple")
    environment = parsed.get("disposableEnvironment")
    tools = parsed.get("vendorTools", [])
    verifier = parsed.get("independentVerifier")
    if blockers:
        return None, blockers
    if not isinstance(exact_tuple, dict) or not isinstance(environment, dict) or not isinstance(
        verifier, dict
    ):
        raise RuntimeError("qualification target input normalization failed")
    tool_digests = [_digest(tool) for tool in tools]
    normalized = {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilitySnapshotDigest": capability_snapshot_digest,
        "targetId": catalog_target["targetId"],
        "adapterId": catalog_target["adapterId"],
        "scopeDigest": scope_digest,
        "exactTuple": exact_tuple,
        "exactTupleDigest": _digest(exact_tuple),
        "disposableEnvironment": environment,
        "environmentDigest": _digest(environment),
        "vendorTools": tools,
        "vendorToolDigests": tool_digests,
        "independentVerifier": verifier,
    }
    normalized["qualificationInputDigest"] = _digest(normalized)
    return normalized, blockers


def _receipt_object(target: Mapping[str, Any], index: int) -> dict[str, Any]:
    raw = target.get("receipts")
    if raw is None:
        return {
            "authorization": None,
            "execution": None,
            "independentVerification": None,
            "certification": None,
        }
    receipts = _object(raw, f"targets[{index}].receipts")
    _exact_fields(
        receipts,
        {"authorization", "execution", "independentVerification", "certification"},
        f"targets[{index}].receipts",
    )
    return receipts


def _authorization(
    value: object,
    *,
    target_input: Mapping[str, Any],
    implementer: Mapping[str, str],
    trust_keys: Mapping[str, Mapping[str, Any]],
    now: datetime,
) -> tuple[dict[str, Any], dict[str, str], str]:
    payload, identity, envelope_digest = _verify_envelope(
        value,
        name="authorization receipt",
        role=_ROLE_AUTHORIZER,
        kind="CHINADB_TARGET_EXECUTION_AUTHORIZATION",
        trust_keys=trust_keys,
        signed_at_field="issuedAt",
    )
    fields = {
        "schemaVersion",
        "kind",
        "recordId",
        "scopeDigest",
        "targetId",
        "qualificationInputDigest",
        "environmentId",
        "implementerActorId",
        "implementerOrganizationId",
        "allowedOperations",
        "issuedAt",
        "expiresAt",
    }
    _exact_fields(payload, fields, "authorization receipt payload")
    if (
        identity["actorId"] == implementer["actorId"]
        or identity["organizationId"] == implementer["organizationId"]
    ):
        raise ValueError("environment authorizer must be separated from the implementer")
    expected = {
        "scopeDigest": target_input["scopeDigest"],
        "targetId": target_input["targetId"],
        "qualificationInputDigest": target_input["qualificationInputDigest"],
        "environmentId": target_input["disposableEnvironment"]["environmentId"],
        "implementerActorId": implementer["actorId"],
        "implementerOrganizationId": implementer["organizationId"],
    }
    for field, expected_value in expected.items():
        if payload[field] != expected_value:
            raise ValueError(f"authorization receipt payload {field} binding mismatch")
    operations = payload["allowedOperations"]
    if not isinstance(operations, list) or operations != list(REQUIRED_EXTERNAL_OPERATIONS):
        raise ValueError("authorization receipt operations are not the exact required set")
    issued_at = _timestamp(payload["issuedAt"], "authorization receipt payload.issuedAt")
    expires_at = _timestamp(payload["expiresAt"], "authorization receipt payload.expiresAt")
    environment_expiry = _timestamp(
        target_input["disposableEnvironment"]["expiresAt"],
        "disposableEnvironment.expiresAt",
    )
    if issued_at > now or expires_at <= now or expires_at > environment_expiry:
        raise ValueError("authorization receipt is not currently valid for the environment")
    _required_string(payload["recordId"], "authorization receipt payload.recordId")
    return payload, identity, envelope_digest


def _execution(
    value: object,
    *,
    target_input: Mapping[str, Any],
    authorization: Mapping[str, Any],
    authorization_digest: str,
    trust_keys: Mapping[str, Mapping[str, Any]],
    now: datetime,
) -> tuple[dict[str, Any], dict[str, str], str]:
    payload, identity, envelope_digest = _verify_envelope(
        value,
        name="execution receipt",
        role=_ROLE_EXECUTOR,
        kind="CHINADB_TARGET_EXECUTION_RECEIPT",
        trust_keys=trust_keys,
        signed_at_field="executedAt",
    )
    fields = {
        "schemaVersion",
        "kind",
        "recordId",
        "authorizationRecordId",
        "authorizationEnvelopeDigest",
        "scopeDigest",
        "targetId",
        "qualificationInputDigest",
        "environmentId",
        "exactTupleDigest",
        "vendorToolDigests",
        "artifactDigests",
        "evidenceDigests",
        "executedAt",
        "checks",
        "criticalUnknowns",
        "criticalDifferences",
        "testIntegrityViolations",
    }
    _exact_fields(payload, fields, "execution receipt payload")
    expected = {
        "authorizationRecordId": authorization["recordId"],
        "authorizationEnvelopeDigest": authorization_digest,
        "scopeDigest": target_input["scopeDigest"],
        "targetId": target_input["targetId"],
        "qualificationInputDigest": target_input["qualificationInputDigest"],
        "environmentId": target_input["disposableEnvironment"]["environmentId"],
        "exactTupleDigest": target_input["exactTupleDigest"],
        "vendorToolDigests": target_input["vendorToolDigests"],
    }
    for field, expected_value in expected.items():
        if payload[field] != expected_value:
            raise ValueError(f"execution receipt payload {field} binding mismatch")
    artifact_digests = _digest_set(
        payload["artifactDigests"],
        "execution receipt payload.artifactDigests",
        REQUIRED_EXECUTION_ARTIFACT_DIGESTS,
    )
    evidence_digests = _digest_set(
        payload["evidenceDigests"],
        "execution receipt payload.evidenceDigests",
        REQUIRED_EXECUTION_EVIDENCE_DIGESTS,
    )
    if set(artifact_digests.values()) & set(evidence_digests.values()):
        raise ValueError("execution receipt artifact and evidence digests must not alias")
    payload["artifactDigests"] = artifact_digests
    payload["evidenceDigests"] = evidence_digests
    checks = _object(payload["checks"], "execution receipt payload.checks")
    _exact_fields(checks, set(_EXECUTION_CHECKS), "execution receipt payload.checks")
    if any(checks[field] != "PASSED" for field in _EXECUTION_CHECKS):
        raise ValueError("execution receipt contains a non-passing required check")
    for counter in ("criticalUnknowns", "criticalDifferences", "testIntegrityViolations"):
        if not isinstance(payload[counter], int) or isinstance(payload[counter], bool):
            raise ValueError(f"execution receipt payload.{counter} must be an integer")
        if payload[counter] != 0:
            raise ValueError(f"execution receipt payload.{counter} must be zero")
    executed_at = _timestamp(payload["executedAt"], "execution receipt payload.executedAt")
    if not (
        _timestamp(authorization["issuedAt"], "authorization.issuedAt")
        <= executed_at
        <= _timestamp(authorization["expiresAt"], "authorization.expiresAt")
        and executed_at <= now
    ):
        raise ValueError("execution receipt time is outside authorization or evaluation time")
    _required_string(payload["recordId"], "execution receipt payload.recordId")
    return payload, identity, envelope_digest


def _independent_verification(
    value: object,
    *,
    target_input: Mapping[str, Any],
    execution: Mapping[str, Any],
    execution_digest: str,
    executor_identity: Mapping[str, str],
    implementer: Mapping[str, str],
    trust_keys: Mapping[str, Mapping[str, Any]],
    now: datetime,
) -> tuple[dict[str, Any], dict[str, str], str]:
    payload, identity, envelope_digest = _verify_envelope(
        value,
        name="independent verification receipt",
        role=_ROLE_VERIFIER,
        kind="CHINADB_INDEPENDENT_VERIFICATION_RECEIPT",
        trust_keys=trust_keys,
        signed_at_field="verifiedAt",
    )
    fields = {
        "schemaVersion",
        "kind",
        "recordId",
        "scopeDigest",
        "targetId",
        "qualificationInputDigest",
        "executionRecordId",
        "executionEnvelopeDigest",
        "rawEvidenceDigest",
        "holdoutCorpusDigest",
        "representativeWorkloadDigest",
        "decision",
        "criticalFindings",
        "verifiedAt",
    }
    _exact_fields(payload, fields, "independent verification receipt payload")
    verifier = target_input["independentVerifier"]
    if (
        identity["actorId"] != verifier["actorId"]
        or identity["organizationId"] != verifier["organizationId"]
        or identity["actorId"] in {executor_identity["actorId"], implementer["actorId"]}
        or identity["organizationId"]
        in {executor_identity["organizationId"], implementer["organizationId"]}
    ):
        raise ValueError("independent verifier identity or organization is not independent")
    critical_findings = payload["criticalFindings"]
    if not isinstance(critical_findings, int) or isinstance(critical_findings, bool):
        raise ValueError(
            "independent verification receipt payload.criticalFindings must be an integer"
        )
    expected = {
        "scopeDigest": target_input["scopeDigest"],
        "targetId": target_input["targetId"],
        "qualificationInputDigest": target_input["qualificationInputDigest"],
        "executionRecordId": execution["recordId"],
        "executionEnvelopeDigest": execution_digest,
        "rawEvidenceDigest": execution["evidenceDigests"]["rawEvidenceDigest"],
        "holdoutCorpusDigest": execution["artifactDigests"]["holdoutCorpusDigest"],
        "representativeWorkloadDigest": execution["artifactDigests"][
            "representativeWorkloadDigest"
        ],
        "decision": "PASSED",
        "criticalFindings": 0,
    }
    for field, expected_value in expected.items():
        if payload[field] != expected_value:
            raise ValueError(
                f"independent verification receipt payload {field} binding mismatch"
            )
    verified_at = _timestamp(
        payload["verifiedAt"], "independent verification receipt payload.verifiedAt"
    )
    if (
        verified_at < _timestamp(execution["executedAt"], "execution.executedAt")
        or verified_at > now
    ):
        raise ValueError("independent verification receipt time is invalid")
    _required_string(payload["recordId"], "independent verification receipt payload.recordId")
    return payload, identity, envelope_digest


def _certification(
    value: object,
    *,
    target_input: Mapping[str, Any],
    verification: Mapping[str, Any],
    verification_digest: str,
    verifier_identity: Mapping[str, str],
    executor_identity: Mapping[str, str],
    implementer: Mapping[str, str],
    trust_keys: Mapping[str, Mapping[str, Any]],
    now: datetime,
) -> tuple[dict[str, Any], dict[str, str], str]:
    payload, identity, envelope_digest = _verify_envelope(
        value,
        name="certification receipt",
        role=_ROLE_CERTIFIER,
        kind="CHINADB_PRODUCTION_CERTIFICATION_RECEIPT",
        trust_keys=trust_keys,
        signed_at_field="certifiedAt",
    )
    fields = {
        "schemaVersion",
        "kind",
        "recordId",
        "scopeDigest",
        "targetId",
        "qualificationInputDigest",
        "verificationRecordId",
        "verificationEnvelopeDigest",
        "decision",
        "certifiedAt",
        "expiresAt",
    }
    _exact_fields(payload, fields, "certification receipt payload")
    if (
        identity["actorId"]
        in {
            verifier_identity["actorId"],
            executor_identity["actorId"],
            implementer["actorId"],
        }
        or identity["organizationId"]
        in {
            verifier_identity["organizationId"],
            executor_identity["organizationId"],
            implementer["organizationId"],
        }
    ):
        raise ValueError("certification authority is not sufficiently separated")
    expected = {
        "scopeDigest": target_input["scopeDigest"],
        "targetId": target_input["targetId"],
        "qualificationInputDigest": target_input["qualificationInputDigest"],
        "verificationRecordId": verification["recordId"],
        "verificationEnvelopeDigest": verification_digest,
        "decision": "CERTIFIED",
    }
    for field, expected_value in expected.items():
        if payload[field] != expected_value:
            raise ValueError(f"certification receipt payload {field} binding mismatch")
    certified_at = _timestamp(payload["certifiedAt"], "certification receipt payload.certifiedAt")
    expires_at = _timestamp(payload["expiresAt"], "certification receipt payload.expiresAt")
    if (
        certified_at
        < _timestamp(verification["verifiedAt"], "independent verification.verifiedAt")
        or certified_at > now
        or expires_at <= now
    ):
        raise ValueError("certification receipt validity window is invalid")
    _required_string(payload["recordId"], "certification receipt payload.recordId")
    return payload, identity, envelope_digest


def _target_result(
    target: Mapping[str, Any],
    *,
    index: int,
    catalog_target: Mapping[str, str],
    scope_digest: str,
    capability_snapshot_digest: str,
    implementer: Mapping[str, str],
    trust_keys: Mapping[str, Mapping[str, Any]],
    trust_ready: bool,
    now: datetime,
) -> dict[str, Any]:
    target_input, blockers = _target_input(
        target,
        index=index,
        catalog_target=catalog_target,
        implementer=implementer,
        scope_digest=scope_digest,
        capability_snapshot_digest=capability_snapshot_digest,
        now=now,
    )
    result: dict[str, Any] = {
        "targetId": catalog_target["targetId"],
        "label": catalog_target["label"],
        "adapterId": catalog_target["adapterId"],
        "state": "BLOCKED_INPUT",
        "qualificationInputDigest": None,
        "exactTupleDigest": None,
        "environmentDigest": None,
        "vendorToolDigests": [],
        "authorization": "NOT_RUN",
        "externalExecution": "NOT_RUN",
        "independentVerification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "targetSql": None,
        "evidenceEnvelopeDigests": [],
        "blockers": blockers,
    }
    if target_input is None:
        return result
    result.update(
        {
            "state": "READY_FOR_AUTHORIZATION",
            "qualificationInputDigest": target_input["qualificationInputDigest"],
            "exactTupleDigest": target_input["exactTupleDigest"],
            "environmentDigest": target_input["environmentDigest"],
            "vendorToolDigests": target_input["vendorToolDigests"],
        }
    )
    if not trust_ready:
        result["state"] = "BLOCKED_TRUST"
        result["blockers"].append(
            _blocker(
                "OPERATOR_PINNED_TRUST_STORE_REQUIRED",
                "A digest-matched operator-pinned Ed25519 trust store is required.",
            )
        )
        return result
    receipts = _receipt_object(target, index)
    authorization_value = receipts["authorization"]
    if authorization_value is None:
        result["blockers"].append(
            _blocker(
                "SIGNED_ENVIRONMENT_AUTHORIZATION_REQUIRED",
                "No trusted disposable-environment authorization receipt was supplied.",
            )
        )
        return result
    try:
        authorization, _, authorization_digest = _authorization(
            authorization_value,
            target_input=target_input,
            implementer=implementer,
            trust_keys=trust_keys,
            now=now,
        )
        result["authorization"] = "VERIFIED"
        result["state"] = "READY_FOR_EXTERNAL_EXECUTION"
        result["evidenceEnvelopeDigests"].append(authorization_digest)
    except ValueError as error:
        result["state"] = "BLOCKED_EVIDENCE"
        result["blockers"].append(_blocker("AUTHORIZATION_RECEIPT_INVALID", str(error)))
        return result
    execution_value = receipts["execution"]
    if execution_value is None:
        result["blockers"].append(
            _blocker(
                "EXTERNAL_TARGET_EXECUTION_REQUIRED",
                "Authorized real target execution and raw evidence are still required.",
            )
        )
        return result
    try:
        execution, executor_identity, execution_digest = _execution(
            execution_value,
            target_input=target_input,
            authorization=authorization,
            authorization_digest=authorization_digest,
            trust_keys=trust_keys,
            now=now,
        )
        result["externalExecution"] = "PASSED"
        result["state"] = "READY_FOR_INDEPENDENT_VERIFICATION"
        result["evidenceEnvelopeDigests"].append(execution_digest)
    except ValueError as error:
        result["state"] = "BLOCKED_EVIDENCE"
        result["blockers"].append(_blocker("EXECUTION_RECEIPT_INVALID", str(error)))
        return result
    verification_value = receipts["independentVerification"]
    if verification_value is None:
        result["blockers"].append(
            _blocker(
                "INDEPENDENT_VERIFICATION_RECEIPT_REQUIRED",
                "An independently signed verification receipt is still required.",
            )
        )
        return result
    try:
        verification, verifier_identity, verification_digest = _independent_verification(
            verification_value,
            target_input=target_input,
            execution=execution,
            execution_digest=execution_digest,
            executor_identity=executor_identity,
            implementer=implementer,
            trust_keys=trust_keys,
            now=now,
        )
        result["independentVerification"] = "PASSED"
        result["state"] = "READY_FOR_CERTIFICATION"
        result["evidenceEnvelopeDigests"].append(verification_digest)
    except ValueError as error:
        result["state"] = "BLOCKED_EVIDENCE"
        result["blockers"].append(
            _blocker("INDEPENDENT_VERIFICATION_RECEIPT_INVALID", str(error))
        )
        return result
    certification_value = receipts["certification"]
    if certification_value is None:
        result["blockers"].append(
            _blocker(
                "CERTIFICATION_RECEIPT_REQUIRED",
                "A separately signed production certification decision is still required.",
            )
        )
        return result
    try:
        _, _, certification_digest = _certification(
            certification_value,
            target_input=target_input,
            verification=verification,
            verification_digest=verification_digest,
            verifier_identity=verifier_identity,
            executor_identity=executor_identity,
            implementer=implementer,
            trust_keys=trust_keys,
            now=now,
        )
        result["certification"] = "CERTIFIED"
        result["state"] = "PRODUCTION_DEFINITION_OF_DONE"
        result["evidenceEnvelopeDigests"].append(certification_digest)
    except ValueError as error:
        result["state"] = "BLOCKED_EVIDENCE"
        result["blockers"].append(_blocker("CERTIFICATION_RECEIPT_INVALID", str(error)))
    return result


def _aggregate_state(passed: int, total: int, *, not_run: str = "NOT_RUN") -> str:
    if passed == 0:
        return not_run
    if passed == total:
        return "PASSED"
    return "PARTIAL"


def evaluate_production_qualification(
    request: Mapping[str, Any],
    *,
    trust_store: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    raw = _object(request, "qualification request")
    _walk_untrusted(raw)
    _exact_fields(
        raw,
        {
            "schemaVersion",
            "scope",
            "capabilitySnapshotDigest",
            "trustStoreDigest",
            "implementer",
            "targets",
        },
        "qualification request",
    )
    if raw["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError("qualification request schemaVersion must be 1.0")
    evaluated_at = now or datetime.now(UTC)
    if evaluated_at.tzinfo is None:
        raise ValueError("qualification evaluation time must be timezone-aware")
    evaluated_at = evaluated_at.astimezone(UTC)
    scope = _scope(raw["scope"])
    scope_digest = _digest(scope)
    implementer_raw = _object(raw["implementer"], "implementer")
    _exact_fields(implementer_raw, {"actorId", "organizationId"}, "implementer")
    implementer = {
        "actorId": _required_string(
            implementer_raw["actorId"], "implementer.actorId", pattern=_SCOPE_TOKEN, maximum=128
        ),
        "organizationId": _required_string(
            implementer_raw["organizationId"],
            "implementer.organizationId",
            pattern=_SCOPE_TOKEN,
            maximum=128,
        ),
    }
    if implementer["actorId"] != scope["actorId"]:
        raise ValueError("implementer.actorId must match scope.actorId")
    current_snapshot = str(commercial_capabilities()["capabilitySnapshotDigest"])
    if raw["capabilitySnapshotDigest"] != current_snapshot:
        raise ValueError("qualification capability snapshot is stale")

    trust_ready = False
    trust_digest: str | None = None
    trust_keys: dict[str, dict[str, Any]] = {}
    requested_trust_digest = raw["trustStoreDigest"]
    if requested_trust_digest is not None:
        requested_trust_digest = _required_digest(
            requested_trust_digest, "qualification request.trustStoreDigest"
        )
    if trust_store is not None:
        parsed_trust_store = parse_production_trust_store_json(_canonical_bytes(trust_store))
        trust_digest = production_trust_store_digest(parsed_trust_store)
        if requested_trust_digest != trust_digest:
            raise ValueError("qualification trust store digest binding mismatch")
        trust_keys = _trust_keys(parsed_trust_store)
        trust_ready = True

    targets_raw = raw["targets"]
    if not isinstance(targets_raw, list) or len(targets_raw) != EXPECTED_TARGET_COUNT:
        raise ValueError("qualification request must contain exactly 13 target entries")
    catalog_targets = _catalog_targets()
    expected_ids = [target["targetId"] for target in catalog_targets]
    observed_ids: list[str] = []
    target_objects: list[dict[str, Any]] = []
    for index, raw_target in enumerate(targets_raw):
        target = _object(raw_target, f"targets[{index}]")
        _exact_fields(
            target,
            {
                "targetId",
                "exactTuple",
                "disposableEnvironment",
                "vendorTools",
                "independentVerifier",
                "receipts",
            },
            f"targets[{index}]",
        )
        target_id = _required_string(target["targetId"], f"targets[{index}].targetId")
        observed_ids.append(target_id)
        target_objects.append(target)
    if observed_ids != expected_ids or len(set(observed_ids)) != EXPECTED_TARGET_COUNT:
        raise ValueError("qualification targets must match the exact catalog order and identities")

    target_results = [
        _target_result(
            target_objects[index],
            index=index,
            catalog_target=catalog_targets[index],
            scope_digest=scope_digest,
            capability_snapshot_digest=current_snapshot,
            implementer=implementer,
            trust_keys=trust_keys,
            trust_ready=trust_ready,
            now=evaluated_at,
        )
        for index in range(EXPECTED_TARGET_COUNT)
    ]
    input_complete = sum(
        result["qualificationInputDigest"] is not None for result in target_results
    )
    authorized = sum(result["authorization"] == "VERIFIED" for result in target_results)
    executed = sum(result["externalExecution"] == "PASSED" for result in target_results)
    verified = sum(
        result["independentVerification"] == "PASSED" for result in target_results
    )
    certified = sum(result["certification"] == "CERTIFIED" for result in target_results)
    global_certification = (
        "CERTIFIED"
        if certified == EXPECTED_TARGET_COUNT
        else "PARTIALLY_CERTIFIED"
        if certified
        else "NOT_CERTIFIED"
    )
    result: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "protocolVersion": PROTOCOL_VERSION,
        "package": "chinadb-commercial-migration-skills",
        "scope": scope,
        "scopeDigest": scope_digest,
        "capabilitySnapshotDigest": current_snapshot,
        "trustStoreDigest": trust_digest,
        "requestDigest": _digest(raw),
        "evaluatedAt": _utc_text(evaluated_at),
        "targets": target_results,
        "summary": {
            "targetCount": EXPECTED_TARGET_COUNT,
            "inputCompleteTargetCount": input_complete,
            "authorizationVerifiedTargetCount": authorized,
            "externalExecutionPassedTargetCount": executed,
            "independentlyVerifiedTargetCount": verified,
            "productionDefinitionOfDoneCount": certified,
        },
        "externalExecution": _aggregate_state(executed, EXPECTED_TARGET_COUNT),
        "independentVerification": _aggregate_state(verified, EXPECTED_TARGET_COUNT),
        "certification": global_certification,
        "targetSql": None,
        "productionDefinitionOfDoneCount": certified,
        "effects": {"externalCallsExecuted": []},
    }
    result["resultDigest"] = _digest(result)
    return result


def qualification_result_is_currently_fail_closed(value: Mapping[str, Any]) -> bool:
    result = _object(value, "qualification result")
    return bool(
        result.get("externalExecution") == "NOT_RUN"
        and result.get("independentVerification") == "NOT_RUN"
        and result.get("certification") == "NOT_CERTIFIED"
        and result.get("targetSql") is None
        and result.get("productionDefinitionOfDoneCount") == 0
        and _object(result.get("summary"), "qualification result.summary").get(
            "productionDefinitionOfDoneCount"
        )
        == 0
        and _object(result.get("effects"), "qualification result.effects").get(
            "externalCallsExecuted"
        )
        == []
    )


def signed_envelope(
    *,
    key_id: str,
    private_key: Any,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a signed envelope for tests and authorized offline tooling.

    The caller owns key custody.  Runtime requests never accept private keys.
    """

    checked_key_id = _required_string(key_id, "signed envelope keyId")
    payload_object = _object(payload, "signed envelope payload")
    signature = private_key.sign(_canonical_bytes(payload_object))
    return {
        "algorithm": "ed25519",
        "keyId": checked_key_id,
        "payload": payload_object,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def target_qualification_input_digest(
    request: Mapping[str, Any],
    target_id: str,
    *,
    now: datetime,
) -> str:
    """Return the digest an external authorization must bind for one target."""

    result = evaluate_production_qualification(request, now=now)
    for target in result["targets"]:
        if target["targetId"] != target_id:
            continue
        digest = target["qualificationInputDigest"]
        if digest is None:
            raise ValueError(
                "target qualification input is incomplete: "
                + ", ".join(str(item["code"]) for item in target["blockers"])
            )
        return str(digest)
    raise ValueError(f"unknown ChinaDB target id: {target_id}")
