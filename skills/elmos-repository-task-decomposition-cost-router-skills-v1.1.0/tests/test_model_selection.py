from pathlib import Path
import json, yaml
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={"gpt-5.6-sol-max","claude-opus-5-max","claude-fable-5","grok-4.6","kimi-k3-max","glm-5.3-max","qwen3.8-max","deepseek-v4-pro-0813","gemini-3.7-flash-high","claude-sonnet-5"}

def test_model_selection_schema_exact_allowlist():
    s=json.loads((ROOT/"schemas/model-selection.schema.json").read_text())
    actual={x for x in s["properties"]["selected_model"]["enum"] if x is not None}
    assert actual == EXPECTED

def test_selection_policy_has_smart_and_manual():
    p=yaml.safe_load((ROOT/"config/model-selection-policy.yaml").read_text())
    assert p["default_mode"] == "smart"
    assert set(p["modes"]) == {"smart","manual"}
    assert set(p["modes"]["manual"]["allowed_fallback_policies"]) == {"strict","smart_within_allowlist"}

def test_examples_never_use_unknown_model():
    e=json.loads((ROOT/"examples/model-selection-examples.json").read_text())
    for x in e.values():
        if x["selected_model"] is not None:
            assert x["selected_model"] in EXPECTED
