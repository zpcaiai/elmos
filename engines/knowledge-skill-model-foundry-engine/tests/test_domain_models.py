"""Unit tests for domain models, value objects, and lifecycle state machines."""

from __future__ import annotations

import unittest

from elmos_foundry.domain import (
    ConsentStatus,
    ContentDigest,
    DatasetItem,
    EvidenceBundle,
    ExperienceEpisode,
    GateLevel,
    KnowledgeObject,
    LifecycleState,
    ModelRelease,
    RightsClass,
    SkillContract,
    TenantScope,
)
from elmos_foundry.kernel import ExecutionKernel, KernelSecurityError, KernelStateError


class DomainModelsTests(unittest.TestCase):
    def test_tenant_scope_validation(self) -> None:
        scope = TenantScope(tenant_id="tenant-123", project_id="proj-456", actor_id="user-1")
        self.assertEqual(scope.tenant_id, "tenant-123")
        self.assertEqual(scope.project_id, "proj-456")

        with self.assertRaises(ValueError):
            TenantScope(tenant_id="", project_id="proj-456")

        with self.assertRaises(ValueError):
            TenantScope(tenant_id="tenant-123", project_id="")

    def test_content_digest_of_json(self) -> None:
        d1 = ContentDigest.of_json({"b": 2, "a": 1})
        d2 = ContentDigest.of_json({"a": 1, "b": 2})
        self.assertEqual(str(d1), str(d2))
        self.assertTrue(str(d1).startswith("sha256:"))

    def test_kernel_state_transitions(self) -> None:
        kernel = ExecutionKernel()
        self.assertTrue(kernel.validate_transition(LifecycleState.DRAFT, LifecycleState.PROFILED))
        self.assertTrue(kernel.validate_transition(LifecycleState.PROFILED, LifecycleState.PLANNED))
        self.assertTrue(kernel.validate_transition(LifecycleState.PLANNED, LifecycleState.RUNNING))

        with self.assertRaises(KernelStateError):
            kernel.validate_transition(LifecycleState.DRAFT, LifecycleState.CERTIFIED)

    def test_kernel_merkle_root_computation(self) -> None:
        kernel = ExecutionKernel()
        leaves = ["leaf1", "leaf2", "leaf3"]
        root = kernel.calculate_merkle_root(leaves)
        self.assertEqual(len(root), 64)

        # Deterministic
        root2 = kernel.calculate_merkle_root(leaves)
        self.assertEqual(root, root2)


if __name__ == "__main__":
    unittest.main()
