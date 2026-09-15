"""Shared fail-closed runner for externally mounted Spring certification evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.trust import run_trusted_openssl


class ExternalGateError(ValueError):
    """Raised when an external gate input violates the repository boundary."""


def external_root(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_dir() or resolved.is_symlink():
        raise ExternalGateError("external root must be a real directory")
    if resolved.is_relative_to(ROOT.resolve()):
        raise ExternalGateError("external root must be mounted outside the repository")
    return resolved


def audit_framework_pack(pack_key: str, mounted: Path) -> dict[str, Any]:
    pack = ROOT / "framework-packs" / pack_key
    external_pack = mounted / "packs" / pack_key
    command = [
        sys.executable,
        str(ROOT / "scripts/batch30/run_framework_gate.py"),
        str(pack),
        "--campaign",
        str(pack / "certification/p0-p11-campaign.json"),
        "--external-intake",
        str(external_pack / "external-certification-intake.json"),
        "--trust-store",
        str(external_pack / "trust-store.json"),
        "--evidence-root",
        str(pack),
        "--evidence-root",
        str(external_pack / "evidence"),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return {
        "pack_key": pack_key,
        "passed": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def verify_dossier(mounted: Path, dossier_id: str) -> dict[str, Any]:
    dossier = mounted / "dossiers" / dossier_id
    manifest_path = dossier / "dossier-manifest.json"
    request_path = dossier / "certification-request.json"
    signature_path = dossier / "certification-request.sig"
    trust_path = mounted / "trust-store.json"
    required = (manifest_path, request_path, signature_path, trust_path)
    missing = [str(path) for path in required if not path.is_file() or path.is_symlink()]
    if missing:
        return {"passed": False, "blockers": [f"missing external file: {p}" for p in missing]}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    trust = json.loads(trust_path.read_text(encoding="utf-8"))
    blockers: list[str] = []
    claimed_digest = manifest.get("dossier_sha256")
    digest_subject = dict(manifest)
    digest_subject.pop("dossier_sha256", None)
    actual_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            digest_subject,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if manifest.get("dossier_digest_scope") != "CANONICAL_JSON_WITHOUT_DOSSIER_SHA256":
        blockers.append("dossier digest scope is invalid")
    if claimed_digest != actual_digest:
        blockers.append("dossier manifest digest is invalid")
    if request.get("dossier_sha256") != manifest.get("dossier_sha256"):
        blockers.append("dossier digest mismatch")
    if request.get("dossier_id") != dossier_id or manifest.get("dossier_id") != dossier_id:
        blockers.append("dossier identity mismatch")
    if request.get("request_status") != "SIGNED":
        blockers.append("external certification request is not signed")
    signer_id = request.get("signer_id")
    authorities = [
        item
        for item in trust.get("authorities", [])
        if isinstance(item, dict) and item.get("signer_id") == signer_id
    ]
    if len(authorities) != 1:
        blockers.append("dossier signer is not uniquely trusted")
    elif authorities[0].get("revoked") is not False:
        blockers.append("dossier signer is revoked")
    else:
        key_relative = Path(str(authorities[0].get("public_key", "")))
        public_key = (mounted / key_relative).resolve()
        if (
            key_relative.is_absolute()
            or ".." in key_relative.parts
            or not public_key.is_relative_to(mounted)
            or not public_key.is_file()
            or public_key.is_symlink()
        ):
            blockers.append("trusted public key path is unsafe or missing")
        else:
            completed = run_trusted_openssl(
                [
                    "dgst",
                    "-sha256",
                    "-verify",
                    str(public_key),
                    "-signature",
                    str(signature_path),
                    str(request_path),
                ],
                timeout=30,
            )
            if completed.returncode != 0:
                blockers.append("external dossier signature verification failed")
    return {
        "passed": not blockers,
        "blockers": blockers,
        "dossier_sha256": manifest.get("dossier_sha256"),
        "target_count": manifest.get("target_count"),
    }


def run_gate(
    *, label: str, pack_keys: Sequence[str], dossier_id: str, mounted: Path
) -> tuple[int, dict[str, Any]]:
    root = external_root(mounted)
    packs = [audit_framework_pack(pack_key, root) for pack_key in pack_keys]
    dossier = verify_dossier(root, dossier_id)
    passed = all(item["passed"] for item in packs) and dossier["passed"]
    result = {
        "business_line": label,
        "passed": passed,
        "decision": "CERTIFIED" if passed else "NOT_CERTIFIED",
        "external_root": str(root),
        "packs": packs,
        "dossier": dossier,
    }
    return (0 if passed else 1), result
