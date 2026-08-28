import base64
import hashlib
import hmac
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from elmos_openhands.artifacts import ContentAddressedStore
from elmos_openhands.browser import BrowserAllowlistEntry, BrowserEvidencePolicy, BrowserEvidenceRunner, BrowserScenario, BrowserStep
from elmos_openhands.browser_drivers import BrowserMatrixRunner, BrowserProfile
from elmos_openhands.errors import ContractViolation, LeaseLost, TenantIsolationError
from elmos_openhands.evidence import EvidenceItem, EvidencePackBuilder, EvidenceRepository, EvidenceTrustStore, IndependentEvidenceVerifier, SignatureEnvelope, TrustKey
from elmos_openhands.models import Identity, new_id
from elmos_openhands.provider_sessions import HttpJsonSseTransport, ProviderSessionManager, ProviderTransportError, codex_session_adapter
from elmos_openhands.providers import ProviderRequest
from elmos_openhands.qualification import CampaignOutput, CampaignType, QualificationRunner, QualificationStore, default_production_qualification_plan


class FakeSessionTransport:
    def __init__(self):
        self.calls = []

    def request(self, provider, operation, payload):
        self.calls.append((provider, operation, dict(payload)))
        if operation == "sessions/start":
            return {"session_id": "remote-" + str(payload["idempotency_key"])}
        if operation == "sessions/checkpoint":
            return {"cursor": "checkpoint-a"}
        if operation == "sessions/resume":
            return {"session_id": "remote-resumed"}
        if operation == "sessions/cancel":
            return {"status": "cancelled"}
        if operation == "sessions/usage":
            return {"usage": {"input_tokens": 3, "output_tokens": 1, "cost_micros": 7}}
        raise AssertionError(operation)

    def stream(self, provider, operation, payload):
        self.calls.append((provider, operation, dict(payload)))
        sequence = int(payload["after_sequence"]) + 1
        yield {
            "sequence": sequence,
            "type": "message.delta",
            "payload": {"text": f"part-{sequence}"},
            "usage": {"input_tokens": 1, "output_tokens": 0, "cost_micros": 2},
        }


class TerminalSessionTransport(FakeSessionTransport):
    def stream(self, provider, operation, payload):
        self.calls.append((provider, operation, dict(payload)))
        yield {"sequence": int(payload["after_sequence"]) + 1, "type": "done", "payload": {"finish_reason": "stop"}, "terminal": True}


class InvalidTerminalOrderTransport(FakeSessionTransport):
    def stream(self, provider, operation, payload):
        sequence = int(payload["after_sequence"]) + 1
        yield {"sequence": sequence, "type": "done", "payload": {}, "terminal": True}
        yield {"sequence": sequence + 1, "type": "ping", "payload": {}, "terminal": False}


class FakeHttpResponse:
    def __init__(self, data, url):
        self.data = data
        self.url = url
        self.closed = False

    def read(self, limit=-1):
        return self.data if limit < 0 else self.data[:limit]

    def geturl(self):
        return self.url

    def close(self):
        self.closed = True

    def __iter__(self):
        return iter(self.data.splitlines(keepends=True))


class FakeHttpOpener:
    def __init__(self, responses):
        self.responses = list(responses)

    def open(self, request, timeout):
        return self.responses.pop(0)


class FakeBrowser:
    def __init__(self, ok):
        self.ok = ok

    def execute(self, step):
        return {"ok": self.ok, "locator_resolution": {"locator": step.locator, "strategy": "role"}}

    def capture(self):
        return {"dom.html": "<html>ok</html>"}


class EvidenceBrowser:
    def __init__(self, *, privacy=True):
        self.privacy = privacy

    def execute(self, step):
        return {"ok": True, "console_errors": ["known-widget-error"], "locator_resolution": {"locator": step.locator, "strategy": "role"}}

    def capture(self):
        evidence = {"screenshot.png": b"\x89PNG\r\n\x1a\n\xffbinary", "dom.html": "token=secret-a user@example.com"}
        if self.privacy:
            evidence["privacy.json"] = '{"status":"APPLIED"}'
        return evidence


class FakeSigner:
    algorithm = "Ed25519"

    def __init__(self, key_id, actor_id, secret):
        self.key_id, self.actor_id, self.secret = key_id, actor_id, secret

    def sign(self, payload):
        value = hmac.new(self.secret, payload, hashlib.sha256).digest()
        return SignatureEnvelope(self.algorithm, self.key_id, base64.b64encode(value).decode("ascii"))


class FakeCampaignExecutor:
    executor_id = "external-executor"
    independent = False

    def execute(self, campaign_type, target, authorization_ref):
        return CampaignOutput("PASS", {"raw-log": b"real-run-placeholder-for-unit-test"}, {"requests": 10})


