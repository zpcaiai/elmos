from __future__ import annotations

import unittest

from elmos_pdhi.adapters import AdapterRegistry, AdapterRequest, AdapterStatus
from elmos_pdhi.canonical import digest_object
from elmos_pdhi.runtime_proof import (
    NormalizationPolicy,
    NormalizationRule,
    ObservationKind,
    RuntimeDiffVerdict,
    RuntimeProofService,
    RuntimeTrace,
    TraceEvent,
    compare_runtime_traces,
)


def _trace(
    value: int,
    *,
    complete: bool = True,
    include_api: bool = False,
    request_id: str = "r-1",
    revision: int | None = None,
) -> RuntimeTrace:
    events = [
        TraceEvent(
            0,
            ObservationKind.STATE,
            "state",
            {"value": value, "request_id": request_id},
            digest_object({"event": "state", "value": value, "request_id": request_id}, domain="test-fixture"),
        )
    ]
    required = [ObservationKind.STATE]
    if include_api:
        required.append(ObservationKind.API_RESPONSE)
    return RuntimeTrace(
        scenario_id="scenario-1",
        input_digest=digest_object({"input": 1}, domain="test-fixture"),
        environment_digest=digest_object({"environment": "fixture"}, domain="test-fixture"),
        revision_digest=digest_object({"revision": value if revision is None else revision}, domain="test-fixture"),
        adapter_id="dap.fixture",
        tool_version="1",
        events=tuple(events),
        required_kinds=tuple(required),
        complete=complete,
        evidence_digests=(digest_object({"trace": value, "request_id": request_id}, domain="test-fixture"),),
    )


class RuntimeProofTests(unittest.TestCase):
    def test_partial_or_missing_trace_categories_never_pass(self) -> None:
        partial = _trace(1, complete=False, include_api=True)
        diff = compare_runtime_traces(partial, partial)
        self.assertEqual(RuntimeDiffVerdict.INSUFFICIENT_EVIDENCE, diff.verdict)
        self.assertTrue(diff.missing_evidence)

    def test_normalized_equivalence_and_semantic_regression(self) -> None:
        policy = NormalizationPolicy(
            "request-id-is-nondeterministic",
            (
                NormalizationRule(
                    "drop-request-id",
                    ObservationKind.STATE,
                    ("request_id",),
                    "drop",
                    "request identifier is contractually nondeterministic",
                ),
            ),
            authority_evidence_digest=digest_object(
                {"approved_policy": "request-id-is-nondeterministic"},
                domain="test-fixture",
            ),
        )
        equivalent = compare_runtime_traces(
            _trace(1, request_id="source"),
            _trace(1, request_id="target"),
            policy=policy,
        )
        self.assertEqual(RuntimeDiffVerdict.PASS, equivalent.verdict)
        self.assertTrue(equivalent.residual_uncertainty)
        unapproved_policy = NormalizationPolicy(
            "unapproved",
            (
                NormalizationRule(
                    "drop-request-id-unapproved",
                    ObservationKind.STATE,
                    ("request_id",),
                    "drop",
                    "unapproved test rule",
                ),
            ),
        )
        unapproved = compare_runtime_traces(
            _trace(1, request_id="source"),
            _trace(1, request_id="target"),
            policy=unapproved_policy,
        )
        self.assertEqual(RuntimeDiffVerdict.INSUFFICIENT_EVIDENCE, unapproved.verdict)
        different = compare_runtime_traces(_trace(1), _trace(2))
        self.assertEqual(RuntimeDiffVerdict.FAIL, different.verdict)
        counterexample = RuntimeProofService.counterexample_generator(different, "scenario-1")
        self.assertIsNotNone(counterexample)
        assert counterexample is not None
        self.assertFalse(counterexample.independently_verified)
        self.assertEqual("NOT_RUN", counterexample.replay_manifest["runtime_execution"])

    def test_deterministic_replay_and_missing_dap_adapter(self) -> None:
        service = RuntimeProofService()
        replay = service.deterministic_replay(_trace(1), _trace(1))
        self.assertEqual(RuntimeDiffVerdict.PASS, replay.verdict)
        stale_replay = service.deterministic_replay(_trace(1), _trace(1, revision=2))
        self.assertEqual(RuntimeDiffVerdict.INSUFFICIENT_EVIDENCE, stale_replay.verdict)
        discovery = service.dap_adapter_discovery()
        self.assertEqual(AdapterStatus.NOT_RUN.value, discovery["status"])
        request = AdapterRequest(
            request_id="dap-request",
            adapter_id="dap.missing",
            protocol="dap",
            operation="trace",
            source_digest=digest_object({"binary": 1}, domain="test-fixture"),
        )
        result = AdapterRegistry().invoke(request)
        self.assertEqual(AdapterStatus.NOT_RUN, result.status)


if __name__ == "__main__":
    unittest.main()
