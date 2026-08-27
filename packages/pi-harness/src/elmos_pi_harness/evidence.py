"""Digest-bound evidence records and conservative certification decisions."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, digest, utc_now


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    kind: str
    status: str
    artifact_digests: tuple[str, ...] = ()
    executor: str | None = None
    independent_verifier: str | None = None
    authorization_id: str | None = None
    replay_command: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        uuid.UUID(self.evidence_id)
        if self.status not in {"LOCAL_EXECUTED", "EXTERNAL_VERIFIED", "INDEPENDENTLY_VERIFIED", "NOT_RUN", "UNKNOWN", "FAILED"}:
            raise ValueError("invalid evidence status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id, "kind": self.kind, "status": self.status,
            "artifact_digests": list(self.artifact_digests), "executor": self.executor,
            "independent_verifier": self.independent_verifier, "authorization_id": self.authorization_id,
            "replay_command": self.replay_command, "metadata": dict(self.metadata),
        }


class EvidenceChain:
    def __init__(self, *, scope: Mapping[str, Any]) -> None:
        self.scope = dict(scope)
        self._items: list[EvidenceItem] = []

    def append(self, item: EvidenceItem) -> None:
        if any(existing.evidence_id == item.evidence_id for existing in self._items):
            raise ValueError("duplicate evidence id")
        self._items.append(item)

    @property
    def items(self) -> tuple[EvidenceItem, ...]:
        return tuple(self._items)

    def manifest(self) -> dict[str, Any]:
        payload = {
            "manifest_version": "1.0",
            "scope": self.scope,
            "items": [item.to_dict() for item in self._items],
            "created_at": utc_now(),
        }
        payload["manifest_digest"] = digest(payload)
        return payload

    def write(self, path: str | Path) -> dict[str, Any]:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = canonical_bytes(self.manifest())
        fd, temporary = tempfile.mkstemp(prefix=".evidence-", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return json.loads(raw)


def evaluate_certification(
    items: Iterable[EvidenceItem],
    *,
    external_execution: bool = False,
    independent_verification: bool = False,
    customer_acceptance: bool = False,
) -> dict[str, Any]:
    records = list(items)
    if not records:
        return {"status": "NOT_RUN", "certified": False, "blockers": ["no_evidence"]}
    blockers = sorted({item.status.lower() for item in records if item.status in {"NOT_RUN", "UNKNOWN", "FAILED"}})
    if blockers:
        return {"status": "BLOCKED", "certified": False, "blockers": blockers}
    if not external_execution:
        return {"status": "READY_FOR_EXTERNAL_GATE", "certified": False, "blockers": ["external_execution_not_run"]}
    if not independent_verification:
        return {"status": "NOT_CERTIFIED", "certified": False, "blockers": ["independent_verification_missing"]}
    if not customer_acceptance:
        return {"status": "READY_FOR_HUMAN_DECISION", "certified": False, "blockers": ["customer_acceptance_missing"]}
    return {"status": "READY_FOR_HUMAN_DECISION", "certified": False, "blockers": ["production_certification_is_external"]}
