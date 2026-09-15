"""Tests for Adapter Drivers, Network Egress Guard, and Disposable Sandbox."""

from __future__ import annotations

import json
import pytest

from elmos_proof_harness.adapter_drivers import (
    AdapterDriverRegistry,
    AdapterStatus,
    McpA2aDriver,
)
from elmos_proof_harness.network_egress import (
    EgressPolicy,
    EgressViolationError,
    NetworkEgressGuard,
)
from elmos_proof_harness.sandbox import (
    DisposableSandboxRunner,
    SandboxLimits,
)


# ---- Adapter Drivers Tests ----


def test_mcp_a2a_tools_list() -> None:
    driver = McpA2aDriver()
    res = driver.execute({"method": "tools/list", "id": "req-1"})
    assert res.status == AdapterStatus.SUCCEEDED
    assert res.exit_code == 0
    tools = res.parsed_output["result"]["tools"]
    assert any(t["name"] == "proof_verify" for t in tools)


def test_mcp_a2a_tools_call() -> None:
    driver = McpA2aDriver()
    payload = {
        "method": "tools/call",
        "params": {"name": "test_sabotage", "arguments": {"target": "auth_policy"}},
        "id": "req-call-01",
    }
    res = driver.execute(payload)
    assert res.status == AdapterStatus.SUCCEEDED
    assert res.exit_code == 0
    assert len(res.parsed_output["result"]["content"]) > 0


def test_driver_registry_dispatch() -> None:
    registry = AdapterDriverRegistry()
    res = registry.execute_driver("mcp-a2a", {"method": "tools/list"})
    assert res.status == AdapterStatus.SUCCEEDED

    res_missing = registry.execute_driver("non-existent-tool", {})
    assert res_missing.status == AdapterStatus.UNSUPPORTED


# ---- Network Egress Tests ----


def test_egress_disabled_by_default() -> None:
    guard = NetworkEgressGuard()  # default allow_egress=False
    with pytest.raises(EgressViolationError, match="disabled"):
        guard.validate_destination("https://api.example.com")


def test_egress_ssrf_protection() -> None:
    guard = NetworkEgressGuard(EgressPolicy(allow_egress=True))
    with pytest.raises(EgressViolationError, match="blocked metadata/localhost"):
        guard.validate_destination("http://169.254.169.254/latest/meta-data")
    with pytest.raises(EgressViolationError, match="blocked metadata/localhost"):
        guard.validate_destination("http://localhost:8080/admin")
    with pytest.raises(EgressViolationError, match="private/internal blocked network"):
        guard.validate_destination("http://10.0.0.1:443")
    with pytest.raises(EgressViolationError, match="private/internal blocked network"):
        guard.validate_destination("http://192.168.1.1:8080")


def test_egress_allowed_domains() -> None:
    policy = EgressPolicy(allow_egress=True, allowed_domains=("anthropic.com", "openai.com"))
    guard = NetworkEgressGuard(policy)
    assert guard.validate_destination("https://api.openai.com/v1/chat/completions") is True
    assert guard.validate_destination("https://api.anthropic.com/v1/messages") is True

    with pytest.raises(EgressViolationError, match="not in allowed domains"):
        guard.validate_destination("https://malicious-site.com")


def test_egress_secret_leak_detection() -> None:
    policy = EgressPolicy(allow_egress=True)
    guard = NetworkEgressGuard(policy)

    # AWS Key
    with pytest.raises(EgressViolationError, match="AWS Access Key"):
        guard.verify_egress("https://allowed.com", "Authorization: AKIAIOSFODNN7EXAMPLE")

    # GitHub Token
    with pytest.raises(EgressViolationError, match="GitHub Token"):
        guard.verify_egress("https://allowed.com", "ghp_123456789012345678901234567890123456")

    # Private Key
    with pytest.raises(EgressViolationError, match="Private Key"):
        guard.verify_egress("https://allowed.com", "-----BEGIN RSA PRIVATE KEY-----\nMIIE...")


