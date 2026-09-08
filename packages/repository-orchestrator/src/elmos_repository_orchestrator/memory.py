"""Governed tenant-scoped experience memory with explicit promotion gates."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .contracts import ContractError, canonical_json, require_string, sha256_payload
from .retrieval import tokenize


class MemoryTier(str, Enum):
    BRONZE = "BRONZE"
    SILVER = "SILVER"
    GOLD = "GOLD"


@dataclass(frozen=True, slots=True)
class ExperienceRecord:
    record_id: str
    tenant_id: str
    project_id: str
    revision_id: str
    task_signature: str
    lesson: str
    source_run_id: str
    actor_id: str
    tier: MemoryTier = MemoryTier.BRONZE
    independent_verifier_id: str | None = None
    accepted_by: str | None = None
    rights_approved: bool = False
    global_training_consent: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "record_id",
            "tenant_id",
            "project_id",
            "revision_id",
            "task_signature",
            "lesson",
            "source_run_id",
            "actor_id",
        ):
            require_string(getattr(self, field_name), field_name)
        if self.independent_verifier_id == self.actor_id and self.independent_verifier_id is not None:
            raise ContractError("verifier_not_independent", "memory verifier must differ from the producer")
        if self.tier is MemoryTier.GOLD and not (
            self.independent_verifier_id and self.accepted_by and self.rights_approved
        ):
            raise ContractError("gold_memory_unverified", "Gold memory requires verifier, acceptance, and rights approval")

    @property
    def digest(self) -> str:
        return sha256_payload(
            {
                "record_id": self.record_id,
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "revision_id": self.revision_id,
                "task_signature": self.task_signature,
                "lesson": self.lesson,
                "source_run_id": self.source_run_id,
                "actor_id": self.actor_id,
                "tier": self.tier.value,
                "independent_verifier_id": self.independent_verifier_id,
                "accepted_by": self.accepted_by,
                "rights_approved": self.rights_approved,
                "global_training_consent": self.global_training_consent,
            }
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "task_signature": self.task_signature,
            "lesson": self.lesson,
            "source_run_id": self.source_run_id,
            "actor_id": self.actor_id,
            "tier": self.tier.value,
            "independent_verifier_id": self.independent_verifier_id,
            "accepted_by": self.accepted_by,
            "rights_approved": self.rights_approved,
            "global_training_consent": self.global_training_consent,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ExperienceRecord":
        value = dict(payload)
        value["tier"] = MemoryTier(value.get("tier", MemoryTier.BRONZE.value))
        return cls(**value)


class ExperienceMemoryStore:
    def __init__(self, database_path: Path):
        self.path = database_path.resolve(strict=False)
        if not self.path.parent.is_dir():
            raise ContractError("memory_parent_missing", "memory database parent must exist")
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS experience_memory (
              record_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              project_id TEXT NOT NULL,
              revision_id TEXT NOT NULL,
              payload_json BLOB NOT NULL,
              payload_sha256 TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS experience_scope ON experience_memory(tenant_id, project_id, revision_id)"
        )
        self.connection.commit()

    def put(self, record: ExperienceRecord) -> bool:
        encoded = canonical_json(record.to_payload()).encode("utf-8")
        digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
        existing = self.connection.execute(
            "SELECT payload_sha256 FROM experience_memory WHERE record_id=?", (record.record_id,)
        ).fetchone()
        if existing is not None:
            if existing[0] != digest:
                raise ContractError("memory_identity_conflict", "memory record id already has different content")
            return False
        self.connection.execute(
            "INSERT INTO experience_memory VALUES (?, ?, ?, ?, ?, ?)",
            (record.record_id, record.tenant_id, record.project_id, record.revision_id, encoded, digest),
        )
        self.connection.commit()
        return True

    @staticmethod
    def _decode(encoded: bytes, expected: str) -> ExperienceRecord:
        actual = "sha256:" + hashlib.sha256(encoded).hexdigest()
        if actual != expected:
            raise ContractError("memory_integrity_failure", "experience memory digest mismatch")
        payload = json.loads(encoded)
        if not isinstance(payload, Mapping):
            raise ContractError("memory_contract_failure", "experience memory payload is invalid")
        return ExperienceRecord.from_payload(payload)

    def get(self, record_id: str, *, tenant_id: str, project_id: str) -> ExperienceRecord | None:
        row = self.connection.execute(
            "SELECT payload_json, payload_sha256 FROM experience_memory WHERE record_id=? AND tenant_id=? AND project_id=?",
            (require_string(record_id, "record_id"), require_string(tenant_id, "tenant_id"), require_string(project_id, "project_id")),
        ).fetchone()
        return None if row is None else self._decode(row[0], row[1])

    def search(
        self,
        text: str,
        *,
        tenant_id: str,
        project_id: str,
        revision_id: str | None = None,
        minimum_tier: MemoryTier = MemoryTier.BRONZE,
        limit: int = 10,
    ) -> tuple[ExperienceRecord, ...]:
        if not 1 <= limit <= 100:
            raise ContractError("invalid_memory_limit", "memory limit must be between 1 and 100")
        params: list[str] = [require_string(tenant_id, "tenant_id"), require_string(project_id, "project_id")]
        sql = "SELECT payload_json, payload_sha256 FROM experience_memory WHERE tenant_id=? AND project_id=?"
        if revision_id is not None:
            sql += " AND revision_id=?"
            params.append(require_string(revision_id, "revision_id"))
        query_terms = set(tokenize(text))
        order = {MemoryTier.BRONZE: 0, MemoryTier.SILVER: 1, MemoryTier.GOLD: 2}
        matches: list[tuple[int, int, ExperienceRecord]] = []
        for encoded, digest in self.connection.execute(sql, params):
            record = self._decode(encoded, digest)
            if order[record.tier] < order[minimum_tier]:
                continue
            overlap = len(query_terms & set(tokenize(record.task_signature + " " + record.lesson)))
            if overlap:
                matches.append((overlap, order[record.tier], record))
        matches.sort(key=lambda item: (-item[0], -item[1], item[2].record_id))
        return tuple(item[2] for item in matches[:limit])

    def promote(
        self,
        record_id: str,
        *,
        tenant_id: str,
        project_id: str,
        target_tier: MemoryTier,
        verifier_id: str,
        accepted_by: str | None = None,
        rights_approved: bool = False,
        global_training_consent: bool = False,
    ) -> ExperienceRecord:
        current = self.get(record_id, tenant_id=tenant_id, project_id=project_id)
        if current is None:
            raise ContractError("memory_not_found", "experience memory was not found in the trusted scope")
        if require_string(verifier_id, "verifier_id") == current.actor_id:
            raise ContractError("verifier_not_independent", "memory verifier must differ from the producer")
        order = {MemoryTier.BRONZE: 0, MemoryTier.SILVER: 1, MemoryTier.GOLD: 2}
        if order[target_tier] <= order[current.tier]:
            raise ContractError("memory_promotion_invalid", "target tier must be higher than current tier")
        promoted = replace(
            current,
            tier=target_tier,
            independent_verifier_id=verifier_id,
            accepted_by=accepted_by,
            rights_approved=rights_approved,
            global_training_consent=global_training_consent,
        )
        encoded = canonical_json(promoted.to_payload()).encode("utf-8")
        digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
        self.connection.execute(
            "UPDATE experience_memory SET payload_json=?, payload_sha256=? WHERE record_id=?",
            (encoded, digest, current.record_id),
        )
        self.connection.commit()
        return promoted

    def global_training_export(self, *, tenant_id: str, project_id: str) -> tuple[ExperienceRecord, ...]:
        rows = self.connection.execute(
            "SELECT payload_json, payload_sha256 FROM experience_memory WHERE tenant_id=? AND project_id=?",
            (require_string(tenant_id, "tenant_id"), require_string(project_id, "project_id")),
        )
        records = (self._decode(encoded, digest) for encoded, digest in rows)
        return tuple(
            sorted(
                (
                    record
                    for record in records
                    if record.tier is MemoryTier.GOLD and record.global_training_consent
                ),
                key=lambda record: record.record_id,
            )
        )

    def close(self) -> None:
        self.connection.close()
