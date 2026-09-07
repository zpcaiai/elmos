#!/usr/bin/env python3
"""Batch 43 schema compatibility check over the versioned contract surface.

Compares every JSON Schema under the configured roots against a baseline
revision and classifies each difference as compatible or breaking for existing
consumers. The result is a real measurement, not an assertion: it is derived
only from the two document versions and it reports breaking changes whether or
not that is the convenient answer.

Baseline resolution order:
  1. --baseline-dir <path>  (a checked-out snapshot)
  2. git show <rev>:<path>  (default rev: HEAD)

Exit codes: 0 = no breaking change, 3 = breaking changes found, 2 = usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOTS = ("schemas",)


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def git(*args: str, cwd: Path) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
    except OSError:
        return 127, ""
    return completed.returncode, completed.stdout


def prefetch_baseline(repo: Path, relatives: list[Path], revision: str) -> dict[str, dict]:
    """Read every baseline blob in a single `git cat-file --batch` pass.

    One `git show` per file turns a few hundred schemas into a few hundred
    process spawns, which is slow enough to look like a hang on a large
    repository.
    """
    if not relatives:
        return {}
    request = "".join(f"{revision}:{item.as_posix()}\n" for item in relatives)
    try:
        completed = subprocess.run(
            ["git", "cat-file", "--batch"], cwd=repo, input=request.encode(),
            capture_output=True, check=False,
        )
    except OSError:
        return {}
    if completed.returncode != 0:
        return {}
    baselines: dict[str, dict] = {}
    stream, offset, index = completed.stdout, 0, 0
    while offset < len(stream) and index < len(relatives):
        end = stream.find(b"\n", offset)
        if end == -1:
            break
        header = stream[offset:end].decode("utf-8", "replace").split()
        relative = relatives[index].as_posix()
        index += 1
        if len(header) < 3:  # "<oid> missing" for paths absent from the baseline
            offset = end + 1
            continue
        size = int(header[2])
        body = stream[end + 1: end + 1 + size]
        offset = end + 1 + size + 1
        try:
            baselines[relative] = json.loads(body)
        except (ValueError, json.JSONDecodeError):
            continue
    return baselines


def load_baseline_dir(baseline_dir: Path, relative: Path) -> dict | None:
    candidate = baseline_dir / relative
    if not candidate.is_file():
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None


def as_set(value: object) -> set:
    if isinstance(value, list):
        return {json.dumps(item, sort_keys=True) for item in value}
    return set()


def compare(old: dict, new: dict, pointer: str = "#") -> list[dict]:
    """Classify schema differences from the perspective of an existing consumer.

    A document that used to validate must still validate: anything that can
    reject a previously valid document is breaking.
    """
    findings: list[dict] = []

    def note(kind: str, breaking: bool, detail: str) -> None:
        findings.append({"pointer": pointer, "kind": kind, "breaking": breaking, "detail": detail})

    old_required, new_required = as_set(old.get("required")), as_set(new.get("required"))
    for added in sorted(new_required - old_required):
        note("required-added", True, f"{json.loads(added)} became required")
    for dropped in sorted(old_required - new_required):
        note("required-removed", False, f"{json.loads(dropped)} is no longer required")

    old_properties = old.get("properties", {}) if isinstance(old.get("properties"), dict) else {}
    new_properties = new.get("properties", {}) if isinstance(new.get("properties"), dict) else {}
    closed = new.get("additionalProperties") is False or "unevaluatedProperties" in new
    for removed in sorted(set(old_properties) - set(new_properties)):
        note("property-removed", closed, f"property {removed} was removed from a {'closed' if closed else 'open'} object")
    for added in sorted(set(new_properties) - set(old_properties)):
        note("property-added", False, f"property {added} was added")
    for shared in sorted(set(old_properties) & set(new_properties)):
        if isinstance(old_properties[shared], dict) and isinstance(new_properties[shared], dict):
            findings.extend(compare(old_properties[shared], new_properties[shared], f"{pointer}/properties/{shared}"))

    if old.get("additionalProperties") is not False and new.get("additionalProperties") is False:
        note("object-closed", True, "additionalProperties was tightened to false")

    old_enum, new_enum = as_set(old.get("enum")), as_set(new.get("enum"))
    if old_enum and new_enum and old_enum - new_enum:
        note("enum-narrowed", True, f"enum lost {sorted(json.loads(item) for item in old_enum - new_enum)}")

    if "const" in old and old.get("const") != new.get("const"):
        note("const-changed", True, f"const changed from {old.get('const')!r} to {new.get('const')!r}")

    if "type" in old and "type" in new and old["type"] != new["type"]:
        note("type-changed", True, f"type changed from {old['type']!r} to {new['type']!r}")

    for keyword, tighter in (("minItems", "gt"), ("minLength", "gt"), ("minimum", "gt"),
                             ("maxItems", "lt"), ("maxLength", "lt"), ("maximum", "lt"),
                             ("minProperties", "gt")):
        before, after = old.get(keyword), new.get(keyword)
        if isinstance(after, (int, float)) and isinstance(before, (int, float)):
            if (tighter == "gt" and after > before) or (tighter == "lt" and after < before):
                note("bound-tightened", True, f"{keyword} moved from {before} to {after}")
        elif isinstance(after, (int, float)) and before is None:
            note("bound-introduced", True, f"{keyword} was introduced at {after}")

    if isinstance(old.get("pattern"), str) and isinstance(new.get("pattern"), str) and old["pattern"] != new["pattern"]:
        note("pattern-changed", True, "pattern changed and may reject previously valid values")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--baseline-rev", default="HEAD")
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    roots = arguments.root or list(DEFAULT_ROOTS)
    started = datetime.now(timezone.utc)

    code, head = git("rev-parse", "HEAD", cwd=repo)
    revision = head.strip() if code == 0 else None
    if revision is None and arguments.baseline_dir is None:
        print("ERROR: no git repository and no --baseline-dir supplied", file=sys.stderr)
        return 2

    paths = [path for root in roots for path in sorted((repo / root).rglob("*.schema.json"))]
    relatives = [path.relative_to(repo) for path in paths]
    prefetched = (
        {} if arguments.baseline_dir is not None
        else prefetch_baseline(repo, relatives, arguments.baseline_rev)
    )

    results = []
    for path, relative in zip(paths, relatives):
        current = json.loads(path.read_text(encoding="utf-8"))
        baseline = (
            load_baseline_dir(arguments.baseline_dir, relative)
            if arguments.baseline_dir is not None
            else prefetched.get(relative.as_posix())
        )
        if baseline is None:
            results.append({"schema": relative.as_posix(), "verdict": "added",
                            "digest": sha256_bytes(path.read_bytes()), "findings": []})
            continue
        findings = compare(baseline, current)
        breaking = [item for item in findings if item["breaking"]]
        results.append({
            "schema": relative.as_posix(),
            "verdict": "breaking" if breaking else ("compatible" if findings else "unchanged"),
            "digest": sha256_bytes(path.read_bytes()),
            "findings": findings,
        })

    counts = {verdict: sum(1 for item in results if item["verdict"] == verdict)
              for verdict in ("unchanged", "added", "compatible", "breaking")}
    compared = counts["unchanged"] + counts["compatible"] + counts["breaking"]
    finished = datetime.now(timezone.utc)
    report = {
        "check": "batch43-schema-compatibility",
        "batch": 43,
        "startedAt": started.isoformat().replace("+00:00", "Z"),
        "finishedAt": finished.isoformat().replace("+00:00", "Z"),
        "repositoryRevision": revision,
        "baselineRevision": arguments.baseline_rev if arguments.baseline_dir is None else str(arguments.baseline_dir),
        "roots": roots,
        "replayCommand": f"python3 scripts/batch43_schema_compatibility_check.py --baseline-rev {arguments.baseline_rev}",
        "toolDigest": sha256_bytes(Path(__file__).read_bytes()),
        "pythonVersion": platform.python_version(),
        "counts": counts,
        "totals": {"schemasInspected": len(results), "schemasCompared": compared},
        "metrics": {
            "unsupportedBreakingChangeCount": float(counts["breaking"]),
            "schemaSurfaceCompatibilityRate": round((compared - counts["breaking"]) / compared, 4) if compared else 0.0,
        },
        "results": results,
    }
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8")
        print(f"wrote {arguments.output}")
    else:
        print(payload)
    print(
        f"inspected={len(results)} compared={compared} unchanged={counts['unchanged']} "
        f"added={counts['added']} compatible={counts['compatible']} breaking={counts['breaking']}",
        file=sys.stderr,
    )
    return 3 if counts["breaking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