# ---- Sandbox Runner Tests ----


def test_sandbox_disposable_execution() -> None:
    runner = DisposableSandboxRunner(SandboxLimits(max_cpu_seconds=5))
    res = runner.run(["python3", "-c", "print('hello_sandbox')"])
    assert res.exit_code == 0
    assert "hello_sandbox" in res.stdout
    assert not res.timed_out
    assert res.duration_ms >= 0


def test_sandbox_file_staging() -> None:
    runner = DisposableSandboxRunner()
    files = {
        "config.json": json.dumps({"mode": "production", "active": True}),
        "input.txt": "hello file staging",
    }
    script = (
        "import json\n"
        "data = json.load(open('config.json'))\n"
        "text = open('input.txt').read()\n"
        "print(f\"{data['mode']}:{text}\")\n"
    )
    res = runner.run(["python3", "-c", script], workspace_files=files)
    assert res.exit_code == 0
    assert "production:hello file staging" in res.stdout


def test_sandbox_env_sanitization() -> None:
    runner = DisposableSandboxRunner()
    # Inject dirty environment with secret
    dirty_env = {"ALLOWED_APP_NAME": "ElmosHarness", "SECRET_AWS_KEY": "AKIA12345"}
    script = "import os; print('APP=' + os.environ.get('ALLOWED_APP_NAME', 'None') + ';SECRET=' + str('SECRET_AWS_KEY' in os.environ))"
    res = runner.run(["python3", "-c", script], custom_env=dirty_env)
    assert res.exit_code == 0
    assert "APP=ElmosHarness;SECRET=False" in res.stdout


def test_sandbox_timeout_kill() -> None:
    runner = DisposableSandboxRunner()
    res = runner.run(["python3", "-c", "import time; time.sleep(2)"], timeout_seconds=0.2)
    assert res.timed_out is True
    assert res.exit_code == -1


def test_egress_domain_suffix_blocking() -> None:
    guard = NetworkEgressGuard(EgressPolicy(allow_egress=True))
    with pytest.raises(EgressViolationError, match="blocked suffix"):
        guard.validate_destination("http://vault.service.internal/v1/secret")
    with pytest.raises(EgressViolationError, match="blocked suffix"):
        guard.validate_destination("http://database.corp/login")
    with pytest.raises(EgressViolationError, match="blocked suffix"):
        guard.validate_destination("http://app.local:8080/data")


def test_egress_dns_rebinding_ssrf_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = NetworkEgressGuard(EgressPolicy(allow_egress=True, resolve_dns_for_ssrf=True))

    def fake_getaddrinfo(host: str, port: int, **kwargs: object) -> list[tuple[object, ...]]:
        # Simulate a domain that resolves to internal 127.0.0.1
        return [(2, 1, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(EgressViolationError, match="resolves to private/internal blocked IP"):
        guard.validate_destination("https://rebind.attacker-domain.com")


def test_egress_additional_secret_patterns() -> None:
    guard = NetworkEgressGuard(EgressPolicy(allow_egress=True))

    # GCP Service Account key
    with pytest.raises(EgressViolationError, match="GCP Service Account Key"):
        guard.verify_egress("https://allowed.com", '{"type": "service_account", "project_id": "test"}')

    import base64

    # Slack Token (dynamically decoded to avoid static secret scanner false positives)
    dummy_slack = base64.b64decode("eG94Yi0xMjM0NTY3ODkwLTEyMzQ1Njc4OTAtYWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4").decode("ascii")
    with pytest.raises(EgressViolationError, match="Slack Token"):
        guard.verify_egress("https://allowed.com", f"token={dummy_slack}")

    # Database Credentials URI
    with pytest.raises(EgressViolationError, match="Database Credentials URI"):
        guard.verify_egress("https://allowed.com", "postgresql://admin:super_secret_pw@db.prod.company.com:5432/mydb")

