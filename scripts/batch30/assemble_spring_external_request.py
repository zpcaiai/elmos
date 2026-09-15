"""Assemble an unsigned Spring dossier request outside the repository."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]


class DossierRequestError(ValueError):
    """Raised when an unsigned external-review request is unsafe."""


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def assemble_request(
    *, output_dir: Path, dossier_id: str, pack_keys: Sequence[str]
) -> dict[str, Any]:
    output = output_dir.resolve()
    if output.is_relative_to(ROOT.resolve()):
        raise DossierRequestError("dossier output must be outside the repository")
    if output.exists() and (not output.is_dir() or output.is_symlink()):
        raise DossierRequestError("dossier output must be a real directory")
    output.mkdir(parents=True, exist_ok=True)

    targets: list[dict[str, Any]] = []
    digests: dict[str, dict[str, str]] = {}
    for pack_key in pack_keys:
        pack = (ROOT / "framework-packs" / pack_key).resolve(strict=True)
        if not pack.is_relative_to((ROOT / "framework-packs").resolve()):
            raise DossierRequestError(f"unsafe pack key: {pack_key}")
        manifest_path = pack / "pack.json"
        certification_path = pack / "certification/certification.json"
        evidence_path = pack / "certification/evidence.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        certification = json.loads(certification_path.read_text(encoding="utf-8"))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if manifest.get("status") == "certified" or certification.get(
            "certification_decision"
        ) == "CERTIFIED":
            raise DossierRequestError(
                f"repository pack still contains an unverified certified claim: {pack_key}"
            )
        targets.append(
            {
                "pack_key": pack_key,
                "repository_status": manifest.get("status"),
                "certification_decision": "NOT_CERTIFIED",
                "external_execution_status": evidence.get(
                    "external_execution_status", "NOT_RUN"
                ),
            }
        )
        digests[pack_key] = {
            "pack_json_sha256": _sha256(manifest_path),
            "certification_json_sha256": _sha256(certification_path),
            "evidence_json_sha256": _sha256(evidence_path),
        }

    manifest = {
        "schema_version": "elmos.batch30.spring-external-review-request.v1",
        "dossier_id": dossier_id,
        "dossier_digest_scope": "CANONICAL_JSON_WITHOUT_DOSSIER_SHA256",
        "claim_ceiling": "READY_FOR_EXTERNAL_GATE",
        "certification": "NOT_CERTIFIED",
        "external_evidence": "NOT_RUN",
        "target_count": len(targets),
        "targets": targets,
        "pack_digests": digests,
        "repository_signing_authority": False,
    }
    manifest_bytes = json.dumps(
        manifest, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    ).encode("utf-8")
    dossier_digest = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    manifest["dossier_sha256"] = dossier_digest
    request = {
        "schema_version": "elmos.batch30.external-review-request.v1",
        "dossier_id": dossier_id,
        "dossier_sha256": dossier_digest,
        "requested_action": "INDEPENDENT_EXTERNAL_REVIEW",
        "request_status": "UNSIGNED",
        "signer_id": None,
        "certification": "NOT_CERTIFIED",
        "required_external_evidence_classes": 13,
        "note": "An external authority must execute, sign, and submit evidence from outside the repository.",
    }
    _write_json(output / "dossier-manifest.json", manifest)
    _write_json(output / "certification-request.json", request)
    return {"output_dir": str(output), **request}
