"""Content-addressed evidence and patch-scope validation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import ContractError, Status, normalize_relative_path, require_mapping, require_string
from .planning import paths_overlap


_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVIDENCE_CLASSES = frozenset({"local", "repository", "provider", "runner", "worktree", "scm", "external"})


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return "sha256:" + digest.hexdigest(), size


def confined_file(root: Path, relative_path: str) -> Path:
    relative = normalize_relative_path(relative_path, "evidence.path")
    root_resolved = root.resolve(strict=True)
    candidate = root_resolved.joinpath(*relative.split("/"))
    cursor = root_resolved
    for part in relative.split("/"):
        cursor = cursor / part
        if cursor.is_symlink():
            raise ContractError("evidence_symlink", f"evidence path crosses a symlink: {relative}")
    resolved = candidate.resolve(strict=True)
    if root_resolved != resolved and root_resolved not in resolved.parents:
        raise ContractError("evidence_path_escape", f"evidence escapes approved root: {relative}")
    if not resolved.is_file():
        raise ContractError("evidence_not_file", f"evidence is not a regular file: {relative}")
    return resolved


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    kind: str
    path: str
    sha256: str
    byte_count: int
    executor_id: str
    verifier_id: str
    authorization_id: str
    status: Status
    evidence_class: str = "local"

    @classmethod
    def collect(
        cls,
        *,
        root: Path,
        evidence_id: str,
        kind: str,
        path: str,
        executor_id: str,
        verifier_id: str,
        authorization_id: str,
        status: Status = Status.LOCAL_ENGINEERING_VALIDATED,
        evidence_class: str = "local",
        require_independent: bool = True,
    ) -> "EvidenceRecord":
        executor = require_string(executor_id, "executor_id")
        verifier = require_string(verifier_id, "verifier_id")
        if require_independent and executor == verifier:
            raise ContractError("self_verification", "executor and verifier must be different")
        if status in {Status.READY, Status.PLANNED, Status.NOT_CERTIFIED}:
            raise ContractError("invalid_evidence_status", "evidence must record a terminal observation")
        evidence_class = require_string(evidence_class, "evidence_class")
        if evidence_class not in _EVIDENCE_CLASSES:
            raise ContractError("invalid_evidence_class", "evidence class is not in the closed catalog")
        normalized = normalize_relative_path(path, "evidence.path")
        digest, size = _hash_file(confined_file(root, normalized))
        return cls(
            require_string(evidence_id, "evidence_id"),
            require_string(kind, "kind"),
            normalized,
            digest,
            size,
            executor,
            verifier,
            require_string(authorization_id, "authorization_id"),
            status,
            require_string(evidence_class, "evidence_class"),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "EvidenceRecord":
        value = require_mapping(payload, "evidence")
        try:
            status = Status(value.get("status"))
        except (TypeError, ValueError) as exc:
            raise ContractError("invalid_evidence_status", "unknown evidence status") from exc
        byte_count = value.get("byte_count")
        if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
            raise ContractError("invalid_evidence_size", "evidence byte_count must be non-negative integer")
        digest = require_string(value.get("sha256"), "sha256")
        if not _SHA256.fullmatch(digest):
            raise ContractError("invalid_evidence_digest", "evidence sha256 must be a lowercase prefixed digest")
        evidence_class = require_string(value.get("evidence_class", "local"), "evidence_class")
        if evidence_class not in _EVIDENCE_CLASSES:
            raise ContractError("invalid_evidence_class", "evidence class is not in the closed catalog")
        if status in {Status.READY, Status.PLANNED, Status.NOT_CERTIFIED}:
            raise ContractError("invalid_evidence_status", "evidence must record a terminal observation")
        return cls(
            require_string(value.get("evidence_id"), "evidence_id"),
            require_string(value.get("kind"), "kind"),
            normalize_relative_path(value.get("path"), "evidence.path"),
            digest,
            byte_count,
            require_string(value.get("executor_id"), "executor_id"),
            require_string(value.get("verifier_id"), "verifier_id"),
            require_string(value.get("authorization_id"), "authorization_id"),
            status,
            evidence_class,
        )

    def verify(self, root: Path, *, require_independent: bool = True) -> Path:
        if require_independent and self.executor_id == self.verifier_id:
            raise ContractError("self_verification", "executor and verifier must be different")
        digest, size = _hash_file(confined_file(root, self.path))
        if digest != self.sha256:
            raise ContractError("evidence_digest_mismatch", f"digest mismatch for {self.evidence_id}")
        if size != self.byte_count:
            raise ContractError("evidence_size_mismatch", f"byte count mismatch for {self.evidence_id}")
        return confined_file(root, self.path)

    def to_payload(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "path": self.path,
            "sha256": self.sha256,
            "byte_count": self.byte_count,
            "executor_id": self.executor_id,
            "verifier_id": self.verifier_id,
            "authorization_id": self.authorization_id,
            "status": self.status.value,
            "evidence_class": self.evidence_class,
        }


@dataclass(frozen=True, slots=True)
class PatchScopeDecision:
    status: Status
    reasons: tuple[str, ...]
    changed_paths: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {"status": self.status.value, "reasons": list(self.reasons), "changed_paths": list(self.changed_paths)}


def validate_patch_scope(
    *,
    changed_paths: Iterable[str],
    owned_paths: Iterable[str],
    forbidden_paths: Iterable[str] = (),
    deleted_test_paths: Iterable[str] = (),
) -> PatchScopeDecision:
    changed = tuple(normalize_relative_path(path, "changed_path") for path in changed_paths)
    owned = tuple(normalize_relative_path(path, "owned_path") for path in owned_paths)
    forbidden = tuple(normalize_relative_path(path, "forbidden_path") for path in forbidden_paths)
    deleted_tests = tuple(normalize_relative_path(path, "deleted_test_path") for path in deleted_test_paths)
    reasons: list[str] = []
    if not changed:
        reasons.append("no_op_patch")
    for path in changed:
        if not any(paths_overlap(path, owner) for owner in owned):
            reasons.append(f"out_of_scope:{path}")
        if any(paths_overlap(path, denied) for denied in forbidden):
            reasons.append(f"forbidden_path:{path}")
    if deleted_tests:
        reasons.extend(f"deleted_test:{path}" for path in deleted_tests)
    return PatchScopeDecision(Status.BLOCKED if reasons else Status.LOCAL_ENGINEERING_VALIDATED, tuple(sorted(set(reasons))), changed)
