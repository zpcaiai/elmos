from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={"gpt-5.6-sol-max","claude-opus-5-max","claude-fable-5","grok-4.6","kimi-k3-max","glm-5.3-max","qwen3.8-max","deepseek-v4-pro-0813","gemini-3.7-flash-high","claude-sonnet-5"}
def test_exact_allowlist():
    reg=yaml.safe_load((ROOT/"config/model-registry.yaml").read_text())
    assert set(reg["aliases"]) == EXPECTED
