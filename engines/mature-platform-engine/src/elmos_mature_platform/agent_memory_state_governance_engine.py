"""Agent Memory State Governance Engine (Batch 42 - Skill 1424).

Governs Agent working, episodic, and semantic memory state. Enforces memory quotas,
tenant isolation, TTL expiration, secret/PII redaction scrubbing, and safe checkpointing.
"""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    AgentMemoryEntry,
    MemoryGovernanceQuota,
    MemoryScope,
    MemoryStateStatus,
)


class AgentMemoryStateGovernanceEngine:
    """Enforces governance, privacy, security boundaries, and lifecycle on Agent memory state."""

    # Regex patterns for detecting sensitive data to scrub
    _SECRET_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
        re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
        re.compile(r"""(api[_-]?key|password|secret)[\s:=]+["\']?([a-zA-Z0-9_\-\.]+)""", re.IGNORECASE),
    ]

    def __init__(self) -> None:
        self._entries: Dict[str, AgentMemoryEntry] = {}
        self._quotas: Dict[str, MemoryGovernanceQuota] = {}

    def set_quota(self, quota: MemoryGovernanceQuota) -> str:
        """Configure memory capacity quotas for a tenant."""
        if not quota.tenant_id:
            raise ValueError("tenant_id is required")

        self._quotas[quota.tenant_id] = quota
        return quota.tenant_id

    def write_memory(self, entry: AgentMemoryEntry) -> str:
        """Write an entry to agent memory, enforcing quota, tenant isolation, and scrubbing."""
        if not entry.agent_id or not entry.tenant_id or not entry.key:
            raise ValueError("agent_id, tenant_id, and key are required")

        quota = self._quotas.get(entry.tenant_id)
        if quota:
            agent_active = [
                e
                for e in self._entries.values()
                if e.tenant_id == entry.tenant_id
                and e.agent_id == entry.agent_id
                and e.status == MemoryStateStatus.ACTIVE
            ]
            if len(agent_active) >= quota.max_entries_per_agent:
                raise MemoryError(
                    f"Agent {entry.agent_id} exceeded max memory entries ({quota.max_entries_per_agent})"
                )

            current_bytes = sum(e.size_bytes for e in agent_active)
            if current_bytes + len(entry.value.encode("utf-8")) > quota.max_bytes_per_agent:
                raise MemoryError(
                    f"Agent {entry.agent_id} exceeded max memory bytes ({quota.max_bytes_per_agent})"
                )

        if not entry.entry_id:
            entry.entry_id = f"mem-{uuid.uuid4().hex[:8]}"

        now_str = datetime.now(timezone.utc).isoformat()
        if not entry.created_at:
            entry.created_at = now_str
        entry.last_accessed = now_str

        # Content scrubbing for secrets / tokens
        scrubbed_value = entry.value
        has_pii = False
        for pat in self._SECRET_PATTERNS:
            if pat.search(scrubbed_value):
                has_pii = True
                scrubbed_value = pat.sub("[REDACTED_SECRET]", scrubbed_value)

        entry.value = scrubbed_value
        entry.contains_redacted_pii = has_pii
        entry.size_bytes = len(scrubbed_value.encode("utf-8"))

        self._entries[entry.entry_id] = entry
        return entry.entry_id

    def read_memory(
        self, agent_id: str, tenant_id: str, key: str, scope: Optional[MemoryScope] = None
    ) -> Optional[AgentMemoryEntry]:
        """Read active memory entry with strict tenant isolation and update access timestamp."""
        for e in self._entries.values():
            if (
                e.agent_id == agent_id
                and e.tenant_id == tenant_id
                and e.key == key
                and e.status == MemoryStateStatus.ACTIVE
            ):
                if scope and e.scope != scope:
                    continue
                e.last_accessed = datetime.now(timezone.utc).isoformat()
                return e
        return None

    def evict_expired_memories(self, current_time: Optional[str] = None) -> int:
        """Expire memories whose TTL has elapsed relative to now."""
        now_dt = (
            datetime.fromisoformat(current_time)
            if current_time
            else datetime.now(timezone.utc)
        )
        evicted = 0

        for e in self._entries.values():
            if e.status != MemoryStateStatus.ACTIVE:
                continue
            created_dt = datetime.fromisoformat(e.created_at)
            elapsed_seconds = (now_dt - created_dt).total_seconds()
            if elapsed_seconds > e.ttl_seconds:
                e.status = MemoryStateStatus.PURGED_EXPIRATION
                evicted += 1

        return evicted

    def purge_agent_memory(self, agent_id: str, tenant_id: str) -> int:
        """Cleanly purge all memory entries belonging to a specific agent in a tenant."""
        purged = 0
        for e in self._entries.values():
            if e.agent_id == agent_id and e.tenant_id == tenant_id:
                if e.status == MemoryStateStatus.ACTIVE:
                    e.status = MemoryStateStatus.ARCHIVED
                    purged += 1
        return purged

    def purge_tenant_memory(self, tenant_id: str) -> int:
        """Purge all memories for a tenant upon offboarding or reset."""
        purged = 0
        for e in self._entries.values():
            if e.tenant_id == tenant_id and e.status == MemoryStateStatus.ACTIVE:
                e.status = MemoryStateStatus.ARCHIVED
                purged += 1
        return purged

    def checkpoint_memory_state(self, agent_id: str, tenant_id: str) -> Dict[str, Any]:
        """Generate a portable serialized checkpoint of active agent memories."""
        active_entries = [
            {
                "entry_id": e.entry_id,
                "scope": e.scope.value if hasattr(e.scope, "value") else str(e.scope),
                "key": e.key,
                "value": e.value,
                "created_at": e.created_at,
                "ttl_seconds": e.ttl_seconds,
                "size_bytes": e.size_bytes,
            }
            for e in self._entries.values()
            if e.agent_id == agent_id
            and e.tenant_id == tenant_id
            and e.status == MemoryStateStatus.ACTIVE
        ]

        return {
            "checkpoint_id": f"chkpt-{uuid.uuid4().hex[:8]}",
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "entry_count": len(active_entries),
            "entries": active_entries,
        }

    def restore_memory_state(
        self, agent_id: str, tenant_id: str, checkpoint: Dict[str, Any]
    ) -> int:
        """Restore agent memory entries from a checkpoint."""
        if checkpoint.get("agent_id") != agent_id or checkpoint.get("tenant_id") != tenant_id:
            raise PermissionError("Checkpoint tenant_id or agent_id does not match target")

        entries_data = checkpoint.get("entries", [])
        restored = 0

        for item in entries_data:
            entry = AgentMemoryEntry(
                entry_id=item["entry_id"],
                agent_id=agent_id,
                tenant_id=tenant_id,
                scope=MemoryScope(item["scope"]),
                key=item["key"],
                value=item["value"],
                status=MemoryStateStatus.ACTIVE,
                created_at=item.get("created_at", datetime.now(timezone.utc).isoformat()),
                ttl_seconds=item.get("ttl_seconds", 86400),
                size_bytes=item.get("size_bytes", len(item["value"].encode("utf-8"))),
            )
            self._entries[entry.entry_id] = entry
            restored += 1

        return restored

    def get_governance_report(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate aggregated memory status, security redactions, and storage metrics."""
        samples = [
            e for e in self._entries.values() if not tenant_id or e.tenant_id == tenant_id
        ]
        total = len(samples)
        active = sum(1 for e in samples if e.status == MemoryStateStatus.ACTIVE)
        purged = sum(1 for e in samples if e.status == MemoryStateStatus.PURGED_EXPIRATION)
        redacted = sum(1 for e in samples if e.contains_redacted_pii)
        total_bytes = sum(e.size_bytes for e in samples if e.status == MemoryStateStatus.ACTIVE)

        return {
            "total_entries": total,
            "active_entries": active,
            "purged_entries": purged,
            "redacted_sensitive_entries": redacted,
            "active_storage_bytes": total_bytes,
        }