class ProviderBrowserEvidenceQualificationTests(unittest.TestCase):
    def test_provider_http_transport_blocks_unsafe_endpoints_redirects_and_unbounded_payloads(self):
        identity_payload = {"identity": {"tenant_id": "tenant-a", "project_id": "project-a", "task_id": "task-a", "run_id": "run-a", "node_id": "root", "agent_id": None}}
        with self.assertRaises(ContractViolation):
            HttpJsonSseTransport({"codex": "https://user:secret@provider.invalid"}, lambda provider, identity, operation: "token")
        oversized = FakeHttpResponse(b"{" + b"x" * 2048, "https://provider.invalid/sessions/start")
        bounded = HttpJsonSseTransport(
            {"codex": "https://provider.invalid"},
            lambda provider, identity, operation: "token",
            max_response_bytes=1024,
            opener=FakeHttpOpener((oversized,)),
        )
        with self.assertRaises(ContractViolation):
            bounded.request("codex", "sessions/start", identity_payload)
        redirected = HttpJsonSseTransport(
            {"codex": "https://provider.invalid"},
            lambda provider, identity, operation: "token",
            opener=FakeHttpOpener((FakeHttpResponse(b"{}", "https://attacker.invalid/capture"),)),
        )
        with self.assertRaises(ProviderTransportError):
            redirected.request("codex", "sessions/start", identity_payload)
        with self.assertRaises(ContractViolation):
            redirected.request("codex", "../admin", identity_payload)

    def test_provider_session_lifecycle_is_durable_idempotent_and_usage_reconciles(self):
        transport = FakeSessionTransport()
        manager = ProviderSessionManager((codex_session_adapter(transport),))
        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        start_request = ProviderRequest(identity, "model-a", {}, idempotency_key="start-a")
        session = manager.start("codex", start_request, region="local")
        self.assertEqual(manager.start("codex", start_request, region="local").session_id, session.session_id)
        self.assertEqual(sum(call[1] == "sessions/start" for call in transport.calls), 1)

        first = ProviderRequest(identity, "model-a", {"turn": 1}, idempotency_key="send-a")
        self.assertEqual(manager.send(session, first)[0].sequence, 0)
        self.assertEqual(manager.send(session, first)[0].sequence, 0)
        second = ProviderRequest(identity, "model-a", {"turn": 2}, idempotency_key="send-b")
        self.assertEqual(manager.send(session, second)[0].sequence, 1)
        self.assertEqual(manager.recorded_usage(session).input_tokens, 2)
        forged = replace(session, identity=Identity("tenant-a", "project-b", "task-a", "run-a"))
        with self.assertRaises(TenantIsolationError):
            manager.recorded_usage(forged)

        checkpoint = manager.checkpoint(session, manifest_digest="sha256:" + "a" * 64, idempotency_key="checkpoint-a")
        self.assertEqual(manager.checkpoint(session, manifest_digest="sha256:" + "a" * 64, idempotency_key="checkpoint-a").digest, checkpoint.digest)
        resumed = manager.resume(identity, checkpoint, model="model-a", region="local", idempotency_key="resume-a")
        self.assertEqual(manager.resume(identity, checkpoint, model="model-a", region="local", idempotency_key="resume-a").session_id, resumed.session_id)
        manager.cancel(resumed, "test complete", idempotency_key="cancel-a")
        manager.cancel(resumed, "test complete", idempotency_key="cancel-a")
        self.assertEqual(manager.usage(session).cost_micros, 7)
        manager.close()

    def test_terminal_provider_replays_exact_operation_without_leaking_pending_journal_rows(self):
        transport = TerminalSessionTransport()
        manager = ProviderSessionManager((codex_session_adapter(transport),))
        identity = Identity("tenant-a", "project-a", "task-a", "run-terminal")
        session = manager.start("codex", ProviderRequest(identity, "model-a", {}, idempotency_key="start-terminal"), region="local")
        request = ProviderRequest(identity, "model-a", {"turn": 1}, idempotency_key="send-terminal")
        first = manager.send(session, request)
        self.assertTrue(first[0].terminal)
        self.assertEqual(manager.send(session, request), first)
        with self.assertRaises(LeaseLost):
            manager.send(session, ProviderRequest(identity, "model-a", {"turn": 2}, idempotency_key="send-after-terminal"))
        journal_rows = manager._connection.execute("SELECT COUNT(*) FROM provider_operations WHERE operation='send'").fetchone()[0]
        self.assertEqual(journal_rows, 1)
        manager.close()

        invalid_manager = ProviderSessionManager((codex_session_adapter(InvalidTerminalOrderTransport()),))
        invalid_session = invalid_manager.start(
            "codex",
            ProviderRequest(identity, "model-a", {}, idempotency_key="start-invalid-terminal"),
            region="local",
        )
        with self.assertRaises(ContractViolation):
            invalid_manager.send(
                invalid_session,
                ProviderRequest(identity, "model-a", {"turn": 1}, idempotency_key="send-invalid-terminal"),
            )
        invalid_manager.close()

    def test_browser_matrix_blocks_flaky_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = ContentAddressedStore(Path(temporary) / "cas")
            runner = BrowserMatrixRunner(BrowserEvidenceRunner(artifacts), attempts=2)
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            scenario = BrowserScenario("scenario-a", "flaky", (), (BrowserStep("click", locator="role=button|Save"),))
            outcomes = iter((False, True))
            result = runner.run(identity, scenario, (BrowserProfile("desktop"),), lambda _profile: FakeBrowser(next(outcomes)))
            self.assertEqual(result.classification, "FLAKY_BLOCKED")
            self.assertEqual(result.certification, "NOT_CERTIFIED")

    def test_browser_evidence_preserves_binary_redacts_text_and_requires_privacy_attestation(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = ContentAddressedStore(Path(temporary) / "cas")
            policy = BrowserEvidencePolicy((BrowserAllowlistEntry("console_error", "known-widget-error", time.time() + 60, "security-a", "bounded known issue"),))
            runner = BrowserEvidenceRunner(artifacts, secret_values=("secret-a",), pii_patterns=(r"[\w.+-]+@[\w.-]+",), policy=policy)
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            scenario = BrowserScenario("scenario-evidence", "evidence", (), (BrowserStep("click", locator="role=button|Save"),))
            evidence = runner.run(identity, scenario, EvidenceBrowser())
            self.assertEqual(evidence.status, "pass")
            self.assertEqual(evidence.allowlisted_findings, ("console_error:known-widget-error",))
            stored = {reference.kind: artifacts.get("tenant-a", reference) for reference in evidence.artifact_refs}
            self.assertEqual(stored["browser-screenshot.png"], b"\x89PNG\r\n\x1a\n\xffbinary")
            self.assertNotIn(b"secret-a", stored["browser-dom.html"])
            self.assertNotIn(b"user@example.com", stored["browser-dom.html"])

            sensitive = BrowserScenario("scenario-sensitive", "sensitive", (), (BrowserStep("fill", locator="label=Password", value="secret-a", sensitive=True),))
            self.assertEqual(runner.run(identity, sensitive, EvidenceBrowser(privacy=False)).status, "error")
            expired_runner = BrowserEvidenceRunner(artifacts, policy=BrowserEvidencePolicy((BrowserAllowlistEntry("console_error", "known-widget-error", time.time() - 1, "security-a", "expired"),)))
            self.assertEqual(expired_runner.run(identity, scenario, EvidenceBrowser()).status, "fail")

    def test_signed_evidence_requires_separate_trusted_verifier_and_tenant_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = ContentAddressedStore(Path(temporary) / "cas")
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            producer = FakeSigner("producer-key", "producer", b"producer-secret")
            verifier = FakeSigner("verifier-key", "independent", b"verifier-secret")
            trust = EvidenceTrustStore(
                (
                    TrustKey("producer-key", "producer", "producer", "Ed25519", lambda payload, signature: hmac.compare_digest(signature, hmac.new(b"producer-secret", payload, hashlib.sha256).digest())),
                    TrustKey("verifier-key", "independent", "independent_verifier", "Ed25519", lambda payload, signature: hmac.compare_digest(signature, hmac.new(b"verifier-secret", payload, hashlib.sha256).digest())),
                )
            )
            artifact = artifacts.put("tenant-a", b"raw-evidence", kind="test-log")
            item = EvidenceItem(new_id(), "test-log", "PASS", artifact, "unit", "executor", "sha256:" + "e" * 64, ("runner", "--case", "case-a"))
            pack = EvidencePackBuilder(producer).build(identity, manifest_digest="sha256:" + "a" * 64, target_digest="sha256:" + "b" * 64, items=(item,))
            verification = IndependentEvidenceVerifier(trust, verifier, artifacts.get).verify(pack, expected_manifest=pack.manifest_digest, expected_target=pack.target_digest)
            self.assertEqual(verification.decision, "VERIFIED")
            repository = EvidenceRepository()
            repository.put_pack(pack)
            repository.put_verification(identity, verification)
            with self.assertRaises(TenantIsolationError):
                repository.put_verification(Identity("tenant-a", "project-b", "task-a", "run-a"), verification)
            repository.close()

    def test_qualification_defaults_to_not_run_and_never_self_certifies(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = ContentAddressedStore(Path(temporary) / "cas")
            store = QualificationStore()
            runner = QualificationRunner(store, artifacts)
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            with self.assertRaises(ContractViolation):
                default_production_qualification_plan("sha256:" + "a" * 64, "sha256:" + "0" * 64)
            plan = default_production_qualification_plan("sha256:" + "a" * 64, "sha256:" + "b" * 64)
            for campaign, target in plan.items():
                runner.not_run(identity, campaign, target, "external environment has not executed")
            self.assertTrue(all(value == "NOT_RUN" for value in store.statuses(identity).values()))

            output = runner.run(
                identity,
                CampaignType.LOAD,
                plan[CampaignType.LOAD],
                authorization_ref="authorization-a",
                executor=FakeCampaignExecutor(),
                independent_verifier=lambda _output: ("independent-verifier", "VERIFIED", ()),
                replay_command=("load-runner", "--plan", "frozen-a"),
            )
            self.assertEqual(output.decision, "READY_FOR_EXTERNAL_GATE")
            self.assertEqual(output.as_dict()["certification"], "NOT_CERTIFIED")
            forged = Identity("tenant-a", "project-b", "task-a", "run-a")
            self.assertTrue(all(value == "NOT_RUN" for value in store.statuses(forged).values()))
            store.close()


if __name__ == "__main__":
    unittest.main()
