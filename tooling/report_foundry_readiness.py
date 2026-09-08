#!/usr/bin/env python3
"""Write/check the exhaustive Foundry engineering inventory without executing Skills."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engines/knowledge-skill-model-foundry-engine"
sys.path.insert(0, str(ENGINE / "src"))

from elmos_foundry.readiness import build_readiness, render_markdown  # noqa: E402
from elmos_foundry.skills import load_compiled_catalog  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "docs/knowledge-skill-model-foundry",
    )
    args = parser.parse_args(argv)
    try:
        catalog_path = ENGINE / "catalog/compiled-catalog.json"
        snapshot = load_compiled_catalog(catalog_path)
        raw = catalog_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != snapshot.content_sha256:
            raise ValueError("catalog changed during report generation")
        report = build_readiness(json.loads(raw))
        outputs = {
            "IMPLEMENTATION_MATRIX.json": json.dumps(
                report, indent=2, sort_keys=True, ensure_ascii=False,
            ) + "\n",
            "IMPLEMENTATION_MATRIX.md": render_markdown(report),
        }
        stale = []
        for name, text in outputs.items():
            path = args.output_dir / name
            content = text.encode("utf-8")
            if args.write:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            elif not path.is_file() or path.read_bytes() != content:
                stale.append(name)
        if stale:
            print("Foundry implementation inventory missing or stale: " + ", ".join(stale), file=sys.stderr)
            return 1
        summary = report["summary"]
        print(
            f"Foundry inventory {'written' if args.write else 'verified'}: "
            f"{summary['atomic_skills']} exact Skills, "
            f"{summary['local_semantic_handlers']} bounded LOCAL, "
            f"{summary['native_semantic_programs']} exact NATIVE, "
            f"{summary['prepare_only']} PREPARE_ONLY; NOT_CERTIFIED"
        )
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Foundry implementation inventory failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
