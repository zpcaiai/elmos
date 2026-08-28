from __future__ import annotations

import hashlib
import json
import unittest
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK_ROOTS = (
    ROOT / "client-packs" / "frontend-72-route-equivalence-v2" / "formal-campaign",
    ROOT
    / "verification-packs"
    / "frontend-72-route-formal-equivalence-v2"
    / "formal-campaign",
)

ENGINE_VERIFIER_FILES = (
    "engine-verifier/node_modules/typescript/lib/typescript.js",
    "engine-verifier/node_modules/typescript/package.json",
)
IMPLEMENTATION_DIST_PREFIX = "implementation/engines/frontend-client-engine/dist/src/"
IMPLEMENTATION_FILES = tuple(
    f"{IMPLEMENTATION_DIST_PREFIX}{name}"
    for name in (
        "bounded-interaction-project.js",
        "bounded-interaction-source.js",
        "bounded-navigation-source.js",
        "frontend-formal-equivalence.js",
        "frontend-interaction-formal-cli.js",
        "frontend-interaction-formal-equivalence.js",
        "project-generation.js",
        "project-profiles.js",
        "project-templates.js",
        "project-types.js",
    )
)
FROZEN_FILES = frozenset((*ENGINE_VERIFIER_FILES, *IMPLEMENTATION_FILES))


class FrozenPackIntegrityError(ValueError):
    pass


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FrozenPackIntegrityError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _indexed_records(
    records: object, key: str, *, context: str
) -> dict[str, dict[str, object]]:
    if not isinstance(records, list):
        raise FrozenPackIntegrityError(f"RECORD_LIST_REQUIRED:{context}")
    indexed: dict[str, dict[str, object]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get(key), str):
            raise FrozenPackIntegrityError(f"RECORD_INVALID:{context}")
        identity = record[key]
        if identity in indexed:
            raise FrozenPackIntegrityError(f"RECORD_DUPLICATE:{context}:{identity}")
        indexed[identity] = record
    return indexed


def _referenced_ids(value: object, *, context: str) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise FrozenPackIntegrityError(f"ARTIFACT_REFS_INVALID:{context}")
    if len(value) != len(set(value)):
        raise FrozenPackIntegrityError(f"ARTIFACT_REFS_DUPLICATE:{context}")
    return set(value)


def _validate_bytes(
    relative_path: str, data: bytes, artifact: Mapping[str, object]
) -> None:
    digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
    if artifact.get("bytes") != len(data):
        raise FrozenPackIntegrityError(f"FROZEN_BYTES_MISMATCH:{relative_path}")
    if artifact.get("sha256") != digest:
        raise FrozenPackIntegrityError(f"FROZEN_SHA256_MISMATCH:{relative_path}")


def _validate_evidence_boundary(pack_root: Path) -> None:
    package_root = pack_root.parent
    pack = _load_json(package_root / "pack.json")
    certification = _load_json(package_root / "certification" / "certification.json")
    gate = _load_json(package_root / "certification" / "gate-result.json")

    if pack.get("status") != "experimental":
        raise FrozenPackIntegrityError("PACK_STATUS_NOT_EXPERIMENTAL")
    if certification.get("status") != "experimental":
        raise FrozenPackIntegrityError("CERTIFICATION_STATUS_NOT_EXPERIMENTAL")
    if gate.get("pack_status") != "experimental":
        raise FrozenPackIntegrityError("GATE_PACK_STATUS_NOT_EXPERIMENTAL")
    if gate.get("certification_decision") != "NOT_CERTIFIED":
        raise FrozenPackIntegrityError("GATE_DECISION_NOT_FAIL_CLOSED")
    if gate.get("certification_requested") is not False:
        raise FrozenPackIntegrityError("GATE_CERTIFICATION_REQUESTED")
    if gate.get("external_evidence_status") != "NOT_RUN":
        raise FrozenPackIntegrityError("GATE_EXTERNAL_EVIDENCE_NOT_FAIL_CLOSED")
    for field in (
        "browser_ready",
        "native_ready",
        "runtime_ready",
        "independent_ready",
        "certification_ready",
    ):
        if gate.get(field) is not False:
            raise FrozenPackIntegrityError(f"GATE_READINESS_NOT_FALSE:{field}")


