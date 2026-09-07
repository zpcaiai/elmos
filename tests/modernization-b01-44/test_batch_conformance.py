#!/usr/bin/env python3
"""Executable conformance suite for every Batch 01-44 package.

Each package declares twelve obligations in ``tests/test_catalog.json``.  This
module turns each of them into a real test that drives the runtime and asserts
the *specific* refusal - not merely "an exception happened".  44 batches x 12
cases = 528 executing tests; every one of them fails if the corresponding
enforcement is removed from ``scripts/modernization_b01_44``.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.modernization_b01_44.approval import ApprovalLedger  # noqa: E402
from scripts.modernization_b01_44.canonical import digest, format_instant  # noqa: E402
from scripts.modernization_b01_44.certification import Certificate  # noqa: E402
from scripts.modernization_b01_44.corpus import Budget, CorpusCase  # noqa: E402
from scripts.modernization_b01_44.errors import (  # noqa: E402
    AgentBoundaryViolation,
    CertificationBlocked,
    ProviderDrift,
    TenantIsolationViolation,
    TrustBoundaryViolation,
    UpstreamCertificateMissing,
)
from scripts.modernization_b01_44.evidence import make_evidence  # noqa: E402
from scripts.modernization_b01_44.orchestrator import (  # noqa: E402
    BatchExecutor,
    Platform,
    default_platform,
    standard_corpus,
)
from scripts.modernization_b01_44.packages import load_registry  # noqa: E402
from scripts.modernization_b01_44.policy import Principal  # noqa: E402

NOW = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
REGISTRY = load_registry()
ASSETS = ["alpha", "beta", "gamma"]
SCOPE = "svc-conformance"


def fresh_platform() -> Platform:
    """A platform sharing the immutable registry but nothing mutable."""

    return Platform(registry=REGISTRY)


def seed_upstream(platform: Platform, batch: int, *, status: str = "certified") -> str:
    """Install a valid Batch N-1 certificate so Batch N may run."""

    if batch <= 1:
        return "genesis"
    certificate = Certificate(
        certificate_id=f"cert-seed-b{batch - 1:02d}",
        batch=batch - 1,
        status=status,
        scope=SCOPE,
        input_digests=("0" * 64,),
        evidence_refs=(),
        issued_at=format_instant(NOW - timedelta(days=1)),
        expires_at=format_instant(NOW + timedelta(days=30)),
        limitations=(),
    )
    platform.seed_certificate(certificate)
    return certificate.certificate_id


def make_request(batch: int, upstream_ref: str, **overrides) -> dict:
    request = {
        "request_id": f"req-b{batch:02d}",
        "tenant_id": "tenant-a",
        "project_id": "proj-1",
        "scope": SCOPE,
        "upstream_certificate_refs": [upstream_ref],
        "options": {"assets": list(ASSETS)},
    }
    request.update(overrides)
    return request


def work(unit: dict) -> dict:
    if "unit_id" not in unit:
        raise TrustBoundaryViolation("work unit is not addressable", keys=sorted(unit))
    return {"unit_id": unit["unit_id"], "result": "analysed"}


class BatchConformance(unittest.TestCase):
    """Base class; one subclass is generated per batch."""

    batch: int = 0

    # -- helpers ---------------------------------------------------------

    def run_ok(self, platform: Platform, batch: int, **kwargs):
        upstream = seed_upstream(platform, batch)
        executor = BatchExecutor(platform, batch)
        return executor.execute(
            make_request(batch, upstream),
            principal=Principal("u-1", "tenant-a", "human"),
            now=NOW,
            transform=work,
            corpus=standard_corpus(SCOPE, assets=ASSETS),
            **kwargs,
        )

    # -- T001 ------------------------------------------------------------

    def test_T001_schema_valid(self):
        """Valid input runs and both projections satisfy their schemas."""

        platform = fresh_platform()
        result = self.run_ok(platform, self.batch)
        self.assertIn(result.status, ("completed", "partial"))
        self.assertTrue(result.certificate)
        self.assertEqual(result.certificate.batch, self.batch)
        # as_output()/certificate are schema validated inside execute(); assert
        # the substance the schema cannot: evidence really was produced.
        self.assertGreaterEqual(len(result.evidence_refs), 2)
        self.assertTrue(result.output_digest)

    # -- T002 ------------------------------------------------------------

    def test_T002_schema_invalid_unknown_field(self):
        """An unmodelled top-level field is refused at the trust boundary."""

        platform = fresh_platform()
        upstream = seed_upstream(platform, self.batch)
        request = make_request(self.batch, upstream)
        request["injected_field"] = "should-not-be-accepted"
        with self.assertRaises(TrustBoundaryViolation) as ctx:
            BatchExecutor(platform, self.batch).execute(
                request, principal=Principal("u-1", "tenant-a", "human"), now=NOW
            )
        self.assertEqual(ctx.exception.code, "trust-boundary-violation")

    # -- T003 ------------------------------------------------------------

    def test_T003_missing_upstream_certificate(self):
        """Batch N refuses to run without a valid Batch N-1 certificate."""

        platform = fresh_platform()
        if self.batch == 1:
            # Batch 01 is the chain root: it must still refuse an empty ref list.
            request = make_request(1, "genesis")
            request["upstream_certificate_refs"] = []
            with self.assertRaises(TrustBoundaryViolation):
                BatchExecutor(platform, 1).execute(
                    request, principal=Principal("u-1", "tenant-a", "human"), now=NOW
                )
            return
        request = make_request(self.batch, "cert-that-was-never-issued")
        with self.assertRaises(UpstreamCertificateMissing):
            BatchExecutor(platform, self.batch).execute(
                request, principal=Principal("u-1", "tenant-a", "human"), now=NOW
            )

    # -- T004 ------------------------------------------------------------

    def test_T004_fake_certified_status(self):
        """Asking for 'certified' without holdout evidence cannot grant it."""

        platform = fresh_platform()
        result = self.run_ok(platform, self.batch, requested_status="certified")
        self.assertNotEqual(
            result.certificate.status,
            "certified",
            "gate granted 'certified' without independent review evidence",
        )
        self.assertTrue(result.decision.downgraded)
        self.assertIn("missing-evidence", result.decision.reasons)

    def test_T004b_status_field_edit_does_not_upgrade(self):
        """Editing only the requested status never changes what is granted."""

        low = fresh_platform()
        high = fresh_platform()
        a = self.run_ok(low, self.batch, requested_status="limited")
        b = self.run_ok(high, self.batch, requested_status="certified")
        self.assertEqual(a.certificate.status, b.certificate.status)

    # -- T005 ------------------------------------------------------------

    def test_T005_cross_tenant_access(self):
        """A principal from another tenant is denied and the denial is audited."""

        platform = fresh_platform()
        upstream = seed_upstream(platform, self.batch)
        request = make_request(self.batch, upstream)
        intruder = Principal("u-evil", "tenant-b", "human")
        with self.assertRaises(TenantIsolationViolation):
            BatchExecutor(platform, self.batch).execute(request, principal=intruder, now=NOW)
        audit = platform.policy(self.batch).audit_log
        self.assertTrue(
            any(r.decision == "deny" and r.reason == "cross-tenant" for r in audit),
            "cross-tenant denial was not audited",
        )

    # -- T006 ------------------------------------------------------------

    def test_T006_agent_modifies_tests(self):
        """An agent proposing a change to tests/golden/gate is rejected."""

        policy = fresh_platform().policy(self.batch)
        agent = Principal("agent-1", "tenant-a", "agent")
        for artefact in ("tests", "golden", "gate", "certificate", "policy"):
            with self.assertRaises(AgentBoundaryViolation, msg=f"{artefact} was writable"):
                policy.check_agent_write(agent, artefact, mode="propose")

    def test_T006b_agent_cannot_commit_or_self_approve(self):
        policy = fresh_platform().policy(self.batch)
        agent = Principal("agent-1", "tenant-a", "agent")
        with self.assertRaises(AgentBoundaryViolation):
            policy.check_agent_write(agent, "artifact", mode="commit")
        with self.assertRaises(AgentBoundaryViolation):
            policy.check_agent_write(agent, "artifact", mode="approve")

    # -- T007 ------------------------------------------------------------

    def test_T007_provider_version_drift(self):
        """A major-version change in a pinned provider blocks execution."""

        platform = fresh_platform()
        pin = platform.adapters.register(
            "prov-x", "1.4.0", contract={"ops": ["build"]}, capabilities=["build"]
        ).pin()
        upstream = seed_upstream(platform, self.batch)
        # Same version: no drift, execution proceeds.
        BatchExecutor(platform, self.batch).execute(
            make_request(self.batch, upstream),
            principal=Principal("u-1", "tenant-a", "human"),
            now=NOW,
            transform=work,
            provider_pins=[pin],
        )
        # Provider upgraded underneath us.
        platform.adapters.register("prov-x", "2.0.0", contract={"ops": ["build"]}, capabilities=["build"])
        with self.assertRaises(ProviderDrift):
            BatchExecutor(platform, self.batch).execute(
                make_request(self.batch, upstream, request_id="req-drift"),
                principal=Principal("u-1", "tenant-a", "human"),
                now=NOW,
                transform=work,
                provider_pins=[pin],
            )

    # -- T008 ------------------------------------------------------------

    def test_T008_duplicate_event(self):
        """Delivering the same event twice produces exactly one effect."""

        platform = fresh_platform()
        run, created = platform.workflows.start(
            definition_version=f"b{self.batch:02d}.v1",
            tenant_id="tenant-a",
            project_id="proj-1",
            request={"batch": self.batch},
            now=NOW,
        )
        self.assertTrue(created)
        effects: list[str] = []
        handler = lambda _run: effects.append("applied")  # noqa: E731
        _, first = platform.workflows.apply_event(run, event_id="evt-1", handler=handler, now=NOW)
        _, second = platform.workflows.apply_event(run, event_id="evt-1", handler=handler, now=NOW)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(len(effects), 1)

    def test_T008b_duplicate_start_is_idempotent(self):
        platform = fresh_platform()
        request = {"batch": self.batch, "scope": SCOPE}
        first, created_a = platform.workflows.start(
            definition_version="v1", tenant_id="tenant-a", project_id="p", request=request, now=NOW
        )
        second, created_b = platform.workflows.start(
            definition_version="v1", tenant_id="tenant-a", project_id="p", request=request, now=NOW
        )
        self.assertTrue(created_a)
        self.assertFalse(created_b)
        self.assertEqual(first.workflow_id, second.workflow_id)
        self.assertEqual(len(platform.workflows), 1)

    # -- T009 ------------------------------------------------------------

    def test_T009_runner_disconnect(self):
        """An expired lease moves the run into reconciling, not into loss."""

        platform = fresh_platform()
        run, _ = platform.workflows.start(
            definition_version="v1",
            tenant_id="tenant-a",
            project_id="p",
            request={"batch": self.batch},
            now=NOW,
        )
        platform.workflows.transition(run, "running", now=NOW)
        platform.workflows.acquire_lease(run, "runner-1", NOW)
        self.assertEqual(platform.workflows.reap_expired_leases(NOW), [])
        later = NOW + timedelta(minutes=30)
        reaped = platform.workflows.reap_expired_leases(later)
        self.assertIn(run.workflow_id, reaped)
        self.assertEqual(run.state, "reconciling")

    # -- T010 ------------------------------------------------------------

    def test_T010_rollback_recovery(self):
        """Failure runs compensations newest-first and reaches 'compensated'."""

        platform = fresh_platform()
        run, _ = platform.workflows.start(
            definition_version="v1",
            tenant_id="tenant-a",
            project_id="p",
            request={"batch": self.batch},
            now=NOW,
        )
        platform.workflows.transition(run, "running", now=NOW)
        undone: list[str] = []
        platform.workflows.record_step(
            run, step="write-a", output={"a": 1}, now=NOW, undo=lambda: undone.append("a")
        )
        platform.workflows.record_step(
            run, step="write-b", output={"b": 2}, now=NOW, undo=lambda: undone.append("b")
        )
        platform.workflows.transition(run, "failed", now=NOW, reason="injected")
        order = platform.workflows.compensate(run, NOW)
        self.assertEqual(undone, ["b", "a"])
        self.assertEqual(order, ["write-b", "write-a"])
        self.assertEqual(run.state, "compensated")

    # -- T011 ------------------------------------------------------------

    def test_T011_holdout_regression(self):
        """A holdout failure removes holdout evidence and caps the status."""

        platform = fresh_platform()
        upstream = seed_upstream(platform, self.batch)

        def broken(unit: dict) -> dict:
            if unit.get("asset") == "gamma":
                raise TrustBoundaryViolation("regression on gamma")
            return work(unit)

        corpus = standard_corpus(SCOPE, assets=ASSETS)
        result = BatchExecutor(platform, self.batch).execute(
            make_request(self.batch, upstream),
            principal=Principal("u-1", "tenant-a", "human"),
            now=NOW,
            transform=lambda unit: {"unit_id": unit["unit_id"], "result": "analysed"},
            corpus=[
                CorpusCase(
                    case_id=c.case_id,
                    kind=c.kind,
                    payload=c.payload,
                    expect="accept" if c.kind != "holdout" else "refuse",
                )
                for c in corpus
            ],
            requested_status="certified",
        )
        self.assertNotIn("holdout-corpus", result.benchmark.evidence_scopes())
        self.assertNotEqual(result.certificate.status, "certified")
        self.assertTrue(any("holdout" in item for item in result.limitations))

    # -- T012 ------------------------------------------------------------

    def test_T012_evidence_expiry(self):
        """Expired evidence turns a live certificate stale."""

        platform = fresh_platform()
        result = self.run_ok(platform, self.batch)
        certificate_id = result.certificate.certificate_id
        gate = platform.gate(self.batch)
        self.assertNotEqual(gate.get(certificate_id).status, "stale")
        far_future = NOW + timedelta(days=400)
        affected = gate.sweep_expired_evidence(far_future)
        self.assertIn(certificate_id, affected)
        self.assertEqual(gate.get(certificate_id).status, "stale")

    def test_T012b_input_change_invalidates(self):
        """A certificate that does not cover the new inputs becomes stale."""

        platform = fresh_platform()
        result = self.run_ok(platform, self.batch)
        gate = platform.gate(self.batch)
        affected = gate.invalidate_on_input_change([digest({"changed": True})])
        self.assertIn(result.certificate.certificate_id, affected)
        self.assertEqual(gate.get(result.certificate.certificate_id).status, "stale")


def _build_batch_cases() -> None:
    """Generate one TestCase subclass per batch, named after its catalog."""

    module = sys.modules[__name__]
    for package in REGISTRY:
        name = f"Batch{package.batch:02d}Conformance"
        cls = type(
            name,
            (BatchConformance,),
            {
                "batch": package.batch,
                "__doc__": f"Batch {package.batch:02d} ({package.slug}) conformance obligations.",
            },
        )
        setattr(module, name, cls)


_build_batch_cases()

# The abstract base must not run on its own.
del BatchConformance


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
