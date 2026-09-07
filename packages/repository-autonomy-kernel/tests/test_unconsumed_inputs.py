"""An adapter must not answer while ignoring an input the caller stated.

This exists because of a defect this bridge shipped. ``_packreg_request``
promoted on the presence of a core-shaped ``package`` and forwarded only the
kernel's own fields — so a caller who *also* sent
``test_results: [{"status": "FAIL"}]`` got LOCAL_ENGINEERING_VALIDATED where the
legacy path returns BLOCKED / PACKAGE_INVALID. The test gate did not move or
weaken. The field was simply never read.

That is the failure written up in ``_captured_at``'s own docstring — "a silently
ignored field is a caller who thinks they configured something" — committed one
row over. A survey then found the same shape latent in eight more adapters,
including ``validation-dag`` dropping ``risk_profile``, which is a safety input.

So it is a mechanism rather than nine repairs: every bridged row declares the
declared inputs it reads, and ``serve`` declines to promote when the payload
states one it does not.
"""

from __future__ import annotations

import pytest

from elmos_repository_autonomy import kernel_bridge
from elmos_repository_autonomy.catalog import SKILL_SPECS
from elmos_repository_autonomy.dispatcher import AutonomyRuntime
from elmos_repository_autonomy.kernel_bridge import _is_stated
from elmos_repository_autonomy.models import Status


@pytest.fixture()
def runtime():
    return AutonomyRuntime()


def test_every_bridged_row_declares_what_it_reads():
    """And only names inputs the catalogue actually declares.

    A row naming a field the catalogue does not have is a stale declaration -
    the check would then pass for a reason nobody intended.
    """

    for skill, spec in kernel_bridge.BRIDGES.items():
        declared = set(SKILL_SPECS[skill].inputs)
        assert spec.consumes <= declared, (
            f"{skill} declares consuming {sorted(spec.consumes - declared)}, "
            "which the catalogue does not list as an input"
        )


def test_a_stated_input_the_adapter_ignores_keeps_the_legacy_engine(runtime):
    """`risk_profile` drives which checks are required in the legacy planner.

    The core takes an explicit `test_catalog` where each check carries its own
    `required` flag, so risk is expressed differently and the adapter never
    reads the field. Answering anyway would silently discard a safety input.
    """

    base = {
        "task_spec": {"id": "t"}, "change_graph": {}, "repository_profile": {},
        "risk_profile": {},
        "test_catalog": [{"checkId": "build", "kind": "build", "required": True}],
        "validation_budget": {"maxCost": 100, "maxChecks": 10},
    }

    assert "ENGINE:kernel" in runtime.execute("validation-dag", base).reasons

    stated = runtime.execute("validation-dag", {**base, "risk_profile": {"level": "HIGH"}})
    assert "ENGINE:legacy" in stated.reasons
    assert "KERNEL_INPUT_UNMAPPED:UNCONSUMED:risk_profile" in stated.reasons


def test_an_empty_placeholder_is_not_a_statement(runtime):
    """The distinction is information lost versus a slot left open.

    Half the payloads in this package pass `{}` for context fields they have
    nothing to say about. Refusing on those would route them all to the legacy
    engine over an empty dict, which is strictness with no safety in it.
    """

    assert _is_stated({}) is False
    assert _is_stated([]) is False
    assert _is_stated("") is False
    assert _is_stated(None) is False

    assert _is_stated({"level": "HIGH"}) is True
    assert _is_stated(["x"]) is True


def test_zero_and_false_are_statements_not_absence():
    """This package's own rule: zero is a legal business value.

    Treating `0` or `False` as "nothing was said" would be the silent-zero
    defect - the one this repository has shipped three times - wearing a
    different hat, in the very check meant to stop silent drops.
    """

    assert _is_stated(0) is True
    assert _is_stated(False) is True
    assert _is_stated(0.0) is True


