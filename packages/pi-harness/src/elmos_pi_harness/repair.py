"""Verification-gated repair proposals; no unreviewed patch is applied."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairProposal:
    proposal_id: str
    failure_class: str
    target_paths: tuple[str, ...]
    patch_digest: str
    requires_approval: bool = True


def admit_repair(proposal: RepairProposal, *, verification_passed: bool, approved: bool) -> dict[str, object]:
    blockers = []
    if not proposal.target_paths:
        blockers.append("no_target_paths")
    if proposal.requires_approval and not approved:
        blockers.append("approval_required")
    if not verification_passed:
        blockers.append("verification_not_passed")
    return {"admitted": not blockers, "blockers": blockers, "proposal_id": proposal.proposal_id}
