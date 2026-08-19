"""Skill 15 — result artifact publisher.

Builds an immutable, content-addressed manifest of everything a run produced.
The manifest itself is digested, so a later reader can tell whether the list they
are holding is the one that was sealed.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .durable import DurableStore
from .io_utils import write_json


def _manifest_digest(entries: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        [{k: entry[k] for k in ("logical_name", "version", "sha256", "size_bytes")} for entry in entries],
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_manifest(store: DurableStore, run_id: str, seal: bool = True) -> dict[str, Any]:
    run = store.get_run(run_id)
    artifacts = store.artifacts(run_id)
    checkpoints = store.checkpoints(run_id)

    entries = [
        {
            "logical_name": artifact["logical_name"],
            "version": artifact["version"],
            "media_type": artifact["media_type"],
            "size_bytes": artifact["size_bytes"],
            "sha256": artifact["sha256"],
            "storage_uri": artifact["storage_uri"],
            "git_ref": artifact["git_ref"],
        }
        for artifact in artifacts
    ]
    duplicates = _duplicate_logical_names(entries)

    return {
        "schema_version": "1.0.0",
        "artifact": "result-manifest",
        "run_id": run_id,
        "project_id": run["project_id"],
        "run_state": run["state"],
        "sealed": bool(seal and run["state"] in {"succeeded", "failed", "cancelled"}),
        "seal_refused_reason": (
            None if run["state"] in {"succeeded", "failed", "cancelled"}
            else f"run is still '{run['state']}'; a manifest is only sealed once the run has settled"
        ),
        "artifact_count": len(entries),
        "total_bytes": sum(entry["size_bytes"] for entry in entries),
        "artifacts": entries,
        "superseded_logical_names": duplicates,
        "git_checkpoints": [
            {"task_id": cp["task_id"], "git_commit": cp["git_commit"], "created_at": cp["created_at"]}
            for cp in checkpoints if cp["git_commit"]
        ],
        "manifest_sha256": _manifest_digest(entries),
        "verification": (
            "Recompute sha256 over each artifact's bytes and re-digest the (logical_name, version, "
            "sha256, size_bytes) tuples; a mismatch means the manifest and the bytes have diverged."
        ),
    }


def _duplicate_logical_names(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Logical names carrying more than one version: the earlier ones are superseded, not deleted."""
    by_name: dict[str, list[int]] = {}
    for entry in entries:
        by_name.setdefault(entry["logical_name"], []).append(entry["version"])
    return [
        {"logical_name": name, "versions": sorted(versions), "current": max(versions)}
        for name, versions in sorted(by_name.items()) if len(versions) > 1
    ]


def verify_manifest(
    manifest: dict[str, Any], resolver: Callable[[dict[str, Any]], bytes]
) -> dict[str, Any]:
    """Re-hash every artifact through ``resolver(entry) -> bytes`` and report mismatches."""
    mismatches: list[dict[str, Any]] = []
    missing: list[str] = []
    for entry in manifest["artifacts"]:
        try:
            content = resolver(entry)
        except (KeyError, FileNotFoundError, OSError):
            missing.append(entry["logical_name"])
            continue
        digest = hashlib.sha256(content).hexdigest()
        if digest != entry["sha256"]:
            mismatches.append({
                "logical_name": entry["logical_name"], "version": entry["version"],
                "expected": entry["sha256"], "actual": digest,
            })
    recomputed = _manifest_digest(manifest["artifacts"])
    return {
        "verified": not mismatches and not missing and recomputed == manifest["manifest_sha256"],
        "content_mismatches": mismatches,
        "missing_artifacts": missing,
        "manifest_digest_matches": recomputed == manifest["manifest_sha256"],
    }


def publish(store: DurableStore, run_id: str, output: str | Path, seal: bool = True) -> dict[str, Any]:
    manifest = build_manifest(store, run_id, seal=seal)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / "result-manifest.json", manifest)
    return manifest
