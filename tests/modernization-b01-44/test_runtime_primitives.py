#!/usr/bin/env python3
"""Unit tests for the Batch 01-44 runtime primitives.

These target the guarantees the conformance suite relies on: canonicalisation,
determinism under concurrency, evidence semantics, the certification lattice,
approvals, adapters and corpus scoring.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.modernization_b01_44.adapters import AdapterRegistry  # noqa: E402
from scripts.modernization_b01_44.approval import ApprovalLedger  # noqa: E402
from scripts.modernization_b01_44.canonical import (  # noqa: E402
    CanonicalError,
    canonical_json,
    digest,
    idempotency_key,
    is_digest,
    parse_instant,
    stable_sort,
)
from scripts.modernization_b01_44.certification import (  # noqa: E402
    CertificationGate,
    REQUIRED_EVIDENCE,
    status_rank,
)
from scripts.modernization_b01_44.corpus import (  # noqa: E402
    Budget,
    CorpusCase,
    CorpusRunner,
    BenchmarkResult,
)
from scripts.modernization_b01_44.engine import DeterministicEngine  # noqa: E402
from scripts.modernization_b01_44.errors import (  # noqa: E402
    ApprovalRequired,
    BudgetExceeded,
    DeterminismViolation,
    EvidenceExpired,
    EvidenceMissing,
    PolicyViolation,
    ProviderDrift,
    RuntimeRefusal,
    SchemaViolation,
)
from scripts.modernization_b01_44.evidence import (  # noqa: E402
    UNKNOWN,
    EvidenceStore,
    LineageGraph,
    make_evidence,
    reconcile,
    trust_rank,
)
from scripts.modernization_b01_44.packages import load_registry  # noqa: E402
from scripts.modernization_b01_44.policy import PolicyEngine, Principal  # noqa: E402
from scripts.modernization_b01_44.validation import validate  # noqa: E402

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)
REGISTRY = load_registry()


class CanonicalTest(unittest.TestCase):
    def test_key_order_does_not_change_the_digest(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))

    def test_nested_key_order_does_not_change_the_digest(self):
        left = {"outer": {"z": [1, {"b": 2, "a": 1}], "y": "x"}}
        right = {"outer": {"y": "x", "z": [1, {"a": 1, "b": 2}]}}
        self.assertEqual(digest(left), digest(right))

    def test_list_order_does_change_the_digest(self):
        self.assertNotEqual(digest([1, 2]), digest([2, 1]))

    def test_floats_are_refused(self):
        with self.assertRaises(CanonicalError):
            digest({"ratio": 0.1})

    def test_sets_are_refused(self):
        with self.assertRaises(CanonicalError):
            digest({"tags": {"a", "b"}})

    def test_non_ascii_is_preserved_verbatim(self):
        self.assertIn("语义", canonical_json({"k": "语义"}))

    def test_stable_sort_is_total(self):
        items = [{"b": 1}, {"a": 2}, {"a": 1}]
        self.assertEqual(stable_sort(items), stable_sort(list(reversed(items))))

    def test_idempotency_key_is_a_digest(self):
        self.assertTrue(is_digest(idempotency_key("a", {"b": 1})))

    def test_naive_timestamps_are_refused(self):
        with self.assertRaises(CanonicalError):
            parse_instant("2026-08-04T00:00:00")


class DeterministicEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = DeterministicEngine()
        self.units = [{"i": i} for i in range(64)]

    def test_worker_count_does_not_change_output(self):
        result = self.engine.verify_worker_invariance(
            self.units, lambda u: {"i": u["i"], "v": u["i"] * 2}, worker_counts=(1, 4, 16)
        )
        self.assertTrue(is_digest(result.output_digest))

    def test_unordered_input_yields_the_same_digest(self):
        a = self.engine.execute(self.units, lambda u: u)
        b = self.engine.execute(list(reversed(self.units)), lambda u: u)
        self.assertEqual(a.output_digest, b.output_digest)

    def test_nondeterministic_transform_is_caught(self):
        counter = {"n": 0}

        def unstable(unit):
            counter["n"] += 1
            return {"i": unit["i"], "seq": counter["n"]}

        with self.assertRaises(DeterminismViolation):
            self.engine.verify_worker_invariance(
                self.units, unstable, worker_counts=(1, 4)
            )

    def test_idempotent_execution_replays_instead_of_rerunning(self):
        calls = {"n": 0}

        def counted(unit):
            calls["n"] += 1
            return unit

        first = self.engine.execute(self.units, counted, idempotency="k1")
        second = self.engine.execute(self.units, counted, idempotency="k1")
        self.assertEqual(calls["n"], len(self.units))
        self.assertTrue(second.replayed)
        self.assertEqual(first.output_digest, second.output_digest)

    def test_journal_replays(self):
        result = self.engine.execute(self.units, lambda u: u)
        self.assertTrue(self.engine.replay(result, result.journal))
        tampered = list(result.journal)
        tampered[0] = dict(tampered[0], output_digest="0" * 64)
        self.assertFalse(self.engine.replay(result, tampered))

    def test_fixpoint_converges(self):
        state, journal = self.engine.fixpoint(
            {"n": 5}, lambda s: {"n": max(0, s["n"] - 1)}
        )
        self.assertEqual(state, {"n": 0})
        self.assertEqual(len(journal.entries), 6)

    def test_non_convergent_fixpoint_is_refused_not_truncated(self):
        engine = DeterministicEngine(max_iterations=8)
        with self.assertRaises(BudgetExceeded):
            engine.fixpoint({"n": 0}, lambda s: {"n": s["n"] + 1})

    def test_unit_ceiling_is_enforced(self):
        engine = DeterministicEngine(max_units=3)
        with self.assertRaises(BudgetExceeded):
            engine.execute([{"i": i} for i in range(4)], lambda u: u)


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.store = EvidenceStore()

    def _add(self, scope, trust="deterministic", ttl=timedelta(days=1)):
        ev = make_evidence(
            evidence_id=f"ev-{scope}",
            producer="unit-test",
            created_at=NOW,
            trust_level=trust,
            scope=scope,
            payload={"scope": scope},
            ttl=ttl,
        )
        return self.store.add(ev)

    def test_digest_is_computed_not_supplied(self):
        ev = self._add("schema-conformance")
        self.assertEqual(ev.digest, digest({"scope": "schema-conformance"}))

    def test_append_only(self):
        self._add("s")
        other = make_evidence(
            evidence_id="ev-s",
            producer="someone-else",
            created_at=NOW,
            trust_level="deterministic",
            scope="s",
            payload={"scope": "different"},
        )
        with self.assertRaises(RuntimeRefusal):
            self.store.add(other)

    def test_model_inferred_is_not_execution_grade(self):
        self._add("s", trust="model-inferred")
        with self.assertRaises(EvidenceMissing):
            self.store.resolve(["ev-s"], now=NOW)

    def test_expired_evidence_is_refused(self):
        self._add("s", ttl=timedelta(hours=1))
        with self.assertRaises(EvidenceExpired):
            self.store.resolve(["ev-s"], now=NOW + timedelta(days=2))

    def test_invalidated_evidence_is_refused(self):
        self._add("s")
        self.store.invalidate("ev-s", "provider-drift")
        with self.assertRaises(EvidenceMissing):
            self.store.resolve(["ev-s"], now=NOW)

    def test_scope_mismatch_is_refused(self):
        self._add("s")
        with self.assertRaises(EvidenceMissing):
            self.store.resolve(["ev-s"], now=NOW, scope="other")

    def test_unknown_trust_level_is_refused(self):
        with self.assertRaises(RuntimeRefusal):
            trust_rank("vibes")


class LineageTest(unittest.TestCase):
    def test_cycles_are_refused(self):
        graph = LineageGraph()
        graph.link("b", "a")
        graph.link("c", "b")
        with self.assertRaises(RuntimeRefusal):
            graph.link("a", "c")

    def test_downstream_sweep_is_transitive(self):
        graph = LineageGraph()
        graph.link("b", "a")
        graph.link("c", "b")
        graph.link("d", "c")
        self.assertEqual(graph.downstream_of("a"), ["b", "c", "d"])

    def test_upstream_closure(self):
        graph = LineageGraph()
        graph.link("b", "a")
        graph.link("c", "b")
        self.assertEqual(graph.upstream_closure("c"), ["a", "b"])


class ReconciliationTest(unittest.TestCase):
    def test_unknown_is_never_a_match(self):
        result = reconcile({"k": UNKNOWN, "j": 1}, {"k": 1, "j": 1})
        self.assertEqual(result.unknown, ("k",))
        self.assertEqual(result.matched, ("j",))
        self.assertFalse(result.reconciled)

    def test_denominator_counts_everything(self):
        result = reconcile({"a": 1, "b": 2, "c": UNKNOWN}, {"a": 1, "b": 3, "d": 4})
        self.assertEqual(result.denominator, 4)

    def test_identical_runs_reconcile(self):
        self.assertTrue(reconcile({"a": [1, {"b": 2}]}, {"a": [1, {"b": 2}]}).reconciled)


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = PolicyEngine(REGISTRY.get(9))

    def test_gated_capability_is_denied_by_default(self):
        with self.assertRaises(PolicyViolation):
            self.policy.check_capability(Principal("u", "t"), "network")

    def test_explicit_grant_is_audited(self):
        self.policy.check_capability(Principal("u", "t"), "network", grant=True)
        self.assertEqual(self.policy.audit_log[-1].decision, "allow")

    def test_unknown_capability_is_refused(self):
        with self.assertRaises(PolicyViolation):
            self.policy.denies("teleport")

    def test_human_principal_is_not_bound_by_the_agent_envelope(self):
        self.policy.check_agent_write(Principal("u", "t", "human"), "tests", mode="commit")

    def test_policy_files_drive_behaviour(self):
        self.assertFalse(self.policy.evidence_first["model_claim_is_evidence"])
        self.assertTrue(self.policy.certification_policy["holdout_required_for_certified"])


class CertificationTest(unittest.TestCase):
    def setUp(self):
        self.store = EvidenceStore()
        self.gate = CertificationGate(PolicyEngine(REGISTRY.get(9)), self.store)

    def _evidence(self, scope, trust="runtime-observed", ttl=timedelta(days=10)):
        ev = make_evidence(
            evidence_id=f"ev-{scope}",
            producer="p",
            created_at=NOW,
            trust_level=trust,
            scope=scope,
            payload={"s": scope},
            ttl=ttl,
        )
        self.store.add(ev)
        return ev.evidence_id

    def test_status_lattice_is_ordered(self):
        self.assertLess(status_rank("experimental"), status_rank("limited"))
        self.assertLess(status_rank("limited"), status_rank("certified"))

    def test_no_evidence_means_blocked(self):
        decision = self.gate.evaluate(
            requested_status="certified", scope="s", evidence_refs=[], now=NOW
        )
        self.assertEqual(decision.granted_status, "blocked")

    def test_full_evidence_grants_certified(self):
        refs = [self._evidence(scope) for scope in REQUIRED_EVIDENCE["certified"]]
        decision = self.gate.evaluate(
            requested_status="certified", scope="s", evidence_refs=refs, now=NOW
        )
        self.assertEqual(decision.granted_status, "certified")

    def test_removing_holdout_downgrades_to_limited(self):
        scopes = set(REQUIRED_EVIDENCE["certified"]) - {"holdout-corpus"}
        refs = [self._evidence(scope) for scope in scopes]
        decision = self.gate.evaluate(
            requested_status="certified", scope="s", evidence_refs=refs, now=NOW
        )
        self.assertEqual(decision.granted_status, "limited")
        self.assertIn("missing-evidence", decision.reasons)

    def test_model_inferred_evidence_does_not_count(self):
        refs = [
            self._evidence(scope, trust="model-inferred")
            for scope in REQUIRED_EVIDENCE["certified"]
        ]
        decision = self.gate.evaluate(
            requested_status="certified", scope="s", evidence_refs=refs, now=NOW
        )
        self.assertEqual(decision.granted_status, "blocked")

    def test_granted_never_exceeds_requested(self):
        refs = [self._evidence(scope) for scope in REQUIRED_EVIDENCE["certified"]]
        decision = self.gate.evaluate(
            requested_status="experimental", scope="s", evidence_refs=refs, now=NOW
        )
        self.assertEqual(decision.granted_status, "experimental")

    def test_issue_binds_input_digests(self):
        refs = [self._evidence(scope) for scope in REQUIRED_EVIDENCE["limited"]]
        certificate, _ = self.gate.issue(
            batch=9,
            scope="s",
            requested_status="limited",
            evidence_refs=refs,
            input_digests=[digest({"in": 1})],
            now=NOW,
        )
        self.assertTrue(certificate.covers([digest({"in": 1})]))
        self.assertFalse(certificate.covers([digest({"in": 2})]))

    def test_malformed_input_digest_is_refused(self):
        with self.assertRaises(Exception):
            self.gate.issue(
                batch=9,
                scope="s",
                requested_status="limited",
                evidence_refs=[],
                input_digests=["not-a-digest"],
                now=NOW,
            )


class ApprovalTest(unittest.TestCase):
    def setUp(self):
        self.ledger = ApprovalLedger()
        self.request = {"action": "cutover", "scope": "svc"}

    def test_agent_cannot_grant_approval(self):
        with self.assertRaises(PolicyViolation):
            self.ledger.grant(
                request=self.request,
                approver=Principal("a", "t", "agent"),
                action="cutover",
                now=NOW,
            )

    def test_changed_request_invalidates_the_approval(self):
        approval = self.ledger.grant(
            request=self.request, approver=Principal("h1", "t"), action="cutover", now=NOW
        )
        with self.assertRaises(ApprovalRequired):
            self.ledger.require(
                request={"action": "cutover", "scope": "other"},
                approval_ids=[approval.approval_id],
                action="cutover",
                now=NOW,
            )

    def test_expired_approval_is_refused(self):
        approval = self.ledger.grant(
            request=self.request, approver=Principal("h1", "t"), action="cutover", now=NOW
        )
        with self.assertRaises(ApprovalRequired):
            self.ledger.require(
                request=self.request,
                approval_ids=[approval.approval_id],
                action="cutover",
                now=NOW + timedelta(days=2),
            )

    def test_critical_action_requires_two_distinct_humans(self):
        a = self.ledger.grant(
            request=self.request, approver=Principal("h1", "t"), action="cutover", now=NOW
        )
        with self.assertRaises(ApprovalRequired):
            self.ledger.require(
                request=self.request,
                approval_ids=[a.approval_id],
                action="cutover",
                now=NOW,
                criticality="critical",
            )
        b = self.ledger.grant(
            request=self.request, approver=Principal("h2", "t"), action="cutover", now=NOW
        )
        approvals = self.ledger.require(
            request=self.request,
            approval_ids=[a.approval_id, b.approval_id],
            action="cutover",
            now=NOW,
            criticality="critical",
        )
        self.assertEqual(len(approvals), 2)

    def test_same_human_twice_is_not_dual_control(self):
        a = self.ledger.grant(
            request=self.request, approver=Principal("h1", "t"), action="cutover", now=NOW
        )
        b = self.ledger.grant(
            request=self.request, approver=Principal("h1", "t"), action="cutover", now=NOW
        )
        with self.assertRaises(ApprovalRequired):
            self.ledger.require(
                request=self.request,
                approval_ids=[a.approval_id, b.approval_id],
                action="cutover",
                now=NOW,
                criticality="critical",
            )


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.registry = AdapterRegistry()
        self.pin = self.registry.register(
            "p", "1.2.3", contract={"ops": ["a"]}, capabilities=["a"]
        ).pin()

    def test_no_drift_when_unchanged(self):
        self.assertEqual(self.registry.detect_drift([self.pin]), [])

    def test_patch_bump_is_non_breaking(self):
        self.registry.register("p", "1.2.4", contract={"ops": ["a"]})
        reports = self.registry.detect_drift([self.pin])
        self.assertEqual(len(reports), 1)
        self.assertFalse(reports[0].breaking)
        self.registry.assert_no_breaking_drift([self.pin])

    def test_major_bump_is_breaking(self):
        self.registry.register("p", "2.0.0", contract={"ops": ["a"]})
        with self.assertRaises(ProviderDrift):
            self.registry.assert_no_breaking_drift([self.pin])

    def test_contract_change_at_same_version_is_breaking(self):
        self.registry.register("p", "1.2.3", contract={"ops": ["a", "b"]})
        with self.assertRaises(ProviderDrift):
            self.registry.assert_no_breaking_drift([self.pin])

    def test_absent_provider_is_breaking(self):
        empty = AdapterRegistry()
        with self.assertRaises(ProviderDrift):
            empty.assert_no_breaking_drift([self.pin])

    def test_non_semver_is_refused(self):
        with self.assertRaises(RuntimeRefusal):
            self.registry.register("q", "latest", contract={})


class CorpusTest(unittest.TestCase):
    def setUp(self):
        self.cases = [
            CorpusCase("ok-1", "development", {"unit_id": "u1"}, "accept"),
            CorpusCase("bad-1", "negative", {"nope": True}, "refuse"),
        ]

        def subject(payload):
            if "unit_id" not in payload:
                raise PolicyViolation("not a unit")
            return payload

        self.runner = CorpusRunner(subject)

    def test_accept_and_refuse_are_both_load_bearing(self):
        reports = self.runner.run_all(self.cases)
        self.assertTrue(reports["development"].clean)
        self.assertTrue(reports["negative"].clean)

    def test_subject_that_stops_refusing_fails_the_negative_corpus(self):
        permissive = CorpusRunner(lambda payload: payload)
        report = permissive.run(self.cases, "negative")
        self.assertFalse(report.clean)

    def test_score_carries_an_explicit_denominator(self):
        report = self.runner.run(self.cases, "development")
        self.assertEqual(report.score, "1/1")

    def test_budget_exhaustion_marks_not_run_rather_than_dropping(self):
        many = [
            CorpusCase(f"c{i}", "development", {"unit_id": f"u{i}"}, "accept") for i in range(5)
        ]
        runner = CorpusRunner(lambda p: p, budget=Budget(limit=2, label="corpus"))
        report = runner.run(many, "development")
        self.assertEqual(report.denominator, 5)
        self.assertEqual(report.not_run, 3)
        self.assertFalse(report.clean)

    def test_evidence_scopes_only_from_clean_corpora(self):
        result = BenchmarkResult(reports=self.runner.run_all(self.cases))
        self.assertIn("development-corpus", result.evidence_scopes())
        self.assertNotIn("holdout-corpus", result.evidence_scopes())

    def test_budget_charge_beyond_limit_refuses(self):
        budget = Budget(limit=1)
        budget.charge()
        with self.assertRaises(BudgetExceeded):
            budget.charge()


class ValidationTest(unittest.TestCase):
    def setUp(self):
        self.schema = REGISTRY.get(9).schema("batch-input")

    def test_valid_payload_passes(self):
        validate(
            {
                "request_id": "r",
                "tenant_id": "t",
                "project_id": "p",
                "scope": "s",
                "upstream_certificate_refs": ["c"],
            },
            self.schema,
        )

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(SchemaViolation):
            validate(
                {
                    "request_id": "r",
                    "tenant_id": "t",
                    "project_id": "p",
                    "scope": "s",
                    "upstream_certificate_refs": ["c"],
                    "extra": 1,
                },
                self.schema,
            )

    def test_empty_upstream_list_is_rejected(self):
        with self.assertRaises(SchemaViolation):
            validate(
                {
                    "request_id": "r",
                    "tenant_id": "t",
                    "project_id": "p",
                    "scope": "s",
                    "upstream_certificate_refs": [],
                },
                self.schema,
            )

    def test_bad_digest_pattern_is_rejected(self):
        schema = REGISTRY.get(9).schema("evidence-ref")
        with self.assertRaises(SchemaViolation):
            validate(
                {
                    "evidence_id": "e",
                    "digest": "ZZZ",
                    "producer": "p",
                    "created_at": "2026-08-04T00:00:00Z",
                    "trust_level": "deterministic",
                    "scope": "s",
                },
                schema,
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
