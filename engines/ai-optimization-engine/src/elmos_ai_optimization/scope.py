"""Scope resolution and security boundary enforcement for ao.v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .contracts import (
    RevisionBinding,
    ScopeDeniedError,
    StaleVersionError,
    TrustedScope,
)


@dataclass(frozen=True)
class Grant:
    """Security grant for a repository."""
    tenant: str
    repository: str
    allowed_principals: frozenset[str]
    current_generation: str


class HostAuthority:
    """Simulated host authority store for tenant and repository permissions."""

    def __init__(self) -> None:
        # (tenant, repository) -> Grant
        self._grants: dict[tuple[str, str], Grant] = {}
        # tenant -> current acl_epoch
        self._acl_epochs: dict[str, int] = {}
        # (tenant, principal) -> session valid bool
        self._sessions: set[tuple[str, str, str]] = set()

    def register_grant(self, tenant: str, repository: str, principals: Sequence[str], generation: str = "gen-1") -> None:
        self._grants[(tenant, repository)] = Grant(
            tenant=tenant,
            repository=repository,
            allowed_principals=frozenset(principals),
            current_generation=generation,
        )
        if tenant not in self._acl_epochs:
            self._acl_epochs[tenant] = 1

    def create_session(self, tenant: str, principal: str, token: str) -> None:
        self._sessions.add((tenant, principal, token))

    def revoke_session(self, tenant: str, principal: str, token: str) -> None:
        self._sessions.discard((tenant, principal, token))

    def bump_acl_epoch(self, tenant: str) -> int:
        cur = self._acl_epochs.get(tenant, 1)
        self._acl_epochs[tenant] = cur + 1
        return self._acl_epochs[tenant]

    def get_acl_epoch(self, tenant: str) -> int:
        return self._acl_epochs.get(tenant, 1)

    def is_session_valid(self, tenant: str, principal: str, token: str) -> bool:
        return (tenant, principal, token) in self._sessions

    def get_grant(self, tenant: str, repository: str) -> Grant | None:
        return self._grants.get((tenant, repository))


class ScopeResolver:
    """Host ScopeResolver enforcing tenant isolation and Cartesian safety."""

    def __init__(self, authority: HostAuthority) -> None:
        self.authority = authority

    def resolve(
        self,
        tenant: str,
        principal: str,
        session_token: str,
        requested_revisions: Sequence[tuple[str, str] | tuple[str, str, str]],
    ) -> TrustedScope:
        """Resolve session and revision pairs into a TrustedScope.
        
        revisions argument must be tuples of (repository, snapshot) or (repository, snapshot, generation).
        Cartesian products across repositories and snapshots are strictly rejected.
        """
        if not self.authority.is_session_valid(tenant, principal, session_token):
            raise ScopeDeniedError(f"Invalid or revoked session for principal {principal}")

        if not requested_revisions:
            raise ScopeDeniedError("Requested revisions cannot be empty")

        acl_epoch = self.authority.get_acl_epoch(tenant)
        seen_repos: set[str] = set()
        resolved: list[RevisionBinding] = []

        for item in requested_revisions:
            if len(item) == 2:
                repo, snapshot = item
                gen = None
            elif len(item) == 3:
                repo, snapshot, gen = item
            else:
                raise ScopeDeniedError(f"Invalid revision tuple: {item}")

            if repo in seen_repos:
                raise ScopeDeniedError(f"Duplicate repository requested in scope: {repo}")
            seen_repos.add(repo)

            grant = self.authority.get_grant(tenant, repo)
            if grant is None:
                raise ScopeDeniedError(f"No grant for repository {repo} in tenant {tenant}")

            if principal not in grant.allowed_principals:
                raise ScopeDeniedError(f"Principal {principal} is not authorized for repository {repo}")

            expected_gen = grant.current_generation
            if gen is not None and gen != expected_gen:
                raise StaleVersionError(f"Stale generation for {repo}: requested {gen}, current {expected_gen}")

            resolved.append(
                RevisionBinding(
                    repository=repo,
                    snapshot=snapshot,
                    generation=expected_gen,
                )
            )

        return TrustedScope(
            tenant=tenant,
            principal=principal,
            acl_epoch=acl_epoch,
            security_context_ref=f"ctx-{tenant}-{principal}-{acl_epoch}",
            revisions=tuple(resolved),
        )

    def revalidate(self, scope: TrustedScope) -> None:
        """Verify that the TrustedScope has not expired or had its permissions revoked."""
        current_epoch = self.authority.get_acl_epoch(scope.tenant)
        if scope.acl_epoch != current_epoch:
            raise ScopeDeniedError(f"Scope stale: acl_epoch {scope.acl_epoch} != current {current_epoch}")

        for r in scope.revisions:
            grant = self.authority.get_grant(scope.tenant, r.repository)
            if grant is None or scope.principal not in grant.allowed_principals:
                raise ScopeDeniedError(f"Permission revoked for {r.repository}")
            if grant.current_generation != r.generation:
                raise StaleVersionError(f"Generation changed for {r.repository}")
