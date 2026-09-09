"""Organization self-service and OIDC binding for hosted generation.

Tenant and actor always come from a verified identity session. A configured
single-tenant organization id is a production defect, not a fallback.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROLES = ("VIEWER", "DEVELOPER", "MAINTAINER", "OPERATOR", "APPROVER", "TENANT_ADMIN")
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")


class IdentityError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def require_https_issuer(issuer: str, *, allow_loopback: bool = False) -> str:
    parsed = urlparse(issuer)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise IdentityError("OIDC_ISSUER_NOT_HTTPS")
    if parsed.hostname in {"127.0.0.1", "localhost", "::1"} and not allow_loopback:
        raise IdentityError("OIDC_ISSUER_LOOPBACK_FORBIDDEN")
    return issuer.rstrip("/")


def require_oidc_configuration(environment: dict[str, str]) -> dict[str, str]:
    required = (
        "ELMOS_OIDC_ISSUER_URI",
        "ELMOS_OIDC_AUTHORIZATION_ENDPOINT",
        "ELMOS_OIDC_TOKEN_ENDPOINT",
        "ELMOS_OIDC_JWKS_URI",
        "ELMOS_OIDC_CLIENT_ID",
        "ELMOS_OIDC_CLIENT_SECRET",
        "ELMOS_OIDC_REDIRECT_URI",
        "ELMOS_OIDC_AUDIENCE",
    )
    missing = [name for name in required if not environment.get(name)]
    if missing:
        raise IdentityError("OIDC_NOT_CONFIGURED:" + ",".join(missing))
    allow_loopback = environment.get("ELMOS_OIDC_ALLOW_LOOPBACK") == "true"
    issuer = require_https_issuer(
        environment["ELMOS_OIDC_ISSUER_URI"],
        allow_loopback=allow_loopback,
    )
    for name in (
        "ELMOS_OIDC_AUTHORIZATION_ENDPOINT",
        "ELMOS_OIDC_TOKEN_ENDPOINT",
        "ELMOS_OIDC_JWKS_URI",
        "ELMOS_OIDC_REDIRECT_URI",
    ):
        require_https_issuer(environment[name], allow_loopback=allow_loopback)
    if environment.get("ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID"):
        raise IdentityError("TRUSTED_SINGLE_TENANT_FORBIDDEN")
    return {
        "issuer": issuer,
        "client_id": environment["ELMOS_OIDC_CLIENT_ID"],
        "audience": environment["ELMOS_OIDC_AUDIENCE"],
    }


@dataclass
class Membership:
    subject: str
    email: str
    role: str
    joined_at: int


@dataclass
class Organization:
    organization_id: str
    name: str
    created_by: str
    created_at: int
    members: dict[str, Membership] = field(default_factory=dict)
    invitations: dict[str, dict[str, Any]] = field(default_factory=dict)


class OrganizationDirectory:
    def __init__(self) -> None:
        self.organizations: dict[str, Organization] = {}
        self.by_subject: dict[str, set[str]] = {}

    def provision(
        self,
        *,
        name: str,
        subject: str,
        email: str,
        now: int | None = None,
    ) -> Organization:
        if not IDENTITY.match(subject) or not EMAIL.match(email):
            raise IdentityError("IDENTITY_SUBJECT_INVALID")
        if not re.match(r"^[A-Za-z][A-Za-z0-9 .-]{1,80}$", name):
            raise IdentityError("ORGANIZATION_NAME_INVALID")
        observed = int(now if now is not None else time.time())
        organization = Organization(
            organization_id=f"org-{uuid.uuid4()}",
            name=name,
            created_by=subject,
            created_at=observed,
        )
        organization.members[subject] = Membership(
            subject=subject,
            email=email,
            role="TENANT_ADMIN",
            joined_at=observed,
        )
        self.organizations[organization.organization_id] = organization
        self.by_subject.setdefault(subject, set()).add(organization.organization_id)
        return organization

    def invite(
        self,
        organization_id: str,
        *,
        actor: str,
        email: str,
        role: str,
        now: int | None = None,
    ) -> dict[str, Any]:
        organization = self._require(organization_id)
        membership = organization.members.get(actor)
        if membership is None or membership.role != "TENANT_ADMIN":
            raise IdentityError("ORGANIZATION_ADMIN_REQUIRED")
        if role not in ROLES or role == "TENANT_ADMIN":
            raise IdentityError("ORGANIZATION_ROLE_INVALID")
        if not EMAIL.match(email):
            raise IdentityError("IDENTITY_EMAIL_INVALID")
        token = f"inv-{uuid.uuid4()}"
        invitation = {
            "token": token,
            "email": email,
            "role": role,
            "expires_at": int(now if now is not None else time.time()) + 7 * 24 * 3600,
        }
        organization.invitations[token] = invitation
        return invitation

    def accept(
        self,
        token: str,
        *,
        subject: str,
        email: str,
        now: int | None = None,
    ) -> Organization:
        observed = int(now if now is not None else time.time())
        for organization in self.organizations.values():
            invitation = organization.invitations.get(token)
            if invitation is None:
                continue
            if invitation["expires_at"] <= observed:
                raise IdentityError("ORGANIZATION_INVITATION_EXPIRED")
            if invitation["email"] != email:
                raise IdentityError("ORGANIZATION_INVITATION_EMAIL_MISMATCH")
            organization.members[subject] = Membership(
                subject=subject,
                email=email,
                role=invitation["role"],
                joined_at=observed,
            )
            del organization.invitations[token]
            self.by_subject.setdefault(subject, set()).add(organization.organization_id)
            return organization
        raise IdentityError("ORGANIZATION_INVITATION_NOT_FOUND")

    def authorize_generation(self, organization_id: str, subject: str) -> Membership:
        organization = self._require(organization_id)
        membership = organization.members.get(subject)
        if membership is None:
            raise IdentityError("ORGANIZATION_MEMBERSHIP_REQUIRED")
        if membership.role in {"VIEWER"}:
            raise IdentityError("ORGANIZATION_ROLE_CANNOT_GENERATE")
        return membership

    def _require(self, organization_id: str) -> Organization:
        organization = self.organizations.get(organization_id)
        if organization is None:
            raise IdentityError("ORGANIZATION_NOT_FOUND")
        return organization

    def dump(self, path: Path) -> None:
        payload = {
            organization_id: {
                "name": organization.name,
                "created_by": organization.created_by,
                "members": {
                    subject: {
                        "email": member.email,
                        "role": member.role,
                        "joined_at": member.joined_at,
                    }
                    for subject, member in organization.members.items()
                },
            }
            for organization_id, organization in self.organizations.items()
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
