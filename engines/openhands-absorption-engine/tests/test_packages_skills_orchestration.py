import asyncio
import dataclasses
import unittest

from elmos_openhands.errors import BudgetExceeded, ContractViolation, TenantIsolationError
from elmos_openhands.models import Identity
from elmos_openhands.orchestration import (
    ChildAgentContract,
    DagControlStore,
    DagPlan,
    MergeInput,
    SemanticMergeCoordinator,
    TemporalDagOrchestrator,
    WorkspaceStrategy,
)
from elmos_openhands.packages import (
    CapabilityPackageBuilder,
    CapabilityPackageRegistry,
    HmacPackageSigner,
    PackageConformanceRunner,
)
from elmos_openhands.skill_routing import (
    IndexedSkill,
    SemanticSkillRouter,
    SkillConstraints,
    SkillRoutingBenchmark,
    SkillRoutingContext,
    SkillRoutingStore,
)
from elmos_openhands.skills import SkillMetadata


class FakeTemporalHandle:
    run_id = "temporal-run-a"

    def __init__(self):
        self.signals = []
        self.updates = []
        self.cancelled = False
        self.start_contract = {}

    async def signal(self, name, payload):
        self.signals.append((name, dict(payload)))

    async def cancel(self):
        self.cancelled = True

    async def execute_update(self, name, payload, **kwargs):
        self.updates.append((name, dict(payload), dict(kwargs)))
        return {"status": "applied", "version": payload["plan"]["version"]}

    async def query(self, name):
        return {"phase": "children", "plan_version": 1, "query": name, **self.start_contract}


class WorkflowAlreadyStartedError(Exception):
    pass


class FakeTemporalClient:
    def __init__(self):
        self.handle = FakeTemporalHandle()
        self.started = []
        self.duplicate = False

    async def start_workflow(self, workflow, arg, **kwargs):
        if self.duplicate:
            raise WorkflowAlreadyStartedError("duplicate")
        self.started.append((workflow, dict(arg), dict(kwargs)))
        self.handle.start_contract = {
            "identity": dict(arg["plan"]["identity"]),
            "plan_digest": arg["plan"]["digest"],
            "manifest_digest": arg["manifest_digest"],
            "start_idempotency_key": arg["idempotency_key"],
        }
        return self.handle

    def get_workflow_handle(self, workflow_id, *, run_id=None):
        return self.handle


class FakeRepository:
    def __init__(self):
        self.rolled_back = []
        self.revisions = []

    def create_integration_branch(self, run_id, base_revision):
        return f"integration/{run_id}"

    def changed_files(self, revision):
        return ("shared.py",) if revision in {"rev-a", "rev-b"} else ()

    def changed_symbols(self, revision):
        return ("shared.symbol",) if revision in {"rev-a", "rev-b"} else ()

    def apply_revision(self, integration_branch, revision):
        self.revisions.append(revision)
        return {"status": "applied", "revision": revision}

    def apply_resolution(self, integration_branch, resolution):
        return {"status": "applied", "resolution": dict(resolution)}

    def head(self, integration_branch):
        return "integrated-head"

    def rollback(self, integration_branch, base_revision):
        self.rolled_back.append((integration_branch, base_revision))


