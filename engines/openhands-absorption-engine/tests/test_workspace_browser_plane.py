import tempfile
import unittest
from pathlib import Path

from elmos_openhands.artifacts import ContentAddressedStore
from elmos_openhands.browser import BrowserEvidenceRunner, BrowserScenario, BrowserStep
from elmos_openhands.errors import ContractViolation, NotConfigured
from elmos_openhands.models import Identity
from elmos_openhands.plane import AdmissionController, WorkerRegistry
from elmos_openhands.workspace import ContainerSandboxProvider, IsolationClass, LocalWorkspaceProvider, WorkspaceRequest


class FakeBrowser:
    def execute(self, step):
        return {"ok": True, "locator_resolution": {"requested": step.locator, "resolved_by": "role"}}

    def capture(self):
        return {"screenshot": b"token=secret-value", "console": ""}


class WorkspaceBrowserPlaneTests(unittest.TestCase):
    def test_snapshot_restore_is_digest_bound_and_rejects_links(self):
        with tempfile.TemporaryDirectory() as root:
            artifacts = ContentAddressedStore(Path(root) / "cas")
            provider = LocalWorkspaceProvider(Path(root) / "workspaces", artifacts)
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            lease = provider.activate(provider.allocate(WorkspaceRequest(identity)))
            result = Path(lease.root) / "out" / "result.txt"
            result.write_text("before")
            snapshot = provider.snapshot(lease)
            result.write_text("after")
            provider.restore(lease, snapshot)
            self.assertEqual(result.read_text(), "before")
            foreign = ContentAddressedStore(Path(root) / "foreign").put("tenant-b", b"data")
            with self.assertRaises(Exception):
                provider.restore(lease, foreign)

    def test_workspace_lease_survives_provider_restart(self):
        with tempfile.TemporaryDirectory() as root:
            artifacts = ContentAddressedStore(Path(root) / "cas")
            workspace_root = Path(root) / "workspaces"
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            provider = LocalWorkspaceProvider(workspace_root, artifacts)
            lease = provider.activate(provider.allocate(WorkspaceRequest(identity), now=1), now=2)
            provider.close()
            restarted = LocalWorkspaceProvider(workspace_root, artifacts)
            renewed = restarted.heartbeat(lease, now=3)
            self.assertEqual(renewed.workspace_id, lease.workspace_id)
            restarted.close()

    def test_container_provider_is_hardened_and_local_provider_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            artifacts = ContentAddressedStore(Path(root) / "cas")
            provider = LocalWorkspaceProvider(Path(root) / "workspaces", artifacts)
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            with self.assertRaises(NotConfigured):
                provider.allocate(WorkspaceRequest(identity, isolation_class=IsolationClass.L2, image_digest="sha256:" + "a" * 64))
            lease = type("Lease", (), {"root": str(Path(root) / "tenant-a"), "isolation_class": IsolationClass.L2})()
            command = ContainerSandboxProvider().build_command(lease, "sha256:" + "a" * 64, ["pytest"])
            self.assertIn("--network=none", command)
            self.assertIn("--cap-drop=ALL", command)

    def test_browser_evidence_masks_secrets_and_worker_plane_enforces_quotas(self):
        with tempfile.TemporaryDirectory() as root:
            artifacts = ContentAddressedStore(Path(root) / "cas")
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            scenario = BrowserScenario("s1", "login", (), (BrowserStep("navigate", value="https://example.test"), BrowserStep("click", locator="role=button[name=Submit]")))
            evidence = BrowserEvidenceRunner(artifacts, secret_values=("secret-value",)).run(identity, scenario, FakeBrowser(), trace_id="trace-1")
            self.assertEqual(evidence.status, "pass")
            self.assertNotIn(b"secret-value", artifacts.get("tenant-a", evidence.artifact_refs[0]))
            workers = WorkerRegistry()
            workers.register("worker-a", "local", ["browser"], now=1)
            self.assertEqual(workers.choose(region="local", required_capabilities=["browser"], now=2).worker_id, "worker-a")
            admission = AdmissionController({"tenant-a": 1})
            admission.admit("tenant-a")
            with self.assertRaises(ContractViolation):
                admission.admit("tenant-a")
            admission.release("tenant-a")

    def test_browser_cleanup_runs_after_a_failed_step(self):
        class FailingBrowser(FakeBrowser):
            def __init__(self):
                self.operations = []

            def execute(self, step):
                self.operations.append(step.operation)
                return {"ok": step.operation != "click"}

        with tempfile.TemporaryDirectory() as root:
            artifacts = ContentAddressedStore(Path(root) / "cas")
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            driver = FailingBrowser()
            scenario = BrowserScenario("s2", "failure", (), (BrowserStep("click", locator="role=button"),), (BrowserStep("wait", value="1"),))
            evidence = BrowserEvidenceRunner(artifacts).run(identity, scenario, driver)
            self.assertEqual(evidence.status, "fail")
            self.assertEqual(driver.operations, ["click", "wait"])


if __name__ == "__main__":
    unittest.main()
