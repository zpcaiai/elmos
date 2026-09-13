import os
from pathlib import Path
import sys
import unittest
from datetime import datetime, timedelta, timezone

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.types import (
    AgentMemoryEntry,
    MemoryGovernanceQuota,
    MemoryScope,
    MemoryStateStatus,
)
from elmos_mature_platform.agent_memory_state_governance_engine import AgentMemoryStateGovernanceEngine


class TestAgentMemoryStateGovernanceComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = AgentMemoryStateGovernanceEngine()

    def test_set_quota(self):
        quota = MemoryGovernanceQuota(
            tenant_id="tenant-1",
            max_entries_per_agent=10,
            max_bytes_per_agent=1024,
            default_ttl_seconds=3600,
        )
        tid = self.engine.set_quota(quota)
        self.assertEqual(tid, "tenant-1")

    def test_set_quota_missing_tenant(self):
        quota = MemoryGovernanceQuota(tenant_id="")
        with self.assertRaises(ValueError):
            self.engine.set_quota(quota)

    def test_write_and_read_memory(self):
        entry = AgentMemoryEntry(
            entry_id="mem-1",
            agent_id="agent-1",
            tenant_id="tenant-1",
            scope=MemoryScope.WORKING_SESSION,
            key="user_context",
            value="User prefers dark mode and concise answers",
            status=MemoryStateStatus.ACTIVE,
        )
        eid = self.engine.write_memory(entry)
        self.assertEqual(eid, "mem-1")

        retrieved = self.engine.read_memory("agent-1", "tenant-1", "user_context")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.value, "User prefers dark mode and concise answers")
        self.assertFalse(retrieved.contains_redacted_pii)

    def test_write_memory_missing_required_fields(self):
        entry = AgentMemoryEntry(entry_id="m", agent_id="", tenant_id="t", scope=MemoryScope.EPISODIC, key="k", value="v")
        with self.assertRaises(ValueError):
            self.engine.write_memory(entry)

    def test_tenant_isolation(self):
        entry = AgentMemoryEntry(
            entry_id="mem-sec",
            agent_id="agent-1",
            tenant_id="tenant-alpha",
            scope=MemoryScope.LONG_TERM_SEMANTIC,
            key="secret_project",
            value="Project Titan",
            status=MemoryStateStatus.ACTIVE,
        )
        self.engine.write_memory(entry)

        cross_tenant = self.engine.read_memory("agent-1", "tenant-beta", "secret_project")
        self.assertIsNone(cross_tenant)

        wrong_agent = self.engine.read_memory("agent-2", "tenant-alpha", "secret_project")
        self.assertIsNone(wrong_agent)

    def test_secret_pii_scrubbing(self):
        entry = AgentMemoryEntry(
            entry_id="mem-secret",
            agent_id="agent-1",
            tenant_id="tenant-1",
            scope=MemoryScope.WORKING_SESSION,
            key="credentials",
            value="Here is the key: sk-abcdef1234567890abcdef123456 and bearer secret-token-xyz1234567890",
            status=MemoryStateStatus.ACTIVE,
        )
        self.engine.write_memory(entry)

        retrieved = self.engine.read_memory("agent-1", "tenant-1", "credentials")
        self.assertIsNotNone(retrieved)
        self.assertTrue(retrieved.contains_redacted_pii)
        self.assertNotIn("sk-abcdef1234567890", retrieved.value)
        self.assertIn("[REDACTED_SECRET]", retrieved.value)

    def test_max_entries_quota_enforced(self):
        quota = MemoryGovernanceQuota(tenant_id="tenant-strict", max_entries_per_agent=2, max_bytes_per_agent=10000)
        self.engine.set_quota(quota)

        e1 = AgentMemoryEntry(entry_id="e1", agent_id="ag1", tenant_id="tenant-strict", scope=MemoryScope.WORKING_SESSION, key="k1", value="v1")
        e2 = AgentMemoryEntry(entry_id="e2", agent_id="ag1", tenant_id="tenant-strict", scope=MemoryScope.WORKING_SESSION, key="k2", value="v2")
        e3 = AgentMemoryEntry(entry_id="e3", agent_id="ag1", tenant_id="tenant-strict", scope=MemoryScope.WORKING_SESSION, key="k3", value="v3")

        self.engine.write_memory(e1)
        self.engine.write_memory(e2)
        with self.assertRaises(MemoryError):
            self.engine.write_memory(e3)

    def test_max_bytes_quota_enforced(self):
        quota = MemoryGovernanceQuota(tenant_id="tenant-byte-limit", max_entries_per_agent=10, max_bytes_per_agent=30)
        self.engine.set_quota(quota)

        e1 = AgentMemoryEntry(entry_id="e1", agent_id="ag1", tenant_id="tenant-byte-limit", scope=MemoryScope.WORKING_SESSION, key="k1", value="12345678901234567890")
        e2 = AgentMemoryEntry(entry_id="e2", agent_id="ag1", tenant_id="tenant-byte-limit", scope=MemoryScope.WORKING_SESSION, key="k2", value="12345678901234567890")

        self.engine.write_memory(e1)
        with self.assertRaises(MemoryError):
            self.engine.write_memory(e2)

    def test_evict_expired_memories(self):
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
        entry = AgentMemoryEntry(
            entry_id="mem-expire",
            agent_id="agent-1",
            tenant_id="tenant-1",
            scope=MemoryScope.WORKING_SESSION,
            key="temp_key",
            value="temporary data",
            status=MemoryStateStatus.ACTIVE,
            ttl_seconds=60,
            created_at=old_time,
        )
        self.engine.write_memory(entry)
        entry.created_at = old_time

        evicted = self.engine.evict_expired_memories()
        self.assertEqual(evicted, 1)

        read_res = self.engine.read_memory("agent-1", "tenant-1", "temp_key")
        self.assertIsNone(read_res)

    def test_purge_agent_memory(self):
        e1 = AgentMemoryEntry(entry_id="p1", agent_id="ag-purge", tenant_id="ten-1", scope=MemoryScope.WORKING_SESSION, key="k1", value="v1")
        e2 = AgentMemoryEntry(entry_id="p2", agent_id="ag-purge", tenant_id="ten-1", scope=MemoryScope.EPISODIC, key="k2", value="v2")
        e3 = AgentMemoryEntry(entry_id="p3", agent_id="ag-keep", tenant_id="ten-1", scope=MemoryScope.WORKING_SESSION, key="k3", value="v3")

        self.engine.write_memory(e1)
        self.engine.write_memory(e2)
        self.engine.write_memory(e3)

        purged = self.engine.purge_agent_memory("ag-purge", "ten-1")
        self.assertEqual(purged, 2)
        self.assertIsNone(self.engine.read_memory("ag-purge", "ten-1", "k1"))
        self.assertIsNotNone(self.engine.read_memory("ag-keep", "ten-1", "k3"))

    def test_purge_tenant_memory(self):
        e1 = AgentMemoryEntry(entry_id="t1", agent_id="ag-1", tenant_id="ten-offboard", scope=MemoryScope.WORKING_SESSION, key="k1", value="v1")
        e2 = AgentMemoryEntry(entry_id="t2", agent_id="ag-2", tenant_id="ten-offboard", scope=MemoryScope.EPISODIC, key="k2", value="v2")

        self.engine.write_memory(e1)
        self.engine.write_memory(e2)

        purged = self.engine.purge_tenant_memory("ten-offboard")
        self.assertEqual(purged, 2)
        self.assertIsNone(self.engine.read_memory("ag-1", "ten-offboard", "k1"))

    def test_checkpoint_and_restore(self):
        e1 = AgentMemoryEntry(entry_id="c1", agent_id="ag-chk", tenant_id="ten-chk", scope=MemoryScope.WORKING_SESSION, key="k1", value="v1")
        e2 = AgentMemoryEntry(entry_id="c2", agent_id="ag-chk", tenant_id="ten-chk", scope=MemoryScope.LONG_TERM_SEMANTIC, key="k2", value="v2")

        self.engine.write_memory(e1)
        self.engine.write_memory(e2)

        chkpt = self.engine.checkpoint_memory_state("ag-chk", "ten-chk")
        self.assertEqual(chkpt["entry_count"], 2)

        new_engine = AgentMemoryStateGovernanceEngine()
        restored_count = new_engine.restore_memory_state("ag-chk", "ten-chk", chkpt)
        self.assertEqual(restored_count, 2)

        restored_e1 = new_engine.read_memory("ag-chk", "ten-chk", "k1")
        self.assertIsNotNone(restored_e1)
        self.assertEqual(restored_e1.value, "v1")

    def test_restore_mismatch_permission_error(self):
        chkpt = {"agent_id": "ag-1", "tenant_id": "ten-1", "entries": []}
        with self.assertRaises(PermissionError):
            self.engine.restore_memory_state("ag-2", "ten-1", chkpt)

    def test_governance_report(self):
        e1 = AgentMemoryEntry(entry_id="r1", agent_id="ag-1", tenant_id="ten-rep", scope=MemoryScope.WORKING_SESSION, key="k1", value="clean text")
        e2 = AgentMemoryEntry(entry_id="r2", agent_id="ag-1", tenant_id="ten-rep", scope=MemoryScope.WORKING_SESSION, key="k2", value="token: sk-12345678901234567890")
        self.engine.write_memory(e1)
        self.engine.write_memory(e2)

        rep = self.engine.get_governance_report("ten-rep")
        self.assertEqual(rep["total_entries"], 2)
        self.assertEqual(rep["active_entries"], 2)
        self.assertEqual(rep["redacted_sensitive_entries"], 1)
        self.assertGreater(rep["active_storage_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
