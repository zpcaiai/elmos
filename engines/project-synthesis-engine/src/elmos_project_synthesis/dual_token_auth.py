"""Enterprise Dual-Token Authentication and Seamless Refresh Engine.

Implements production-grade dual-token architecture:
1. Dual-Token Specifications:
   - Access Token: Short-lived (default 15 mins), signed JWT containing user claims,
     tenant_id, roles, permissions, jti, and token_type='access'.
   - Refresh Token: Long-lived (default 7 days), cryptographic signed token containing
     family_id, generation, sub, tenant_id, and token_type='refresh'.
2. Security & Lifecycle Governance:
   - Token Rotation: Every refresh rotates the refresh token (issues a new access token
     and a new refresh token with incremented generation).
   - Replay Attack & Token Theft Defense (Token Family):
     If an already-consumed refresh token is reused, the entire token family is immediately
     compromised and revoked (Family Revocation).
   - Token Blacklist / Immediate Revocation:
     Thread-safe and TTL-bounded blacklist for logout and administrative revocation.
3. Seamless Client Refresh Interceptor:
   - Catches 401 TOKEN_EXPIRED errors and transparently invokes token refresh,
     updating tokens and re-executing requests without end-user interruption.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class TokenError(Exception):
    """Base exception for token operations."""


class TokenExpiredError(TokenError):
    """Raised when access or refresh token has expired."""


class TokenInvalidError(TokenError):
    """Raised when token signature or payload is invalid."""


class TokenRevokedError(TokenError):
    """Raised when token has been explicitly revoked or blacklisted."""


class TokenReplayCompromisedError(TokenError):
    """Raised when an already-consumed refresh token is replayed (token theft detected)."""


ReplayAttackError = TokenReplayCompromisedError


@dataclass
class TokenFamily:
    """Represents a token family identifier and state."""

    family_id: str
    latest_generation: int = 1
    is_compromised: bool = False


@dataclass
class TokenPair:
    """Represents a coordinated Access Token and Refresh Token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"  # noqa: S105
    expires_in: int = 900  # seconds for access token
    refresh_expires_in: int = 604800  # 7 days


@dataclass
class RefreshTokenRecord:
    """State tracking for an active or consumed refresh token within a family."""

    jti: str
    family_id: str
    sub: str
    tenant_id: str
    generation: int
    is_consumed: bool = False
    expires_at: float = 0.0


class TokenBlacklist:
    """In-memory thread-safe blacklist for revoked JTIs and compromised Token Families."""

    def __init__(self) -> None:
        self._blacklisted_jtis: dict[str, float] = {}  # jti -> expires_at
        self._revoked_families: set[str] = set()
        self._lock = threading.Lock()

    def revoke_jti(self, jti: str, expires_at: float) -> None:
        with self._lock:
            self._blacklisted_jtis[jti] = expires_at

    def revoke_family(self, family_id: str) -> None:
        with self._lock:
            self._revoked_families.add(family_id)
            logger.warning("TokenBlacklist: Revoked entire token family [%s] due to replay attack", family_id)

    def is_jti_revoked(self, jti: str) -> bool:
        now = time.time()
        with self._lock:
            exp = self._blacklisted_jtis.get(jti)
            if exp is not None:
                if exp > now:
                    return True
                # Clean up expired entry
                del self._blacklisted_jtis[jti]
            return False

    def is_family_revoked(self, family_id: str) -> bool:
        with self._lock:
            return family_id in self._revoked_families