def test_the_packreg_defect_that_produced_this_mechanism(runtime):
    """The original: a signed package plus failing tests reported as validated."""

    from elmos_autonomy_kernel.packreg import (
        _decode_package,
        default_signing_key,
        set_default_signing_key,
        sign_package,
    )

    set_default_signing_key(b"S" * 48)
    try:
        package = {
            "packageId": "acme", "version": "1.0.0", "skills": ["repository-census"],
            "contractsDigest": "sha256:" + "c" * 64, "permissions": {"fs": "read"},
            "signature": "placeholder",
        }
        package["signature"] = sign_package(
            _decode_package(package).content_digest, default_signing_key())

        clean = runtime.execute("capability-package-registry", {"package": package})
        assert "ENGINE:kernel" in clean.reasons

        with_tests = runtime.execute("capability-package-registry", {
            "package": package, "test_results": [{"status": "FAIL"}]})
        assert "ENGINE:kernel" not in with_tests.reasons
        assert with_tests.status is not Status.LOCAL_ENGINEERING_VALIDATED
    finally:
        set_default_signing_key(None)


# --- the exemption, and why it must be earned ---------------------------------
#
# The ``consumes`` check refuses to promote when the caller states an input the
# adapter does not read. That reasoning holds only if the *other* engine would
# have read it. For seven declared inputs it would not: the catalogue names
# them and both implementations drop them. Refusing on one of those sends the
# call to an engine that ignores it too — the better engine lost, no information
# preserved, nothing gained.
#
# So ``declared_but_unimplemented`` exempts them, and every entry is proved
# here *behaviourally* rather than asserted: the legacy engine's output must be
# identical with and without the field. That makes the list a claim about the
# code, not a place to put things that were inconvenient.


def _legacy_payload(skill):
    """A payload the legacy engine answers, per exempted skill."""

    return {
        "validation-dag": {
            "task_spec": {"id": "t", "acceptance_criteria": [{"id": "c1"}]},
            "change_graph": {}, "repository_profile": {}, "risk_profile": {},
            "test_catalog": [{"id": "c1", "validator": "pytest"}],
        },
        "phase-aware-model-router": {
            "step_profile": {"required_context": 100},
            "model_capability_profiles": [
                {"model_id": "m1", "eval_status": "PASS", "max_context": 8000,
                 "quality": 0.9, "cost_per_call": 0.01, "latency_ms": 500},
            ],
            "risk_profile": {}, "budget": {}, "provider_policy": {},
        },
        "repository-model-elo": {
            "arena_results": [{"candidate_id": "a", "outcome": "PASS", "task_class": "x"},
                              {"candidate_id": "b", "outcome": "FAIL", "task_class": "x"}],
            "task_taxonomy": {},
        },
        "repository-census": {
            "immutable_repository_snapshot": {
                "sha256": "s", "files": [{"path": "a.py", "content": "x=1", "sha256": "d"}],
            },
            # `build_files` is read by legacy and refused by the bridge, so it
            # pins this baseline to the legacy engine - which is the engine
            # whose behaviour the exemption is a claim about. It is present in
            # both runs, so it cannot itself account for a difference.
            "build_files": [{"path": "pyproject.toml", "system": "python"}],
        },
        "lazy-tool-loader": {
            "tool_catalog": [{"tool_id": "echo", "version": "1", "capabilities": ["run"]}],
            "step_requirements": ["run"],
        },
    }[skill]


#: A non-trivial value for each exempted field — something that would visibly
#: change an output if any engine consulted it.
_LOUD_VALUES = {
    "change_graph": {"nodes": [{"id": "n1"}], "edges": [{"from": "n1", "to": "n2"}]},
    "recent_evals": [{"model_id": "m1", "score": 0.1, "status": "FAIL"}],
    "model_cost_latency": [{"model_id": "a", "cost": 999.0, "latency_ms": 99999}],
    "api_schemas": [{"path": "openapi.yaml", "operations": ["GET /x"]}],
    "coverage": {"line_percent": 12.5, "files": [{"path": "a.py", "covered": 3}]},
    "optional_runtime_traces": [{"trace_id": "t1", "spans": [{"name": "s"}]}],
    "agent_contract": {"agentId": "ag-1", "allowedTools": ["echo", "rm-rf"],
                       "network": "allow"},
}