def validate_frozen_pack(
    pack_root: Path, *, byte_overrides: Mapping[str, bytes] | None = None
) -> dict[str, tuple[int, str, str]]:
    """Validate only the platform-neutral, manifest-owned 12-file closure."""

    byte_overrides = byte_overrides or {}
    unknown_overrides = set(byte_overrides) - FROZEN_FILES
    if unknown_overrides:
        raise FrozenPackIntegrityError(
            "UNKNOWN_OVERRIDE:" + ",".join(sorted(unknown_overrides))
        )

    closure_paths = {
        path.relative_to(pack_root).as_posix()
        for directory in (
            pack_root / "engine-verifier" / "node_modules" / "typescript",
            pack_root
            / "implementation"
            / "engines"
            / "frontend-client-engine"
            / "dist"
            / "src",
        )
        for path in directory.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if closure_paths != FROZEN_FILES:
        missing = sorted(FROZEN_FILES - closure_paths)
        extra = sorted(closure_paths - FROZEN_FILES)
        raise FrozenPackIntegrityError(
            f"FROZEN_CLOSURE_MISMATCH:missing={missing}:extra={extra}"
        )

    campaign = _load_json(pack_root / "frontend-formal-route-campaign-v2.json")
    artifacts = _indexed_records(
        campaign.get("artifacts"), "path", context="campaign.artifacts.path"
    )
    artifacts_by_id = _indexed_records(
        campaign.get("artifacts"), "id", context="campaign.artifacts.id"
    )

    implementation = campaign.get("implementation")
    engine_verifier = campaign.get("engine_verifier")
    if not isinstance(implementation, dict) or not isinstance(engine_verifier, dict):
        raise FrozenPackIntegrityError("CAMPAIGN_SECTIONS_INVALID")
    implementation_ids = _referenced_ids(
        implementation.get("artifact_ids"), context="campaign.implementation"
    )
    runtime_ids = _referenced_ids(
        engine_verifier.get("runtime_artifact_ids"),
        context="campaign.engine_verifier",
    )

    node_identity_artifact_id = engine_verifier.get("node_identity_artifact_id")
    node_identity_artifact = artifacts_by_id.get(node_identity_artifact_id)
    node_identity_path = pack_root / "engine-verifier" / "node-identity.json"
    if node_identity_path.is_symlink() or not node_identity_path.is_file():
        raise FrozenPackIntegrityError("NODE_IDENTITY_FILE_UNSAFE")
    if (
        node_identity_artifact is None
        or node_identity_artifact.get("path")
        != "formal-campaign/engine-verifier/node-identity.json"
        or node_identity_artifact.get("role") != "node-environment-identity-v2"
    ):
        raise FrozenPackIntegrityError("NODE_IDENTITY_ARTIFACT_REF_MISMATCH")
    _validate_bytes(
        "engine-verifier/node-identity.json",
        node_identity_path.read_bytes(),
        node_identity_artifact,
    )
    node_identity = _load_json(node_identity_path)
    expected_node_identity = {
        "portability": "PINNED_NODE_ENVIRONMENT_ASSUMPTION",
        "platform": "darwin",
        "arch": "arm64",
        "version": "v26.0.0",
    }
    if {
        field: node_identity.get(field) for field in expected_node_identity
    } != expected_node_identity:
        raise FrozenPackIntegrityError("NODE_IDENTITY_DECLARATION_MISMATCH")
    if engine_verifier.get("portability") != expected_node_identity["portability"]:
        raise FrozenPackIntegrityError("NODE_IDENTITY_PORTABILITY_REF_MISMATCH")

    implementation_manifest_path = pack_root / "implementation" / "manifest.json"
    implementation_manifest = _load_json(implementation_manifest_path)
    manifest_ids = _referenced_ids(
        implementation_manifest.get("artifact_ids"),
        context="implementation.manifest",
    )
    manifest_files = _indexed_records(
        implementation_manifest.get("files"),
        "captured_path",
        context="implementation.manifest.files",
    )
    if manifest_ids != implementation_ids:
        raise FrozenPackIntegrityError("IMPLEMENTATION_ARTIFACT_REFS_MISMATCH")
    if implementation_manifest.get("fingerprint") != implementation.get("fingerprint"):
        raise FrozenPackIntegrityError("IMPLEMENTATION_FINGERPRINT_REF_MISMATCH")

    manifest_artifact_id = implementation.get("manifest_artifact_id")
    manifest_artifact = artifacts_by_id.get(manifest_artifact_id)
    if manifest_artifact is None:
        raise FrozenPackIntegrityError("IMPLEMENTATION_MANIFEST_REF_MISSING")
    if manifest_artifact.get("path") != "formal-campaign/implementation/manifest.json":
        raise FrozenPackIntegrityError("IMPLEMENTATION_MANIFEST_PATH_MISMATCH")
    _validate_bytes(
        "implementation/manifest.json",
        implementation_manifest_path.read_bytes(),
        manifest_artifact,
    )

    validated: dict[str, tuple[int, str, str]] = {}
    for relative_path in sorted(FROZEN_FILES):
        file_path = pack_root / relative_path
        if file_path.is_symlink() or not file_path.is_file():
            raise FrozenPackIntegrityError(f"FROZEN_FILE_UNSAFE:{relative_path}")
        artifact_path = f"formal-campaign/{relative_path}"
        artifact = artifacts.get(artifact_path)
        if artifact is None:
            raise FrozenPackIntegrityError(f"FROZEN_ARTIFACT_MISSING:{relative_path}")
        artifact_id = artifact.get("id")
        if not isinstance(artifact_id, str):
            raise FrozenPackIntegrityError(
                f"FROZEN_ARTIFACT_ID_INVALID:{relative_path}"
            )

        data = (
            byte_overrides[relative_path]
            if relative_path in byte_overrides
            else file_path.read_bytes()
        )
        _validate_bytes(relative_path, data, artifact)
        digest = artifact.get("sha256")
        if not isinstance(digest, str):
            raise FrozenPackIntegrityError(f"FROZEN_SHA256_INVALID:{relative_path}")

        if relative_path in ENGINE_VERIFIER_FILES:
            if artifact_id not in runtime_ids:
                raise FrozenPackIntegrityError(
                    f"ENGINE_RUNTIME_REF_MISSING:{relative_path}"
                )
        else:
            if artifact_id not in implementation_ids:
                raise FrozenPackIntegrityError(
                    f"IMPLEMENTATION_REF_MISSING:{relative_path}"
                )
            manifest_entry = manifest_files.get(artifact_path)
            expected_repository_path = relative_path.removeprefix("implementation/")
            if (
                manifest_entry is None
                or manifest_entry.get("artifact_id") != artifact_id
                or manifest_entry.get("repository_path") != expected_repository_path
            ):
                raise FrozenPackIntegrityError(
                    f"IMPLEMENTATION_FILE_REF_MISMATCH:{relative_path}"
                )

        validated[relative_path] = (len(data), digest, artifact_id)

    _validate_evidence_boundary(pack_root)
    return validated


class FrontendV2FrozenPackIntegrityTests(unittest.TestCase):
    def test_client_and_verification_pack_closures_match_exact_manifests(self) -> None:
        client = validate_frozen_pack(PACK_ROOTS[0])
        verification = validate_frozen_pack(PACK_ROOTS[1])

        self.assertEqual(12, len(client))
        self.assertEqual(client, verification)

    def test_tampered_frozen_file_fails_closed(self) -> None:
        relative_path = f"{IMPLEMENTATION_DIST_PREFIX}project-types.js"
        tampered = (PACK_ROOTS[0] / relative_path).read_bytes() + b"// tampered\n"

        with self.assertRaisesRegex(
            FrozenPackIntegrityError, "FROZEN_(BYTES|SHA256)_MISMATCH"
        ):
            validate_frozen_pack(
                PACK_ROOTS[0], byte_overrides={relative_path: tampered}
            )


if __name__ == "__main__":
    unittest.main()
