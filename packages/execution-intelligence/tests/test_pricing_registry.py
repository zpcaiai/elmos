"""The shipped rate card is checked like any other artifact."""
import re

from conftest import ROOT

from elmos_execution_intelligence.io_utils import load_json
from elmos_execution_intelligence.validation import validate_pricing

VERIFIED = ROOT / "config" / "model-pricing.json"
TEMPLATE = ROOT / "config" / "model-pricing.template.json"
CAPABILITIES = ROOT / "config" / "provider-capabilities.json"
TOKEN_FIELDS = ("input", "cached_input", "cache_write", "output", "reasoning_output")


def test_the_verified_registry_validates_with_no_warnings():
    errors, warnings = validate_pricing(load_json(VERIFIED))
    assert errors == []
    assert warnings == [], "a verified registry must contain no not_for_billing entries"


def test_every_rate_cites_a_real_url_and_a_verification_date():
    for model in load_json(VERIFIED)["models"]:
        assert re.match(r"^https://", model["source_reference"]), model["id"]
        assert re.match(r"^\d{4}-\d{2}-\d{2}", model["verified_at"]), model["id"]
        assert model["not_for_billing"] is False


def test_every_rate_is_a_non_negative_number_with_no_placeholders():
    for model in load_json(VERIFIED)["models"]:
        for field in TOKEN_FIELDS:
            value = model["rates_per_million"][field]
            assert isinstance(value, int | float) and value >= 0, f"{model['id']}.{field}"


def test_modelling_decisions_are_recorded_not_hidden():
    """reasoning_output == output is a decision, not a vendor line item."""
    for model in load_json(VERIFIED)["models"]:
        rates = model["rates_per_million"]
        if rates["reasoning_output"] == rates["output"]:
            joined = " ".join(model.get("mapping_notes", []))
            assert "reasoning_output" in joined, f"{model['id']} must state why"
        if rates["cache_write"] == 0:
            joined = " ".join(model.get("mapping_notes", []))
            assert "cache_write" in joined, f"{model['id']} must state why cache_write is 0"


def test_cached_input_is_never_more_expensive_than_input():
    for model in load_json(VERIFIED)["models"]:
        rates = model["rates_per_million"]
        assert rates["cached_input"] <= rates["input"], model["id"]


def test_the_template_still_refuses_to_validate():
    """The template ships with nulls on purpose: it must not be usable as a rate card."""
    errors, _ = validate_pricing(load_json(TEMPLATE))
    assert errors, "the template must fail validation until someone fills it in"


def test_every_priced_model_has_a_capability_profile():
    priced = {model["id"] for model in load_json(VERIFIED)["models"]}
    profiled = set(load_json(CAPABILITIES)["models"])
    assert priced <= profiled, priced - profiled


def test_capability_tiers_are_from_the_declared_order():
    capabilities = load_json(CAPABILITIES)
    order = set(capabilities["tier_order"])
    for name, profile in capabilities["models"].items():
        assert profile["tier"] in order, name


def test_routing_on_the_verified_registry_prefers_cheaper_tiers():
    from elmos_execution_intelligence.routing import optimize_routing

    tasks = load_json(ROOT / "profiles" / "elmos" / "task-dag.json")
    plan = optimize_routing(tasks, load_json(VERIFIED), load_json(CAPABILITIES))
    assert plan["rates_are_illustrative"] is False
    assert plan["unroutable_tasks"] == []
    assert plan["totals"]["optimized"] <= plan["totals"]["frontier_baseline"]
    assert set(plan["tier_distribution"]) <= set(load_json(CAPABILITIES)["tier_order"])


def test_not_included_providers_are_named_rather_than_silently_absent():
    registry = load_json(VERIFIED)
    joined = " ".join(registry["not_included"]).lower()
    assert "kimi" in joined or "moonshot" in joined
    assert "qwen" in joined


def test_unverified_providers_carry_their_evidence_trail_not_a_guess():
    """A provider we could not verify records what was tried, and no numbers."""
    pending = load_json(VERIFIED)["pending_verification"]
    for key in ("moonshot_kimi", "alibaba_qwen"):
        entry = pending[key]
        assert entry["models_confirmed_to_exist"], key
        assert entry["urls_tried"], key
        assert entry["next_step"], key
        # the whole point: no rate sneaked in from a third party
        assert "rates_per_million" not in entry, key
    assert "does not accept them" in pending["why"]


def test_no_pending_provider_leaked_into_the_billable_models():
    ids = {model["id"] for model in load_json(VERIFIED)["models"]}
    for banned in ("kimi", "moonshot", "qwen"):
        assert not any(banned in model_id for model_id in ids), banned