def test_every_exempted_field_is_provably_ignored_by_the_legacy_engine(runtime):
    """The exemption is a claim about the code, and this is the proof.

    For each field: run the legacy engine without it, then with a value loud
    enough to change any output that consulted it. The results must be
    identical. If a future change makes an engine read one of these, this fails
    and the entry has to go — which is the point of proving it rather than
    listing it.
    """

    exempted = [
        (skill, field)
        for skill, spec in sorted(kernel_bridge.BRIDGES.items())
        for field in sorted(spec.declared_but_unimplemented)
    ]
    assert len(exempted) == 7, "the exempted set changed; re-derive it before editing"

    for skill, field in exempted:
        payload = _legacy_payload(skill)
        assert field not in payload or not payload[field], (skill, field)

        without = runtime.execute(skill, dict(payload))
        with_field = runtime.execute(skill, {**payload, field: _LOUD_VALUES[field]})

        assert "ENGINE:legacy" in without.reasons, (skill, field)
        assert without.output == with_field.output, (
            f"{skill}.{field} changes the legacy output, so it is NOT unimplemented - "
            "remove it from declared_but_unimplemented"
        )


def test_an_exempted_field_no_longer_blocks_promotion(runtime):
    """The reachability this buys back.

    `recent_evals` is declared by the catalogue, read by neither engine, and was
    routing every caller who sent one to the legacy float ranking.
    """

    def model(model_id, price, tier):
        return {"modelId": model_id, "tier": tier, "provider": "acme",
                "contextWindow": 200000, "maxOutput": 8192,
                "priceInputPerMtok": price, "priceOutputPerMtok": price,
                "capabilities": ["code"], "reliabilityPrior": "0.99",
                "deprecated": False}

    payload = {
        "step_profile": {"phase": "execute", "riskClass": "high",
                         "candidateModelIds": ["cheap", "frontier"],
                         "requiredCapabilities": ["code"],
                         "estimatedInputTokens": 10000, "estimatedOutputTokens": 2000},
        "model_registry": [model("cheap", "1.00", "standard"),
                           model("frontier", "15.00", "frontier")],
        "routing_policy": {"rules": [{"phase": "execute", "riskClass": "high",
                                      "minTier": "frontier",
                                      "requiredCapabilities": ["code"],
                                      "allowedProviders": ["acme"],
                                      "costCeiling": "5.00"}]},
        "recent_evals": [{"model_id": "frontier", "score": 0.99}],
    }

    result = runtime.execute("phase-aware-model-router", payload)
    assert result.error is None
    assert "ENGINE:kernel" in result.reasons


def test_a_field_only_the_legacy_engine_reads_still_blocks(runtime):
    """The exemption must not swallow the real cases.

    `risk_profile` *is* read by the legacy router, so a caller who states one
    still keeps the engine that will use it.
    """

    outcome = kernel_bridge.serve("phase-aware-model-router", {
        "step_profile": {"phase": "execute", "riskClass": "high",
                         "candidateModelIds": ["m"], "requiredCapabilities": []},
        "model_registry": [{"modelId": "m", "tier": "frontier", "provider": "a",
                            "contextWindow": 1000, "maxOutput": 100,
                            "priceInputPerMtok": "1.00", "priceOutputPerMtok": "1.00",
                            "capabilities": [], "reliabilityPrior": "0.9",
                            "deprecated": False}],
        "routing_policy": {"rules": []},
        "risk_profile": {"level": "CRITICAL"},
    })

    assert outcome.served is False
    assert "KERNEL_INPUT_UNMAPPED:UNCONSUMED:risk_profile" in outcome.reasons
