#!/usr/bin/env python3
"""Evaluate externally produced Batch 30 evidence without creating trust material.

This entry point intentionally cannot generate keys, evidence, customer approvals,
or independent-review claims.  Every trust and evidence input must be mounted from
outside the repository.  Promotion remains dry-run unless ``--apply`` is supplied.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.batch30.certification_campaign import (  # noqa: E402
    CampaignError,
    evaluate_certification_campaign,
)
from scripts.batch30.promote_framework_certification import (  # noqa: E402
    PromotionError,
    promote,
)


class ExternalCampaignError(ValueError):
    """Raised when external certification authority boundaries are violated."""


def _external_file(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or resolved.is_symlink():
        raise ExternalCampaignError(f"{label} must be a real regular file")
    if resolved.is_relative_to(ROOT.resolve()):
        raise ExternalCampaignError(f"{label} must be mounted outside the repository")
    return resolved


def _external_directory(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_dir() or resolved.is_symlink():
        raise ExternalCampaignError(f"{label} must be a real directory")
    if resolved.is_relative_to(ROOT.resolve()):
        raise ExternalCampaignError(f"{label} must be mounted outside the repository")
    return resolved


def execute_campaign(
    *,
    pack_dir: Path,
    external_intake: Path,
    trust_store: Path,
    evidence_roots: Iterable[Path],
    campaign_path: Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Re-verify one externally executed campaign and optionally promote it."""

    pack = pack_dir.resolve(strict=True)
    if not pack.is_dir() or pack.is_symlink():
        raise ExternalCampaignError("pack_dir must be a real directory")
    campaign = (campaign_path or pack / "certification/p0-p11-campaign.json").resolve(
        strict=True
    )
    if not campaign.is_file() or campaign.is_symlink() or not campaign.is_relative_to(pack):
        raise ExternalCampaignError("campaign must be a real file inside the selected pack")

    intake = _external_file(external_intake, "external intake")
    trust = _external_file(trust_store, "trust store")
    external_roots = [
        _external_directory(path, f"external evidence root {index}")
        for index, path in enumerate(evidence_roots)
    ]
    if not external_roots:
        raise ExternalCampaignError("at least one external evidence root is required")

    roots = [pack, *external_roots]
    if apply:
        return promote(
            pack_dir=pack,
            campaign_path=campaign,
            intake_path=intake,
            trust_store=trust,
            evidence_roots=roots,
            apply=True,
        )

    result = evaluate_certification_campaign(
        pack_dir=pack,
        campaign_path=campaign,
        intake_path=intake,
        trust_store=trust,
        evidence_roots=roots,
    )
    return {
        **result,
        "apply_requested": False,
        "external_inputs_only": True,
        "certification_mutated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_dir", type=Path)
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--external-intake", type=Path, required=True)
    parser.add_argument("--trust-store", type=Path, required=True)
    parser.add_argument("--evidence-root", action="append", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = execute_campaign(
            pack_dir=args.pack_dir,
            campaign_path=args.campaign,
            external_intake=args.external_intake,
            trust_store=args.trust_store,
            evidence_roots=args.evidence_root,
            apply=args.apply,
        )
    except (CampaignError, ExternalCampaignError, PromotionError, OSError, ValueError) as exc:
        print(f"CAMPAIGN FAIL: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
