"""Exact repository-owned promotion metadata for installed Precision Skills."""

from __future__ import annotations

import hashlib


PROMOTION_METADATA = (
    'implementation_state: "VERIFIED"\n'
    'external_evidence_status: "LOCAL_EXECUTED"\n'
    'production_certification: "NOT_CERTIFIED"\n'
).encode("utf-8")


def normalized_promoted_skill(content: bytes, name: str) -> bytes:
    """Strip one exact frontmatter overlay and reject every partial variant."""

    name_marker = f"name: {name}\n".encode("utf-8")
    promoted_marker = name_marker + PROMOTION_METADATA
    frontmatter_end = content.find(b"\n---\n", 4)
    if (
        not content.startswith(b"---\n")
        or frontmatter_end == -1
        or content.count(name_marker) != 1
        or content.count(PROMOTION_METADATA) != 1
        or content.count(promoted_marker) != 1
        or content.find(promoted_marker) >= frontmatter_end
    ):
        raise ValueError(f"installed Skill promotion metadata mismatch: {name}")
    return content.replace(promoted_marker, name_marker, 1)


def promoted_skill_source_digest(content: bytes, name: str) -> str:
    return hashlib.sha256(normalized_promoted_skill(content, name)).hexdigest()
