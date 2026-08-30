import tempfile
import unittest
from pathlib import Path

from elmos_openhands.artifacts import ContentAddressedStore
from elmos_openhands.firewall import ActionFirewall
from elmos_openhands.ledger import EventLedger
from elmos_openhands.models import ExecutionManifest, Identity, Usage
from elmos_openhands.observability import CostMeter, MetricsRegistry
from elmos_openhands.providers import NativeAgentAdapter, ProviderResponse
from elmos_openhands.runtime import AgentRuntime
from elmos_openhands.service import RuntimeControlPlane
from elmos_openhands.tools import ToolGateway, ToolRegistry


class ObservabilityServiceTests(unittest.TestCase):
    def test_cost_meter_is_exact_and_reconciles_with_invoice(self):
        ledger = EventLedger()
        self.addCleanup(ledger.close)
        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        ledger.create_run(identity, "sha256:" + "a" * 64)
        meter = CostMeter(ledger)
        meter.record(identity, usage=Usage(cost_micros=100), unit="model-output", source="provider-a")
        self.assertEqual(meter.reconcile(identity, 100)["status"], "pass")
        self.assertEqual(meter.reconcile(identity, 102)["status"], "incident")

    def test_metrics_spans_and_service_event_cursor_are_available(self):
        metrics = MetricsRegistry()
        with metrics.span("agent.turn", {"tenant_id": "tenant-a"}) as span:
            span["event"] = "started"
        metrics.increment("turns", attributes={"tenant_id": "tenant-a"})
        self.assertEqual(metrics.snapshot()["turns{tenant_id=tenant-a}"], 1)
        with tempfile.TemporaryDirectory() as root:
            ledger = EventLedger(str(Path(root) / "ledger.sqlite"))
            self.addCleanup(ledger.close)
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            manifest = ExecutionManifest("commit", "policy", "native", "model")
            runtime = AgentRuntime(ledger, NativeAgentAdapter(decisions=[ProviderResponse(completion=__import__("elmos_openhands.models", fromlist=["CompletionProposal"]).CompletionProposal(identity.run_id, "proposed"))]), ToolGateway(ledger, ActionFirewall(), ToolRegistry(), ContentAddressedStore(Path(root) / "cas")))
            service = RuntimeControlPlane(ledger, runtime)
            service.create_run(identity, manifest)
            page = service.event_page(identity)
            self.assertTrue(page)
            self.assertEqual(service.health().certification, "NOT_CERTIFIED")


if __name__ == "__main__":
    unittest.main()
