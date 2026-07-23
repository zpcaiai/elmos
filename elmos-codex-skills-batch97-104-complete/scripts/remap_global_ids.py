#!/usr/bin/env python3
"""Generate a non-mutating global-ID allocation proposal."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--out")
    parser.add_argument("--authority")
    args = parser.parse_args()
    if args.start < 1:
        parser.error("--start must be positive")
    root = Path(args.root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    skills = manifest.get("skills", [])
    if len(skills) != 128 or any(skill.get("global_id") is not None for skill in skills):
        parser.error("package is not in the expected unassigned Batch-local state")
    mapping = {skill["id"]: f"PG{args.start + index:03d}" for index, skill in enumerate(skills)}
    status = "PROPOSED_UNAPPROVED"
    authority_ref = None
    if args.authority:
        authority = json.loads(Path(args.authority).read_text(encoding="utf-8"))
        digest = authority.get("existing_ids_digest")
        if (
            authority.get("status") != "APPROVED"
            or authority.get("namespace") != "elmos.global-pg"
            or authority.get("start") != args.start
            or authority.get("count") != 128
            or not isinstance(authority.get("approver"), str)
            or not authority["approver"].strip()
            or not isinstance(digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        ):
            parser.error("namespace authority is invalid or does not cover this allocation")
        status = "APPROVED_MAPPING_ONLY"
        authority_ref = digest
    result = {
        "schema_version": "elmos.global-id-allocation-proposal.v1",
        "package": manifest.get("package"),
        "source_namespace": "batch-local-product-closure",
        "status": status,
        "authority_ref": authority_ref,
        "mapping": mapping,
        "package_mutated": False,
    }
    rendered = json.dumps(result, indent=2) + "\n"
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists() and (output.is_symlink() or not output.is_file()):
            parser.error("output must be a regular file")
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
