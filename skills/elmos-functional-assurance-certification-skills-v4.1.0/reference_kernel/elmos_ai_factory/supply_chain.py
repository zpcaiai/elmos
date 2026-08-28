from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PackageTrustInput:
    signature_verified: bool
    publisher_trusted: bool
    provenance_complete: bool
    reproducible_build: bool
    permission_expansions: tuple[str,...]
    observed_undeclared_behaviors: tuple[str,...]
    revoked: bool=False


def trust_decision(value: PackageTrustInput) -> tuple[str,tuple[str,...]]:
    reasons=[]
    if value.revoked: reasons.append('publisher-or-artifact-revoked')
    if not value.signature_verified: reasons.append('signature-unverified')
    if not value.publisher_trusted: reasons.append('publisher-untrusted')
    if not value.provenance_complete: reasons.append('provenance-incomplete')
    if value.permission_expansions: reasons.append('permission-expansion')
    if value.observed_undeclared_behaviors: reasons.append('undeclared-behavior')
    if reasons:return 'BLOCKED',tuple(reasons)
    return ('TRUSTED' if value.reproducible_build else 'BOUNDED'),(() if value.reproducible_build else ('build-not-reproduced',))
