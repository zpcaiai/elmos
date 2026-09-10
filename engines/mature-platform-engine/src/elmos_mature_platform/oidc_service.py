"""Enterprise OIDC Provider and Token Validation Service for Elmos Mature Platform."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from elmos_mature_platform.types import (
    JwtClaims,
    OidcTokenResult,
    RbacRule,
    TokenRevocationRecord,
)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = 4 - (len(s) % 4)
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s.encode("utf-8"))


class EnterpriseOidcProvider:
    """Enterprise OIDC Token Service with real key signing, JWKS, token revocation and RBAC."""

    def __init__(self, issuer: str = "https://auth.enterprise.elmos.io", key_id: str = "elmos-oidc-k1") -> None:
        self.issuer = issuer
        self.key_id = key_id
        self.revocation_registry: Dict[str, TokenRevocationRecord] = {}
        self.seen_jtis: Set[str] = set()
        self.rbac_policies: Dict[str, List[RbacRule]] = {}
        self.event_log: List[str] = []

        # Generate RSA private and public key via OpenSSL for standard compliance
        self._temp_dir = tempfile.TemporaryDirectory()
        self.private_key_path = os.path.join(self._temp_dir.name, "oidc_priv.pem")
        self.public_key_path = os.path.join(self._temp_dir.name, "oidc_pub.pem")
        self._generate_rsa_keys()
        self._init_default_rbac()

    def __del__(self) -> None:
        try:
            self._temp_dir.cleanup()
        except Exception:
            pass

    def _log(self, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        entry = f"[{ts}][OIDC-PROVIDER] {message}"
        self.event_log.append(entry)

    def _generate_rsa_keys(self) -> None:
        # Generate 2048-bit RSA key using openssl
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", self.private_key_path],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "rsa", "-pubout", "-in", self.private_key_path, "-out", self.public_key_path],
            check=True,
            capture_output=True,
        )
        self._log(f"Generated cryptographic RSA-2048 keypair for key_id={self.key_id}")

    def _init_default_rbac(self) -> None:
        """Configures enterprise RBAC rules."""
        self.rbac_policies["platform_admin"] = [
            RbacRule("platform_admin", ["*"], ["*"], tenant_bound=False),
        ]
        self.rbac_policies["tenant_operator"] = [
            RbacRule("tenant_operator", ["read", "write", "deploy", "failover", "reconcile"], ["deployment", "slo", "dr", "finops"], tenant_bound=True),
        ]
        self.rbac_policies["auditor"] = [
            RbacRule("auditor", ["read", "verify"], ["audit_log", "compliance", "evidence", "sbom"], tenant_bound=True),
        ]

    def get_jwks(self) -> Dict[str, Any]:
        """Exposes public JWKS metadata."""
        pub_pem = open(self.public_key_path, "r", encoding="utf-8").read()
        pub_fingerprint = hashlib.sha256(pub_pem.encode("utf-8")).hexdigest()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": self.key_id,
                    "x5t#S256": pub_fingerprint,
                    "pem": pub_pem,
                }
            ]
        }

    def mint_token(
        self,
        tenant_id: str,
        subject: str,
        roles: Optional[List[str]] = None,
        permissions: Optional[List[str]] = None,
        expires_in: int = 3600,
        audience: str = "https://api.enterprise.elmos.io",
    ) -> OidcTokenResult:
        """Mints an authentic RS256 JWT."""
        now = int(time.time())
        jti = str(uuid.uuid4())
        claims = JwtClaims(
            iss=self.issuer,
            sub=subject,
            aud=audience,
            exp=now + expires_in,
            nbf=now - 5,
            iat=now,
            jti=jti,
            tenant_id=tenant_id,
            roles=roles or ["tenant_operator"],
            permissions=permissions or ["read", "write"],
        )

        header = {"alg": "RS256", "typ": "JWT", "kid": self.key_id}
        h_json = json.dumps(header, separators=(",", ":")).encode("utf-8")
        c_dict = {
            "iss": claims.iss,
            "sub": claims.sub,
            "aud": claims.aud,
            "exp": claims.exp,
            "nbf": claims.nbf,
            "iat": claims.iat,
            "jti": claims.jti,
            "tenant_id": claims.tenant_id,
            "roles": claims.roles,
            "permissions": claims.permissions,
            "scope": claims.scope,
        }
        c_json = json.dumps(c_dict, separators=(",", ":")).encode("utf-8")

        payload_to_sign = f"{_b64url_encode(h_json)}.{_b64url_encode(c_json)}".encode("utf-8")

        # Sign using OpenSSL
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", self.private_key_path],
            input=payload_to_sign,
            check=True,
            capture_output=True,
        )
        sig_b64 = _b64url_encode(proc.stdout)
        jwt_token = f"{payload_to_sign.decode('utf-8')}.{sig_b64}"

        self._log(f"Minted OIDC RS256 token for tenant={tenant_id}, sub={subject}, jti={jti[:8]}...")
        return OidcTokenResult(token=jwt_token, expires_in=expires_in, claims=claims)

    def verify_token(self, token_str: str, expected_audience: Optional[str] = None) -> Tuple[bool, Optional[JwtClaims], str]:
        """Cryptographically verifies the JWT, expiration, and revocation list."""
        parts = token_str.split(".")
        if len(parts) != 3:
            return False, None, "E_MALFORMED_JWT: Token must consist of header.payload.signature"

        h_b64, c_b64, sig_b64 = parts
        try:
            h_data = json.loads(_b64url_decode(h_b64).decode("utf-8"))
            c_data = json.loads(_b64url_decode(c_b64).decode("utf-8"))
            sig_bytes = _b64url_decode(sig_b64)
        except Exception as exc:
            return False, None, f"E_DECODE_FAILED: {exc}"

        # Algorithm confusion protection
        if h_data.get("alg") != "RS256":
            return False, None, f"E_INVALID_ALG: Refusing token with alg={h_data.get('alg')}"

        # Verify signature via OpenSSL
        payload_bytes = f"{h_b64}.{c_b64}".encode("utf-8")
        with tempfile.NamedTemporaryFile("wb", delete=False) as sig_file:
            sig_file.write(sig_bytes)
            sig_file_path = sig_file.name

        try:
            res = subprocess.run(
                ["openssl", "dgst", "-sha256", "-verify", self.public_key_path, "-signature", sig_file_path],
                input=payload_bytes,
                capture_output=True,
            )
            if res.returncode != 0:
                return False, None, "E_SIGNATURE_INVALID: Cryptographic signature mismatch"
        finally:
            if os.path.exists(sig_file_path):
                os.remove(sig_file_path)

        now = int(time.time())
        # Check expiration
        if c_data.get("exp", 0) < now:
            return False, None, f"E_TOKEN_EXPIRED: Token expired at {c_data.get('exp')} (current={now})"

        # Check not before
        if c_data.get("nbf", 0) > now + 5:
            return False, None, f"E_TOKEN_NOT_YET_VALID: Valid from {c_data.get('nbf')}"

        # Check audience
        if expected_audience and c_data.get("aud") != expected_audience:
            return False, None, f"E_AUDIENCE_MISMATCH: Expected {expected_audience}, got {c_data.get('aud')}"

        # Check issuer
        if c_data.get("iss") != self.issuer:
            return False, None, f"E_ISSUER_MISMATCH: Expected {self.issuer}, got {c_data.get('iss')}"

        # Check revocation list
        jti = c_data.get("jti", "")
        if jti in self.revocation_registry:
            rev = self.revocation_registry[jti]
            return False, None, f"E_TOKEN_REVOKED: JTI {jti} revoked at {rev.revoked_at} (reason: {rev.reason})"

        claims = JwtClaims(
            iss=c_data["iss"],
            sub=c_data["sub"],
            aud=c_data["aud"],
            exp=c_data["exp"],
            nbf=c_data["nbf"],
            iat=c_data["iat"],
            jti=jti,
            tenant_id=c_data["tenant_id"],
            roles=c_data.get("roles", []),
            permissions=c_data.get("permissions", []),
            scope=c_data.get("scope", ""),
        )

        return True, claims, "OK: Validated"

    def revoke_token(self, jti: str, tenant_id: str, actor: str, reason: str = "Security revocation") -> None:
        """Revokes a specific token by JTI."""
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.revocation_registry[jti] = TokenRevocationRecord(
            jti=jti,
            revoked_at=now,
            tenant_id=tenant_id,
            reason=reason,
            actor=actor,
        )
        self._log(f"Token revoked: jti={jti[:8]}... tenant={tenant_id} by actor={actor}")

    def evaluate_access(
        self,
        claims: JwtClaims,
        action: str,
        resource_type: str,
        target_tenant_id: str,
    ) -> Tuple[bool, str]:
        """Zero-trust multi-tenant authorization evaluator."""
        # 1. Zero-tolerance cross-tenant access defense
        if claims.tenant_id != target_tenant_id and "platform_admin" not in claims.roles:
            self._log(f"SECURITY ALERT: Blocked cross-tenant access attempt by tenant={claims.tenant_id} to resource of tenant={target_tenant_id}")
            return False, f"E_CROSS_TENANT_VIOLATION: Actor tenant {claims.tenant_id} denied access to tenant {target_tenant_id}"

        # 2. RBAC rules evaluation
        for role in claims.roles:
            rules = self.rbac_policies.get(role, [])
            for rule in rules:
                action_allowed = "*" in rule.allowed_actions or action in rule.allowed_actions
                resource_allowed = "*" in rule.allowed_resources or resource_type in rule.allowed_resources
                if action_allowed and resource_allowed:
                    return True, f"OK: Authorized via role {role}"

        return False, f"E_FORBIDDEN: Insufficient permissions for action {action} on {resource_type}"
