from __future__ import annotations
import unittest
from elmos_formal_assurance.models import (
    AssuranceLevel, ProofResult, ProofRun, ProofRunState, ProofStatus,
)
from elmos_formal_assurance.orchestrator import InMemoryOrchestrator, OrchestrationError

def run(i, account="a"):
    return ProofRun(id=f"r{i}", account_id=account, obligation_id=f"o{i}")

def proved(i):
    return ProofResult(f"o{i}", ProofStatus.PROVED_SOLVER_TRUSTED,
                       AssuranceLevel.A2_SOLVER_PROVED, "SMT")

class OrchestratorTests(unittest.TestCase):
    def test_account_concurrency_limit_three(self):
        orch = InMemoryOrchestrator()
        for i in range(3):
            orch.submit(run(i))
        with self.assertRaises(OrchestrationError):
            orch.submit(run(4))

    def test_different_account_has_independent_limit(self):
        orch = InMemoryOrchestrator()
        for i in range(3):
            orch.submit(run(i,"a"))
        orch.submit(run(4,"b"))
        self.assertEqual(4, len(orch.runs))

    def test_fencing_blocks_stale_worker(self):
        orch = InMemoryOrchestrator()
        orch.submit(run(1))
        t1 = orch.acquire("r1","w1",1)
        t2 = orch.acquire("r1","w2",t1)
        with self.assertRaises(OrchestrationError):
            orch.start("r1","w1",t1)
        orch.start("r1","w2",t2)

    def test_owner_can_commit_once(self):
        orch = InMemoryOrchestrator()
        orch.submit(run(1))
        token = orch.acquire("r1","w1",1)
        orch.start("r1","w1",token)
        orch.commit("r1","w1",token,proved(1))
        self.assertEqual(ProofRunState.SUCCEEDED, orch.runs["r1"].state)
        with self.assertRaises(OrchestrationError):
            orch.commit("r1","w1",token,proved(1))

    def test_result_obligation_must_match(self):
        orch = InMemoryOrchestrator()
        orch.submit(run(1))
        token = orch.acquire("r1","w1",1)
        orch.start("r1","w1",token)
        bad = ProofResult("other",ProofStatus.PROVED_SOLVER_TRUSTED,AssuranceLevel.A2_SOLVER_PROVED,"SMT")
        with self.assertRaises(OrchestrationError):
            orch.commit("r1","w1",token,bad)

    def test_terminal_state_cannot_regress(self):
        orch = InMemoryOrchestrator()
        orch.submit(run(1))
        orch.transition("r1", ProofRunState.CANCELLED)
        with self.assertRaises(OrchestrationError):
            orch.transition("r1", ProofRunState.QUEUED)

if __name__ == "__main__":
    unittest.main()
