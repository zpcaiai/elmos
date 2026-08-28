import unittest

from elmos_openhands.dag import DurableAgentDag
from elmos_openhands.errors import ContractViolation, LeaseLost, NotConfigured, TenantIsolationError
from elmos_openhands.models import Identity
from elmos_openhands.packages import CapabilityPackageRegistry, HmacPackageSigner
from elmos_openhands.providers import CodexCompatibleAdapter, ProviderRequest, ProviderRouter, RouteConstraints, normalize_provider_response


class PackagesDagProviderTests(unittest.TestCase):
    def test_signed_package_lifecycle_and_revocation(self):
        signer = HmacPackageSigner({"publisher-a": b"test-key"})
        registry = CapabilityPackageRegistry(signer=signer)
        self.addCleanup(registry.close)
        manifest = {"name": "skill-a", "version": "1.0.0", "publisher": "publisher-a", "permissions": ["workspace.read"], "dependencies": [], "files": [{"path": "sha256:" + "a" * 64}]}
        package = registry.publish(manifest, trust_level="trusted")
        registry.install(package)
        registry.activate("tenant-a", package.name, package.version)
        self.assertEqual(registry.pin_for_run("tenant-a", "skill-a").digest, package.digest)
        registry.revoke(package.name, package.version, "security issue")
        with self.assertRaises(ContractViolation):
            registry.pin_for_run("tenant-a", "skill-a")

    def test_untrusted_package_cannot_be_activated(self):
        signer = HmacPackageSigner({"publisher-a": b"test-key"})
        registry = CapabilityPackageRegistry(signer=signer)
        self.addCleanup(registry.close)
        manifest = {"name": "skill-b", "version": "1.0.0", "publisher": "publisher-a", "permissions": [], "dependencies": [], "files": [{"path": "sha256:" + "b" * 64}]}
        package = registry.publish(manifest)
        registry.install(package)
        with self.assertRaises(ContractViolation):
            registry.activate("tenant-a", package.name, package.version)

    def test_package_approval_and_deprecation_are_explicit_lifecycle_states(self):
        signer = HmacPackageSigner({"publisher-a": b"test-key"})
        registry = CapabilityPackageRegistry(signer=signer)
        self.addCleanup(registry.close)
        manifest = {"name": "skill-c", "version": "1.0.0", "publisher": "publisher-a", "permissions": [], "dependencies": [], "files": [{"path": "sha256:" + "c" * 64}]}
        package = registry.publish(manifest)
        registry.install(package)
        approved = registry.approve(package.name, package.version, "security-reviewer")
        self.assertEqual(approved.trust_level, "verified")
        registry.activate("tenant-a", package.name, package.version)
        registry.deprecate(package.name, package.version, "superseded")
        self.assertEqual(registry.pin_for_run("tenant-a", package.name).version, package.version)

    def test_dag_fanout_fanin_and_fencing(self):
        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        dag = DurableAgentDag()
        self.addCleanup(dag.close)
        dag.add(identity, "plan")
        self.assertEqual(dag.add(identity, "plan").node_id, "plan")
        dag.add(identity, "left", ("plan",), budget_micros=10)
        dag.add(identity, "right", ("plan",), budget_micros=10)
        with self.assertRaises(TenantIsolationError):
            dag.get(Identity("tenant-a", "project-b", "task-a", "run-a"), "plan")
        plan_claim = dag.claim(identity, "plan", "planner")
        self.assertEqual(dag.claim(identity, "plan", "planner").fencing_token, plan_claim.fencing_token)
        plan_result = dag.complete(identity, "plan", "planner", plan_claim.fencing_token, "artifact-plan")
        self.assertEqual(dag.complete(identity, "plan", "planner", plan_claim.fencing_token, "artifact-plan"), plan_result)
        ready = dag.ready(identity)
        self.assertEqual({node.node_id for node in ready}, {"left", "right"})
        left_claim = dag.claim(identity, "left", "worker-a")
        with self.assertRaises(LeaseLost):
            dag.complete(identity, "left", "worker-b", left_claim.fencing_token, "artifact-left")
        dag.complete(identity, "left", "worker-a", left_claim.fencing_token, "artifact-left")
        right_claim = dag.claim(identity, "right", "worker-a")
        dag.complete(identity, "right", "worker-a", right_claim.fencing_token, "artifact-right")
        self.assertEqual({node.node_id for node in dag.ready(identity)}, set())
        dag.add(identity, "cycle-a")
        dag.add(identity, "cycle-b", ("cycle-a",))
        with self.assertRaises(ContractViolation):
            dag.amend(identity, "cycle-a", depends_on=("cycle-b",))
        dag.add(identity, "removable")
        dag.remove(identity, "removable", "planner revision")
        dag.remove(identity, "removable", "planner revision replay")
        with self.assertRaises(KeyError):
            dag.get(identity, "removable")

    def test_external_adapters_normalize_and_router_fails_closed(self):
        def transport(provider, request):
            self.assertEqual(provider, "codex-compatible")
            self.assertEqual(request["tenant_id"], "tenant-a")
            return {"kind": "completion", "summary": "proposed", "status": "succeeded", "usage": {"output_tokens": 2}}

        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        adapter = CodexCompatibleAdapter(transport)
        response = adapter.decide(ProviderRequest(identity, "model", {"text": "context"}))
        self.assertEqual(response.completion.summary, "proposed")
        self.assertIs(adapter, ProviderRouter([adapter]).choose(RouteConstraints(allowed_providers=frozenset({"codex-compatible"}))))
        with self.assertRaises(NotConfigured):
            ProviderRouter([adapter]).choose(RouteConstraints(allowed_providers=frozenset({"missing"})))

    def test_provider_failure_falls_back_to_compatible_adapter(self):
        class Broken:
            capabilities = type("Capabilities", (), {"provider": "broken", "regions": frozenset({"local"}), "supports_checkpoints": True})()

            def decide(self, request):
                raise RuntimeError("provider down")

        class Healthy:
            capabilities = type("Capabilities", (), {"provider": "healthy", "regions": frozenset({"local"}), "supports_checkpoints": True})()

            def decide(self, request):
                return normalize_provider_response({"kind": "completion", "summary": "ok", "usage": {}}, request.identity)

        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        response = ProviderRouter([Broken(), Healthy()]).call(ProviderRequest(identity, "model", {}), RouteConstraints())
        self.assertEqual(response.completion.summary, "ok")

    def test_provider_router_enforces_cost_ceiling(self):
        def expensive(provider, request):
            return {"kind": "completion", "summary": "too expensive", "usage": {"cost_micros": 2}}

        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        adapter = CodexCompatibleAdapter(expensive)
        with self.assertRaises(ContractViolation):
            ProviderRouter([adapter]).call(ProviderRequest(identity, "model", {}), RouteConstraints(max_cost_micros=1))


if __name__ == "__main__":
    unittest.main()