class DualTokenAuthManager:
    """Manages dual-token issuance, validation, rotation, and replay detection."""

    def __init__(
        self,
        secret_key: str = "elmos-enterprise-secret-key-32chars!!",  # noqa: S107
        access_token_ttl: int = 900,  # 15 mins
        refresh_token_ttl: int = 604800,  # 7 days
        jwt_secret: str | None = None,
    ) -> None:
        effective_key = jwt_secret if jwt_secret is not None else secret_key
        self.secret_key = effective_key.encode("utf-8")
        self.access_token_ttl = access_token_ttl
        self.refresh_token_ttl = refresh_token_ttl
        self.blacklist = TokenBlacklist()
        # Storage of active and consumed refresh tokens: jti -> RefreshTokenRecord
        self._refresh_records: dict[str, RefreshTokenRecord] = {}
        # Mapping from family_id to latest active generation
        self._family_latest_generation: dict[str, int] = {}
        self._lock = threading.Lock()

    # --- Low-Level JWT Utility ---

    def _base64url_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

    def _base64url_decode(self, s: str) -> bytes:
        rem = len(s) % 4
        if rem > 0:
            s += "=" * (4 - rem)
        return base64.urlsafe_b64decode(s.encode("utf-8"))

    def _sign_jwt(self, payload: dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        h_str = self._base64url_encode(json.dumps(header, separators=(",", ":")).encode())
        p_str = self._base64url_encode(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{h_str}.{p_str}".encode()
        sig = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
        sig_str = self._base64url_encode(sig)
        return f"{h_str}.{p_str}.{sig_str}"

    def _verify_jwt(self, token: str, check_blacklist: bool = True) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise TokenInvalidError("Malformed JWT structure")
        h_str, p_str, sig_str = parts
        signing_input = f"{h_str}.{p_str}".encode()
        expected_sig = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
        actual_sig = self._base64url_decode(sig_str)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise TokenInvalidError("Invalid token cryptographic signature")

        try:
            payload: dict[str, Any] = json.loads(self._base64url_decode(p_str).decode("utf-8"))
        except Exception as e:
            raise TokenInvalidError(f"Cannot parse token payload: {e}") from e

        # Expiration check
        exp = payload.get("exp", 0)
        if exp < time.time():
            raise TokenExpiredError("Token has expired")

        # Blacklist check
        if check_blacklist:
            jti = payload.get("jti")
            if jti and self.blacklist.is_jti_revoked(jti):
                raise TokenRevokedError("Token has been revoked")

        return payload

    # --- Dual Token Operations ---

    def issue_token_pair(
        self,
        sub: str | None = None,
        tenant_id: str = "default",
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
        family_id: str | None = None,
        generation: int = 1,
        user_id: str | None = None,
    ) -> TokenPair:
        """Issue a coordinated Access Token and Refresh Token pair."""
        effective_sub = user_id if user_id is not None else (sub or "anonymous")
        now = time.time()
        fam_id = family_id or f"fam-{uuid4().hex[:12]}"

        # 1. Access Token
        access_jti = f"acc-{uuid4().hex[:12]}"
        access_payload = {
            "sub": effective_sub,
            "tenant_id": tenant_id,
            "roles": roles or ["user"],
            "permissions": permissions or ["read", "write"],
            "iat": int(now),
            "exp": int(now + self.access_token_ttl),
            "jti": access_jti,
            "token_type": "access",
            "family_id": fam_id,
        }
        access_token = self._sign_jwt(access_payload)

        # 2. Refresh Token
        refresh_jti = f"ref-{uuid4().hex[:12]}"
        refresh_exp = now + self.refresh_token_ttl
        refresh_payload = {
            "sub": effective_sub,
            "tenant_id": tenant_id,
            "family_id": fam_id,
            "generation": generation,
            "iat": int(now),
            "exp": int(refresh_exp),
            "jti": refresh_jti,
            "token_type": "refresh",
        }
        refresh_token = self._sign_jwt(refresh_payload)

        # Record active refresh token
        with self._lock:
            record = RefreshTokenRecord(
                jti=refresh_jti,
                family_id=fam_id,
                sub=effective_sub,
                tenant_id=tenant_id,
                generation=generation,
                is_consumed=False,
                expires_at=refresh_exp,
            )
            self._refresh_records[refresh_jti] = record
            self._family_latest_generation[fam_id] = generation

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.access_token_ttl,
            refresh_expires_in=self.refresh_token_ttl,
        )

    def verify_access_token(self, access_token: str) -> dict[str, Any]:
        """Verify access token signature, expiry, revocation, and type."""
        payload = self._verify_jwt(access_token)
        if payload.get("token_type") != "access":
            raise TokenInvalidError("Expected token_type='access'")
        fam_id = payload.get("family_id")
        if fam_id and self.blacklist.is_family_revoked(fam_id):
            raise TokenRevokedError("Token family has been compromised and revoked")
        return payload

    def refresh(self, refresh_token: str) -> TokenPair:
        """Perform seamless token refresh with Token Rotation and Replay Attack Protection."""
        payload = self._verify_jwt(refresh_token, check_blacklist=False)
        if payload.get("token_type") != "refresh":
            raise TokenInvalidError("Expected token_type='refresh'")

        jti = payload.get("jti")
        family_id = payload.get("family_id")
        sub = payload.get("sub")
        tenant_id = payload.get("tenant_id")
        gen = payload.get("generation", 1)

        if not jti or not family_id or not sub or not tenant_id:
            raise TokenInvalidError("Refresh token missing required claims")

        with self._lock:
            # Check if entire family is already revoked
            if self.blacklist.is_family_revoked(family_id):
                raise TokenRevokedError(f"Token family [{family_id}] has been revoked (Token family compromised)")

            record = self._refresh_records.get(jti)
            if record is None:
                # Untracked token -> suspicious, revoke family
                self.blacklist.revoke_family(family_id)
                raise TokenReplayCompromisedError("Unrecognized refresh token; token family compromised")

            # REPLAY ATTACK DETECTION:
            # If the refresh token has ALREADY been consumed, it indicates an attacker is reusing a stolen token!
            if record.is_consumed:
                self.blacklist.revoke_family(family_id)
                raise TokenReplayCompromisedError(
                    f"Replay attack detected on consumed token [{jti}]! Family [{family_id}] invalidated."
                )

            if self.blacklist.is_jti_revoked(jti):
                raise TokenRevokedError("Token has been revoked")

            # Consume current token
            record.is_consumed = True
            # Blacklist this JTI so it cannot be used again
            self.blacklist.revoke_jti(jti, record.expires_at)

        # Issue new rotated token pair with incremented generation
        new_generation = gen + 1
        return self.issue_token_pair(
            sub=sub,
            tenant_id=tenant_id,
            family_id=family_id,
            generation=new_generation,
        )

    refresh_token_pair = refresh

    def revoke_token(self, token: str) -> None:
        """Explicitly revoke a token and add it to blacklist."""
        try:
            payload = self._verify_jwt(token)
            jti = payload.get("jti")
            exp = payload.get("exp", time.time() + 3600)
            if jti:
                self.blacklist.revoke_jti(jti, exp)
            fam_id = payload.get("family_id")
            if fam_id:
                self.blacklist.revoke_family(fam_id)
        except TokenError:
            pass

    def logout(self, access_token: str, refresh_token: str | None = None) -> None:
        """Logout user and revoke access and refresh tokens."""
        self.revoke_token(access_token)
        if refresh_token:
            self.revoke_token(refresh_token)


# ============================================================================
# Client Seamless Refresh Interceptor
# ============================================================================


class SeamlessRefreshClientInterceptor:
    """Client-side interceptor that automatically handles 401 TOKEN_EXPIRED by invoking refresh."""

    def __init__(
        self,
        auth_manager: DualTokenAuthManager | None = None,
        token_pair: TokenPair | None = None,
        get_access_token: Callable[[], str] | None = None,
        refresh_tokens: Callable[[], str] | None = None,
    ) -> None:
        self.auth_manager = auth_manager
        self.current_tokens = token_pair
        self._get_access_token = get_access_token
        self._refresh_tokens = refresh_tokens
        self._lock = threading.Lock()

    def execute_with_retry(self, request_fn: Callable[[dict[str, str]], Any]) -> Any:
        """Execute request and retry on 401 with refreshed token."""
        token = (
            self._get_access_token()
            if self._get_access_token
            else (self.current_tokens.access_token if self.current_tokens else "")
        )
        headers = {"Authorization": f"Bearer {token}"}
        res = request_fn(headers)
        if isinstance(res, dict) and res.get("status_code") == 401:
            if self._refresh_tokens:
                new_token = self._refresh_tokens()
            elif self.auth_manager and self.current_tokens:
                new_pair = self.auth_manager.refresh(self.current_tokens.refresh_token)
                self.current_tokens = new_pair
                new_token = new_pair.access_token
            else:
                return res
            new_headers = {"Authorization": f"Bearer {new_token}"}
            return request_fn(new_headers)
        return res

    def execute_request(self, api_caller: Any) -> Any:
        """Execute an API request, automatically refreshing tokens on 401 TOKEN_EXPIRED."""
        # Attempt request with current access token
        try:
            token = self._get_access_token() if self._get_access_token else (self.current_tokens.access_token if self.current_tokens else "")
            return api_caller(token)
        except Exception as exc:
            if "TOKEN_EXPIRED" in str(exc) or "expired" in str(exc).lower():
                logger.info("ClientInterceptor: Caught 401 TOKEN_EXPIRED. Initiating seamless refresh...")
                with self._lock:
                    # Refresh tokens
                    if self._refresh_tokens:
                        new_token = self._refresh_tokens()
                    elif self.auth_manager and self.current_tokens:
                        new_pair = self.auth_manager.refresh(self.current_tokens.refresh_token)
                        self.current_tokens = new_pair
                        new_token = new_pair.access_token
                    else:
                        raise
                    logger.info("ClientInterceptor: Tokens refreshed seamlessly. Replaying original request...")

                # Replay request with new access token
                return api_caller(new_token)
            raise
