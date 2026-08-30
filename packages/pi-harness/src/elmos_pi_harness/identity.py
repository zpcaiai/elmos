"""OIDC and mTLS identity binding with no trusted caller-supplied tenant header."""

from __future__ import annotations

import re
import ssl
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .canonical import require_nonempty, require_uuid
from .models import PolicyDeniedError


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    tenant_id: str
    actor_id: str
    subject: str
    issuer: str
    authentication_methods: frozenset[str]
    project_ids: frozenset[str] = frozenset()
    roles: frozenset[str] = frozenset()
    certificate_fingerprint: str | None = None

    def __post_init__(self) -> None:
        require_uuid(self.tenant_id, "tenant_id")
        require_nonempty(self.actor_id, "actor_id", 256)
        require_nonempty(self.subject, "subject", 512)
        require_nonempty(self.issuer, "issuer", 512)
        if not self.authentication_methods:
            raise ValueError("authentication_methods cannot be empty")
        for project_id in self.project_ids:
            require_uuid(project_id, "project_id")

    def assert_project(self, project_id: str) -> None:
        project_id = require_uuid(project_id, "project_id")
        if self.project_ids and project_id not in self.project_ids:
            raise PolicyDeniedError("identity is not bound to the requested project")


class JWTDecoder(Protocol):
    def decode(self, token: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class OIDCConfig:
    issuer: str
    audience: str
    jwks_url: str
    tenant_claim: str = "tenant_id"
    project_claim: str = "project_ids"
    actor_claim: str = "preferred_username"
    role_claim: str = "roles"
    algorithms: tuple[str, ...] = ("RS256", "ES256")
    max_token_age_seconds: int = 3600
    jwks_ca_file: str | None = None
    jwks_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        require_nonempty(self.issuer, "issuer", 512)
        require_nonempty(self.audience, "audience", 512)
        require_nonempty(self.jwks_url, "jwks_url", 1024)
        if not self.issuer.startswith("https://"):
            raise ValueError("issuer must use HTTPS")
        if not self.jwks_url.startswith("https://"):
            raise ValueError("jwks_url must use HTTPS")
        if self.jwks_ca_file is not None:
            ca_path = Path(self.jwks_ca_file)
            if not ca_path.is_absolute() or ca_path.is_symlink() or not ca_path.is_file():
                raise ValueError(
                    "jwks_ca_file must be an absolute regular non-symlink file"
                )
            object.__setattr__(self, "jwks_ca_file", str(ca_path.resolve(strict=True)))
        if not 1 <= self.jwks_timeout_seconds <= 60:
            raise ValueError("jwks_timeout_seconds must be between 1 and 60")
        if not self.algorithms or any(
            value not in {"RS256", "RS384", "RS512", "ES256", "ES384"}
            for value in self.algorithms
        ):
            raise ValueError("OIDC algorithms must be an explicit asymmetric allowlist")
        if self.max_token_age_seconds < 60:
            raise ValueError("max_token_age_seconds is too small")


class PyJWTDecoder:
    """Real JWKS-backed JWT decoder, loaded only with the ``identity`` extra."""

    def __init__(self, config: OIDCConfig) -> None:
        try:
            import jwt
        except (
            ImportError
        ) as exc:  # pragma: no cover - depends on optional production extra
            raise RuntimeError(
                "PyJWT is required; install elmos-pi-harness[identity]"
            ) from exc
        self._jwt = jwt
        self._config = config
        tls_context = ssl.create_default_context(cafile=config.jwks_ca_file)
        tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
        tls_context.verify_mode = ssl.CERT_REQUIRED
        tls_context.check_hostname = True
        tls_context.options |= ssl.OP_NO_COMPRESSION
        self._jwk_client = jwt.PyJWKClient(
            config.jwks_url,
            cache_keys=True,
            lifespan=300,
            timeout=config.jwks_timeout_seconds,
            ssl_context=tls_context,
        )

    def decode(self, token: str) -> Mapping[str, Any]:
        key = self._jwk_client.get_signing_key_from_jwt(token).key
        claims = self._jwt.decode(
            token,
            key,
            algorithms=list(self._config.algorithms),
            audience=self._config.audience,
            issuer=self._config.issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
        if not isinstance(claims, Mapping):
            raise ValueError("OIDC token claims must be an object")
        return dict(claims)


class OIDCAuthenticator:
    def __init__(self, config: OIDCConfig, decoder: JWTDecoder | None = None) -> None:
        self.config = config
        self.decoder = decoder or PyJWTDecoder(config)

    def authenticate(self, bearer_token: str) -> AuthenticatedPrincipal:
        token = require_nonempty(bearer_token, "bearer_token", 16_384)
        claims = dict(self.decoder.decode(token))
        now = int(datetime.now(timezone.utc).timestamp())
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        if not isinstance(issued_at, (int, float)) or not isinstance(
            expires_at, (int, float)
        ):
            raise PolicyDeniedError("OIDC token is missing numeric iat/exp claims")
        if (
            issued_at > now + 60
            or expires_at <= now
            or now - issued_at > self.config.max_token_age_seconds
        ):
            raise PolicyDeniedError("OIDC token is expired, future-issued, or too old")
        if claims.get("iss") != self.config.issuer:
            raise PolicyDeniedError("OIDC issuer mismatch")
        audience = claims.get("aud")
        audiences = {audience} if isinstance(audience, str) else set(audience or [])
        if self.config.audience not in audiences:
            raise PolicyDeniedError("OIDC audience mismatch")
        tenant_id = require_uuid(
            claims.get(self.config.tenant_claim), self.config.tenant_claim
        )
        subject = require_nonempty(claims.get("sub"), "sub", 512)
        actor_value = claims.get(self.config.actor_claim) or subject
        actor_id = require_nonempty(actor_value, self.config.actor_claim, 256)
        projects = _string_sequence(
            claims.get(self.config.project_claim), self.config.project_claim
        )
        if not projects:
            raise PolicyDeniedError("OIDC identity has no project bindings")
        roles = _string_sequence(
            claims.get(self.config.role_claim), self.config.role_claim
        )
        return AuthenticatedPrincipal(
            tenant_id=tenant_id,
            actor_id=actor_id,
            subject=subject,
            issuer=self.config.issuer,
            authentication_methods=frozenset({"oidc"}),
            project_ids=frozenset(
                require_uuid(value, "project_id") for value in projects
            ),
            roles=frozenset(roles),
        )


@dataclass(frozen=True)
class CertificateIdentity:
    spiffe_uri: str
    not_before: datetime
    not_after: datetime
    serial_number: int
    fingerprint_sha256: str


class CertificateDecoder(Protocol):
    def decode(self, certificate_der: bytes) -> CertificateIdentity: ...


class CryptographyCertificateDecoder:
    def decode(self, certificate_der: bytes) -> CertificateIdentity:
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes
        except (
            ImportError
        ) as exc:  # pragma: no cover - depends on optional production extra
            raise RuntimeError(
                "cryptography is required; install elmos-pi-harness[identity]"
            ) from exc
        certificate = x509.load_der_x509_certificate(certificate_der)
        uris = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value.get_values_for_type(x509.UniformResourceIdentifier)
        spiffe = [value for value in uris if value.startswith("spiffe://")]
        if len(spiffe) != 1:
            raise PolicyDeniedError(
                "mTLS certificate must contain exactly one SPIFFE URI SAN"
            )
        if hasattr(certificate, "not_valid_before_utc"):
            not_before = certificate.not_valid_before_utc
            not_after = certificate.not_valid_after_utc
        else:  # pragma: no cover - compatibility with older cryptography
            not_before = certificate.not_valid_before.replace(tzinfo=timezone.utc)
            not_after = certificate.not_valid_after.replace(tzinfo=timezone.utc)
        return CertificateIdentity(
            spiffe[0],
            not_before,
            not_after,
            certificate.serial_number,
            certificate.fingerprint(hashes.SHA256()).hex(),
        )


class CRLRevocationChecker:
    """Fail-closed CRL serial checker; OpenSSL validates CRL signatures in TLS."""

    def __init__(self, paths: Sequence[Path]) -> None:
        if not paths:
            raise ValueError("at least one CRL path is required")
        try:
            from cryptography import x509
        except ImportError as exc:  # pragma: no cover - optional production extra
            raise RuntimeError(
                "cryptography is required; install elmos-pi-harness[identity]"
            ) from exc
        now = datetime.now(timezone.utc)
        revoked: set[int] = set()
        for path in paths:
            if not path.is_absolute() or not path.is_file() or path.is_symlink():
                raise PolicyDeniedError("CRL path must be an absolute regular file")
            raw = path.read_bytes()
            crl = (
                x509.load_pem_x509_crl(raw)
                if raw.lstrip().startswith(b"-----BEGIN")
                else x509.load_der_x509_crl(raw)
            )
            next_update = getattr(crl, "next_update_utc", None)
            last_update = getattr(crl, "last_update_utc", None)
            if (
                next_update is None
                or last_update is None
                or not (last_update <= now < next_update)
            ):
                raise PolicyDeniedError("CRL is stale or outside its validity interval")
            revoked.update(item.serial_number for item in crl)
        self._revoked = frozenset(revoked)

    def __call__(self, serial_number: int, _fingerprint: str) -> bool:
        return serial_number in self._revoked


SPIFFE_PATTERN = re.compile(
    r"^spiffe://(?P<trust_domain>[a-z0-9.-]+)/tenant/(?P<tenant>[0-9a-fA-F-]{36})/workload/(?P<actor>[A-Za-z0-9._:@/-]{1,256})$"
)


class MTLSAuthenticator:
    def __init__(
        self,
        trust_domain: str,
        *,
        decoder: CertificateDecoder | None = None,
        revocation_checker: Callable[[int, str], bool] | None = None,
    ) -> None:
        self.trust_domain = require_nonempty(trust_domain, "trust_domain", 253).lower()
        self.decoder = decoder or CryptographyCertificateDecoder()
        if revocation_checker is None:
            raise ValueError("a fail-closed certificate revocation checker is required")
        self.revocation_checker = revocation_checker

    def authenticate(
        self, certificate_der: bytes, *, transport_chain_verified: bool
    ) -> AuthenticatedPrincipal:
        if not transport_chain_verified:
            raise PolicyDeniedError("mTLS transport chain was not verified")
        if not certificate_der:
            raise PolicyDeniedError("client certificate is required")
        identity = self.decoder.decode(certificate_der)
        now = datetime.now(timezone.utc)
        if identity.not_before > now or identity.not_after <= now:
            raise PolicyDeniedError("mTLS certificate is not currently valid")
        if self.revocation_checker(identity.serial_number, identity.fingerprint_sha256):
            raise PolicyDeniedError("mTLS certificate has been revoked")
        match = SPIFFE_PATTERN.fullmatch(identity.spiffe_uri)
        if not match or match.group("trust_domain").lower() != self.trust_domain:
            raise PolicyDeniedError(
                "mTLS SPIFFE identity is outside the configured trust domain"
            )
        tenant_id = require_uuid(match.group("tenant"), "spiffe tenant")
        actor_id = require_nonempty(match.group("actor"), "spiffe workload", 256)
        return AuthenticatedPrincipal(
            tenant_id=tenant_id,
            actor_id=actor_id,
            subject=identity.spiffe_uri,
            issuer="spiffe://" + self.trust_domain,
            authentication_methods=frozenset({"mtls"}),
            certificate_fingerprint="sha256:" + identity.fingerprint_sha256,
        )


def bind_oidc_and_mtls(
    oidc: AuthenticatedPrincipal, mtls: AuthenticatedPrincipal
) -> AuthenticatedPrincipal:
    if oidc.tenant_id != mtls.tenant_id:
        raise PolicyDeniedError("OIDC and mTLS tenant identities do not match")
    return AuthenticatedPrincipal(
        tenant_id=oidc.tenant_id,
        actor_id=oidc.actor_id,
        subject=oidc.subject,
        issuer=oidc.issuer,
        authentication_methods=oidc.authentication_methods
        | mtls.authentication_methods,
        project_ids=oidc.project_ids,
        roles=oidc.roles,
        certificate_fingerprint=mtls.certificate_fingerprint,
    )


class HTTPCompositeAuthenticator:
    """Adapter used by the built-in HTTPS server after TLS chain validation."""

    def __init__(self, oidc: OIDCAuthenticator, mtls: MTLSAuthenticator) -> None:
        self.oidc = oidc
        self.mtls = mtls

    def authenticate(
        self,
        headers: Mapping[str, str],
        certificate_der: bytes | None,
        *,
        transport_chain_verified: bool,
    ) -> AuthenticatedPrincipal:
        authorization = headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise PolicyDeniedError("OIDC bearer token is required")
        oidc_principal = self.oidc.authenticate(authorization[7:])
        mtls_principal = self.mtls.authenticate(
            certificate_der or b"", transport_chain_verified=transport_chain_verified
        )
        principal = bind_oidc_and_mtls(oidc_principal, mtls_principal)
        # Legacy context headers are never authoritative. If a proxy still
        # sends them, mismatch is rejected to prevent confused-deputy bugs.
        header_tenant = headers.get("X-Tenant-Id")
        if (
            header_tenant
            and require_uuid(header_tenant, "X-Tenant-Id") != principal.tenant_id
        ):
            raise PolicyDeniedError(
                "caller tenant header conflicts with authenticated identity"
            )
        header_actor = headers.get("X-Actor-Id")
        if header_actor and header_actor != principal.actor_id:
            raise PolicyDeniedError(
                "caller actor header conflicts with authenticated identity"
            )
        return principal


def _string_sequence(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values: Sequence[Any] = (value,)
    elif isinstance(value, Sequence):
        values = value
    else:
        raise PolicyDeniedError(f"{field_name} must be a string or string array")
    return tuple(require_nonempty(item, field_name, 256) for item in values)