class PackagesSkillsOrchestrationTests(unittest.TestCase):
    def test_deterministic_package_bundle_supply_chain_registry_and_run_pin(self):
        metadata = {
            "name": "commercial-skill",
            "version": "1.2.3",
            "publisher": "publisher-a",
            "permissions": ["workspace.read"],
            "minimum_elmos_version": "1.0.0",
            "network_domains": [],
            "contract_versions": {"skill": "1.0"},
            "migrations": [],
            "rollback": {"strategy": "deactivate-and-pin-previous"},
        }
        builder = CapabilityPackageBuilder()
        first = builder.build(metadata, {"skills/example/SKILL.md": b"# Example\n"}, {"runtime": "2.0.0"}, build_identity="builder-a", source_revision="sha256:" + "a" * 64)
        second = builder.build(metadata, {"skills/example/SKILL.md": b"# Example\n"}, {"runtime": "2.0.0"}, build_identity="builder-a", source_revision="sha256:" + "a" * 64)
        self.assertEqual(first.bundle, second.bundle)
        self.assertEqual(first.digest, second.digest)
        with self.assertRaises(ContractViolation):
            builder.verify(dataclasses.replace(first, bundle=first.bundle + b"tamper"))

        signer = HmacPackageSigner({"publisher-a": b"local-test-key"})
        registry = CapabilityPackageRegistry(signer=signer)
        package = registry.publish_build(first, trust_level="untrusted")
        self.assertEqual(registry.bundle(package.name, package.version), first.bundle)
        registry.install(package)
        registry.approve(package.name, package.version, "security-reviewer")
        registry.restrict_to_tenants(package.name, package.version, ("tenant-a",))
        registry.activate("tenant-a", package.name, package.version)
        pin = registry.bind_run("tenant-a", "run-a", package.name)
        self.assertEqual(registry.verify_resume_pins("tenant-a", "run-a", {package.name: pin.digest})[0].digest, pin.digest)
        registry.close()

    def test_package_conformance_requires_all_checks_and_independent_verifier(self):
        metadata = {
            "name": "package-a", "version": "1.0.0", "publisher": "publisher-a", "permissions": [],
            "minimum_elmos_version": "1.0.0", "network_domains": [], "contract_versions": {"skill": "1.0"},
            "migrations": [], "rollback": {"strategy": "deactivate"},
        }
        build = CapabilityPackageBuilder().build(metadata, {"README.md": b"ok"}, {}, build_identity="builder-a", source_revision="sha256:" + "b" * 64)
        checks = {name: "PASS" for name in PackageConformanceRunner.REQUIRED_CHECKS}
        result = PackageConformanceRunner().run(build, lambda _manifest: {"checks": checks, "evidence": b"sandbox-log"}, executor_id="executor-a", independent_verifier_id="verifier-b")
        self.assertEqual(result.status, "PASS")
        blocked = PackageConformanceRunner().run(build, lambda _manifest: {"checks": checks, "evidence": b"sandbox-log"}, executor_id="executor-a")
        self.assertEqual(blocked.status, "BLOCKED")

    def test_semantic_skill_routing_permissions_conflicts_progressive_loading_and_benchmark(self):
        store = SkillRoutingStore()
        safe = SkillMetadata(
            "safe-skill", "1.0.0", "Python testing workflow", frozenset({"python", "test"}),
            frozenset({"workspace.read"}), content={"contract": {"input": "repo"}, "instructions": "run tests", "examples": ["pytest"], "scripts": ["runner"]},
            token_estimate=50, package_name="package-a", trust_level="verified",
        )
        conflicting = SkillMetadata("conflicting-skill", "1.0.0", "Python alternate", frozenset({"python"}), frozenset({"workspace.read"}), content={"contract": {}, "instructions": "alternate"})
        router = SemanticSkillRouter(
            (
                IndexedSkill(safe, SkillConstraints(languages=frozenset({"python"}), max_risk="R3"), (1.0, 0.0)),
                IndexedSkill(conflicting, SkillConstraints(languages=frozenset({"python"}), incompatible_skills=frozenset({"active-skill"}), max_risk="R3"), (0.9, 0.1)),
            ),
            store,
            embed=lambda _query: (1.0, 0.0),
        )
        context = SkillRoutingContext("tenant-a", "python test", frozenset({"workspace.read"}), frozenset({"python"}), active_skills=frozenset({"active-skill"}), task_risk="R2")
        ranked = router.route(context)
        self.assertEqual(ranked[0].name, "safe-skill")
        self.assertFalse(next(item for item in ranked if item.name == "conflicting-skill").load_allowed)
        with self.assertRaises(ContractViolation):
            router.disclose(context, "conflicting-skill", "L1_contract", request_id="request-a", window_key="day-a", token_limit=1000)
        with self.assertRaises(ContractViolation):
            router.disclose(context, "safe-skill", "L2_instructions", request_id="request-a", window_key="day-a", token_limit=1000)
        router.disclose(context, "safe-skill", "L1_contract", request_id="request-a", window_key="day-a", token_limit=1000)
        router.disclose(context, "safe-skill", "L2_instructions", request_id="request-a", window_key="day-a", token_limit=1000)
        disclosed = router.disclose(context, "safe-skill", "L3_examples", request_id="request-a", window_key="day-a", token_limit=1000)
        self.assertIn("scripts", disclosed)
        benchmark = SkillRoutingBenchmark().evaluate(((('safe-skill',), ranked, ('active-skill',)),))
        self.assertEqual(benchmark.status, "PASS")
        store.close()

    def test_temporal_client_contract_dag_budget_compensation_and_semantic_merge(self):
        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        first = ChildAgentContract("plan", "plan task", ("git:" + "a" * 40,), {"artifact": "plan"}, budget_micros=10)
        second = ChildAgentContract("code", "code task", ("artifact:plan",), {"artifact": "diff"}, dependencies=("plan",), workspace_strategy=WorkspaceStrategy.WORKTREE, budget_micros=20)
        plan = DagPlan.create(identity, 1, (first, second), "initial plan")
        client = FakeTemporalClient()
        orchestrator = TemporalDagOrchestrator(client, task_queue="elmos-agent")
        started = asyncio.run(orchestrator.start(plan, manifest_digest="sha256:" + "c" * 64, idempotency_key="start-a"))
        self.assertEqual(started.workflow_id, "elmos:tenant-a:project-a:task-a:run-a:root")
        self.assertEqual(asyncio.run(orchestrator.status(started.workflow_id))["phase"], "children")
        client.duplicate = True
        self.assertEqual(asyncio.run(orchestrator.start(plan, manifest_digest="sha256:" + "c" * 64, idempotency_key="start-a")), started)
        conflicting = DagPlan.create(identity, 1, (first, second), "conflicting duplicate")
        with self.assertRaises(ContractViolation):
            asyncio.run(orchestrator.start(conflicting, manifest_digest="sha256:" + "c" * 64, idempotency_key="start-a"))
        amended = DagPlan.create(identity, 2, (first, second), "operator refinement")
        asyncio.run(orchestrator.amend(started.workflow_id, amended, expected_version=1, actor="operator-a", idempotency_key="amend-a"))
        self.assertEqual(client.handle.updates[0][0], "amend_plan")
        self.assertEqual(client.handle.updates[0][2]["id"], "amend-a")
        asyncio.run(orchestrator.cancel(started.workflow_id, actor="operator-a", reason="test", idempotency_key="cancel-a"))
        self.assertFalse(client.handle.cancelled)
        self.assertEqual(client.handle.signals[-1][0], "request_cancel")

        control = DagControlStore()
        control.save_plan(plan, actor="planner-a")
        control.save_plan(plan, actor="planner-a")
        with self.assertRaises(TenantIsolationError):
            control.consume_budget(Identity("tenant-a", "project-b", "task-a", "run-a"), "plan", 1, global_limit_micros=30, idempotency_key="forged-budget")
        control.consume_budget(identity, "plan", 5, global_limit_micros=30, idempotency_key="budget-a")
        control.consume_budget(identity, "plan", 5, global_limit_micros=30, idempotency_key="budget-a")
        with self.assertRaises(BudgetExceeded):
            control.consume_budget(identity, "plan", 6, global_limit_micros=30, idempotency_key="budget-b")
        control.lock_resource(identity, "file:shared.py", "plan")
        with self.assertRaises(ContractViolation):
            control.lock_resource(identity, "file:shared.py", "code")
        self.assertEqual(control.register_compensation(identity, "plan", "undo", idempotency_key="compensate-plan"), 0)
        self.assertEqual(control.register_compensation(identity, "plan", "undo", idempotency_key="compensate-plan"), 0)
        self.assertEqual(control.compensate(identity, {"undo": lambda node, key: "receipt:" + node + ":" + key}), ("receipt:plan:compensate-plan",))
        self.assertEqual(control.compensate(identity, {"undo": lambda node, key: "receipt:" + node + ":" + key}), ())
        control.close()

        repository = FakeRepository()
        coordinator = SemanticMergeCoordinator(repository)
        blocked = coordinator.integrate(identity, base_revision="base", inputs=(MergeInput("a", "rev-a", "artifact:a"), MergeInput("b", "rev-b", "artifact:b")), resolve=None, verify=lambda _revision: True)
        self.assertEqual(blocked.status, "blocked")
        merged = coordinator.integrate(identity, base_revision="base", inputs=(MergeInput("a", "rev-a", "artifact:a"), MergeInput("b", "rev-b", "artifact:b")), resolve=lambda files, symbols, inputs: {"approved_by": "integrator", "changes": [*files, *symbols]}, verify=lambda revision: revision == "integrated-head")
        self.assertEqual(merged.status, "succeeded")


if __name__ == "__main__":
    unittest.main()
