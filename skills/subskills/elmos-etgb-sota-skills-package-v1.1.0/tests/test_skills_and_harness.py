from pathlib import Path

from etgb.budget import BudgetLedger
from etgb.checkpoint import CheckpointStore
from etgb.evidence import EvidenceStore
from etgb.harness import HarnessRuntime, PhaseResult
from etgb.skills import audit_skills
from etgb.state import JsonRunStateStore
from etgb.io import package_root


class Adapter:
    def __init__(self, artifact: Path):
        self.artifact = artifact
        self.compensated = False
        self.cleaned = False

    def _ok(self, phase: str) -> PhaseResult:
        self.artifact.write_text(f"{phase} password=secret")
        return PhaseResult(status="passed", outputs={"phase": phase}, artifacts=[self.artifact],
                           usage={"input_tokens": 1, "output_tokens": 1, "credit_usd": 0.01, "wall_clock_ms": 1})
    def prepare(self, context): return self._ok("prepare")
    def baseline(self, context): return self._ok("baseline")
    def transform_or_generate(self, context): return self._ok("transform")
    def build(self, context): return self._ok("build")
    def validate(self, context): return self._ok("validate")
    def score(self, context): return self._ok("score")
    def publish(self, context): return self._ok("publish")
    def compensate(self, context): self.compensated = True; return PhaseResult(status="passed")
    def cleanup(self, context): self.cleaned = True; return PhaseResult(status="passed")


def test_skill_dependency_graph_is_valid() -> None:
    report = audit_skills(package_root())
    assert report["valid"] and report["skill_count"] == 24


def test_reference_harness_completes_with_durable_evidence_and_budget(tmp_path: Path) -> None:
    states = JsonRunStateStore(tmp_path / "states")
    run = states.create(run_id="run", owner_id="worker", tenant_id="tenant",
                        candidate_digest="sha256:" + "a" * 64, plan_digest="sha256:" + "b" * 64,
                        lease_seconds=600)
    budget = BudgetLedger(tmp_path / "budget.json")
    budget.reserve(run_id="run", tenant_id="tenant", owner_id="worker", max_input_tokens=100,
                   max_output_tokens=100, max_credit_usd=1, max_wall_clock_ms=1000)
    evidence = EvidenceStore(tmp_path / "evidence", hmac_key=b"key")
    runtime = HarnessRuntime(state_store=states, checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
                             budget_ledger=budget, evidence_store=evidence)
    capabilities = [f"harness.{name}" for name in ["prepare", "baseline", "transform_or_generate", "build", "validate", "score", "publish"]]
    authority = {
        "schema_version": "1.1", "authority_id": "auth", "environment_id": "env",
        "owner_type": "environment", "owner_id": "worker", "tenant_id": "tenant",
        "role": "validation-worker", "capabilities": capabilities,
        "filesystem": {"read_roots": ["/workspace"], "write_roots": ["/workspace"]},
        "network": {"mode": "deny", "allowlist": []}, "secrets": {"allowed_refs": []},
        "hidden_tests": {"read": True, "write": False, "execute": True}, "fencing_token": 1,
        "expires_at": "2030-01-01T00:00:00Z",
    }
    adapter = Adapter(tmp_path / "phase.log")
    result = runtime.execute(run_id="run", adapter=adapter,
                             context={"business_line": "spring-modernization"}, authority=authority,
                             owner_id="worker", fencing_token=run["fencing_token"])
    assert result["status"] == "COMPLETED"
    assert states.load("run")["state"] == "COMPLETED"
    assert states.load("run")["checkpoint_digest"].startswith("sha256:")
    assert budget.reconcile("run")["valid"]
    assert result["evidence"]["valid"] and result["evidence"]["signature_status"] == "valid"
    blobs = [path.read_bytes() for path in (tmp_path / "evidence/blobs/sha256").rglob("*") if path.is_file()]
    assert blobs and all(b"secret" not in content for content in blobs)
