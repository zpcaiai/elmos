import datetime as dt

from etgb.policy import authorize, authority_digest


def authority() -> dict:
    return {
        "schema_version": "1.1",
        "authority_id": "auth-1",
        "environment_id": "env-1",
        "owner_type": "environment",
        "owner_id": "worker-1",
        "tenant_id": "tenant-1",
        "role": "transform-worker",
        "capabilities": ["filesystem.read", "harness.prepare"],
        "filesystem": {"read_roots": ["/workspace/source"], "write_roots": ["/workspace/target"]},
        "network": {"mode": "allowlist", "allowlist": ["repo.maven.apache.org", "*.example.org"]},
        "secrets": {"allowed_refs": ["secret://model/token"]},
        "hidden_tests": {"read": False, "write": False, "execute": False},
        "fencing_token": 7,
        "expires_at": "2030-01-01T00:00:00Z",
    }


def request(**overrides: object) -> dict:
    value = {
        "authority_id": "auth-1", "environment_id": "env-1", "owner_id": "worker-1",
        "tenant_id": "tenant-1", "action": "filesystem.read", "path": "/workspace/source/a.java",
        "path_mode": "read", "fencing_token": 7,
    }
    value.update(overrides)
    return value


def test_owner_bound_authority_allows_exact_scope() -> None:
    a = authority()
    assert authorize(a, request()).allowed
    assert authority_digest(a).startswith("sha256:")


def test_hidden_tests_path_traversal_and_stale_fence_are_denied() -> None:
    a = authority()
    assert authorize(a, request(hidden_test_action="read")).rule == "hidden-tests"
    assert authorize(a, request(path="/workspace/source/../hidden-tests/x")).rule == "filesystem"
    assert authorize(a, request(fencing_token=6)).rule == "fencing"
    assert authorize(a, request(owner_id="worker-2")).rule == "owner-binding"


def test_expired_authority_is_denied() -> None:
    decision = authorize(authority(), request(), now=dt.datetime(2031, 1, 1, tzinfo=dt.timezone.utc))
    assert not decision.allowed and decision.rule == "authority-expiry"
