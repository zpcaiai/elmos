"""Tests for Dual-Token Authentication, Token Rotation, Replay Attack Detection, and Blacklist."""

from __future__ import annotations

import pytest

from elmos_project_synthesis.dual_token_auth import (
    DualTokenAuthManager,
    ReplayAttackError,
    SeamlessRefreshClientInterceptor,
    TokenRevokedError,
)


def test_login_and_token_pair_issuance():
    auth_mgr = DualTokenAuthManager(jwt_secret="test-super-secret-enterprise-key-32")
    pair = auth_mgr.issue_token_pair(
        user_id="user-101",
        tenant_id="tenant-enterprise-1",
        roles=["ADMIN", "OPERATOR"],
    )

    assert pair.access_token is not None
    assert pair.refresh_token is not None
    assert pair.token_type == "Bearer"
    assert pair.expires_in == 900
    assert pair.refresh_expires_in == 604800

    # Validate access token
    payload = auth_mgr.verify_access_token(pair.access_token)
    assert payload["sub"] == "user-101"
    assert payload["tenant_id"] == "tenant-enterprise-1"
    assert payload["roles"] == ["ADMIN", "OPERATOR"]


def test_token_refresh_and_rotation():
    auth_mgr = DualTokenAuthManager(jwt_secret="test-super-secret-enterprise-key-32")
    pair1 = auth_mgr.issue_token_pair(user_id="user-101", tenant_id="tenant-1")

    # Refresh
    pair2 = auth_mgr.refresh_token_pair(pair1.refresh_token)
    assert pair2.access_token != pair1.access_token
    assert pair2.refresh_token != pair1.refresh_token

    # Verify new access token works
    payload2 = auth_mgr.verify_access_token(pair2.access_token)
    assert payload2["sub"] == "user-101"


def test_token_family_replay_attack_detection():
    auth_mgr = DualTokenAuthManager(jwt_secret="test-super-secret-enterprise-key-32")
    pair1 = auth_mgr.issue_token_pair(user_id="user-101", tenant_id="tenant-1")

    # Legitimate client refreshes -> gets pair2
    pair2 = auth_mgr.refresh_token_pair(pair1.refresh_token)

    # Attacker tries to use stolen old pair1.refresh_token
    with pytest.raises(ReplayAttackError) as exc_info:
        auth_mgr.refresh_token_pair(pair1.refresh_token)
    assert "Replay attack detected" in str(exc_info.value)

    # Because family was invalidated, legitimate pair2.refresh_token is now also blocked
    with pytest.raises(TokenRevokedError) as exc_info2:
        auth_mgr.refresh_token_pair(pair2.refresh_token)
    assert "Token family compromised" in str(exc_info2.value)


def test_token_blacklist_and_logout():
    auth_mgr = DualTokenAuthManager(jwt_secret="test-super-secret-enterprise-key-32")
    pair = auth_mgr.issue_token_pair(user_id="user-101", tenant_id="tenant-1")

    # Verify works before logout
    assert auth_mgr.verify_access_token(pair.access_token)["sub"] == "user-101"

    # Logout and blacklist
    auth_mgr.logout(pair.access_token, pair.refresh_token)

    # Access token verification fails
    with pytest.raises(TokenRevokedError):
        auth_mgr.verify_access_token(pair.access_token)

    # Refresh token verification fails
    with pytest.raises(TokenRevokedError):
        auth_mgr.refresh_token_pair(pair.refresh_token)


def test_seamless_refresh_client_interceptor():
    auth_mgr = DualTokenAuthManager(jwt_secret="test-super-secret-enterprise-key-32")
    pair = auth_mgr.issue_token_pair(user_id="user-101", tenant_id="tenant-1")

    current_access_token = pair.access_token
    current_refresh_token = pair.refresh_token

    def token_refresher() -> str:
        nonlocal current_access_token, current_refresh_token
        new_pair = auth_mgr.refresh_token_pair(current_refresh_token)
        current_access_token = new_pair.access_token
        current_refresh_token = new_pair.refresh_token
        return current_access_token

    interceptor = SeamlessRefreshClientInterceptor(
        get_access_token=lambda: current_access_token,
        refresh_tokens=token_refresher,
    )

    call_count = 0

    def mock_backend_request(headers: dict[str, str]) -> dict[str, str | int]:
        nonlocal call_count
        call_count += 1
        auth = headers.get("Authorization", "")
        # First call with old token fails simulated 401
        if call_count == 1:
            return {"status_code": 401, "body": "TOKEN_EXPIRED"}
        # Second call with refreshed token succeeds
        return {"status_code": 200, "body": "SUCCESS", "token_used": auth}

    response = interceptor.execute_with_retry(mock_backend_request)
    assert response["status_code"] == 200
    assert response["body"] == "SUCCESS"
    assert call_count == 2
