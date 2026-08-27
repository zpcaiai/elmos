#!/usr/bin/env python3
"""Validate the bounded, fail-closed Vercel Web Console source context."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE_FILES = 14_000
MAX_SOURCE_BYTES = 90 * 1024 * 1024
EXPECTED_IGNORE_PATTERNS = (
    "/*",
    "!/apps/",
    "/apps/*",
    "!/apps/web-console/",
    "!/apps/web-console/**",
    "!/contracts/",
    "/contracts/*",
    "!/contracts/pricing-catalog-schema/",
    "/contracts/pricing-catalog-schema/*",
    "!/contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json",
    "!/routes/",
    "!/routes/**",
    "!/pom.xml",
)
PRICING_CONTRACT = "contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json"
REPOSITORY_PROFILE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,120}$")
REPOSITORY_EVIDENCE_REF_PATTERN = re.compile(
    r"^certification/[a-z0-9][a-z0-9._/-]{1,260}\.json$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_REPOSITORY_EVIDENCE_BYTES = 8 * 1024 * 1024


def is_deployment_source(path: str) -> bool:
    """Return whether a tracked path belongs to the bounded deployment context."""

    return (
        path == "pom.xml"
        or path == PRICING_CONTRACT
        or path.startswith("apps/web-console/")
        or path.startswith("routes/")
    )


def semantic_ignore_patterns(path: Path) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def validate_ignore_policy(root: Path) -> None:
    root_ignore = root / ".vercelignore"
    app_ignore = root / "apps" / "web-console" / ".vercelignore"
    if not root_ignore.is_file() or root_ignore.is_symlink():
        raise ValueError("ROOT_VERCELIGNORE_MISSING_OR_UNSAFE")
    if app_ignore.exists() or app_ignore.is_symlink():
        raise ValueError("APP_VERCELIGNORE_MUST_NOT_OVERRIDE_ROOT_POLICY")
    observed = semantic_ignore_patterns(root_ignore)
    if observed != EXPECTED_IGNORE_PATTERNS:
        raise ValueError("VERCELIGNORE_POLICY_DRIFT")


def tracked_paths(root: Path) -> list[str]:
    completed = subprocess.run(
        ("git", "ls-files", "-z"),
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    raw_paths = completed.stdout.split(b"\0")
    if raw_paths and raw_paths[-1] == b"":
        raw_paths.pop()
    paths = [item.decode("utf-8", errors="strict") for item in raw_paths]
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("TRACKED_PATH_INVENTORY_INVALID")
    return paths


def validate_policy_is_tracked(paths: Iterable[str]) -> None:
    if ".vercelignore" not in set(paths):
        raise ValueError("ROOT_VERCELIGNORE_NOT_TRACKED")


def deployment_inventory(root: Path, paths: Iterable[str]) -> list[tuple[str, int]]:
    inventory: list[tuple[str, int]] = []
    for path in sorted(item for item in paths if is_deployment_source(item)):
        pure = PurePosixPath(path)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError(f"DEPLOYMENT_PATH_UNSAFE:{path}")
        candidate = root.joinpath(*pure.parts)
        details = candidate.lstat()
        if not candidate.is_file() or candidate.is_symlink():
            raise ValueError(f"DEPLOYMENT_SOURCE_NOT_REGULAR_FILE:{path}")
        inventory.append((path, details.st_size))
    return inventory


def enforce_budget(inventory: Iterable[tuple[str, int]]) -> tuple[int, int]:
    entries = list(inventory)
    file_count = len(entries)
    byte_count = sum(size for _, size in entries)
    if file_count > MAX_SOURCE_FILES:
        raise ValueError(
            f"VERCEL_SOURCE_FILE_BUDGET_EXCEEDED:{file_count}>{MAX_SOURCE_FILES}"
        )
    if byte_count > MAX_SOURCE_BYTES:
        raise ValueError(
            f"VERCEL_SOURCE_BYTE_BUDGET_EXCEEDED:{byte_count}>{MAX_SOURCE_BYTES}"
        )
    return file_count, byte_count


def _safe_repository_ref(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("PASSED_ROUTE_EVIDENCE_REF_MISSING")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"PASSED_ROUTE_EVIDENCE_REF_UNSAFE:{value}")
    return path.as_posix()


def validate_route_contracts(root: Path, deployed_paths: set[str]) -> tuple[int, int]:
    inventory_path = root / "routes" / "inventory.json"
    raw = json.loads(inventory_path.read_text(encoding="utf-8"))
    routes = raw.get("routes") if isinstance(raw, Mapping) else None
    if not isinstance(routes, list) or not routes:
        raise ValueError("ROUTE_INVENTORY_INVALID")
    if raw.get("route_count") != len(routes):
        raise ValueError("ROUTE_INVENTORY_COUNT_MISMATCH")

    keys: set[str] = set()
    passed_evidence_count = 0
    for route in routes:
        if not isinstance(route, Mapping):
            raise ValueError("ROUTE_ENTRY_INVALID")
        key = route.get("route_key")
        if (
            not isinstance(key, str)
            or not key
            or key in keys
            or "/" in key
            or "\\" in key
        ):
            raise ValueError(f"ROUTE_KEY_INVALID_OR_DUPLICATE:{key}")
        keys.add(key)
        route_contract = f"routes/{key}/route.json"
        if route_contract not in deployed_paths:
            raise ValueError(f"ROUTE_CONTRACT_NOT_DEPLOYED:{route_contract}")
        repository_status = route.get("repository_execution_status", "NOT_RUN")
        descriptor = (
            route.get("repository_profile"),
            route.get("repository_evidence_ref"),
            route.get("repository_evidence_sha256"),
            route.get("repository_evidence_bytes"),
        )
        if repository_status == "PASSED":
            profile, evidence_ref_raw, evidence_sha256, evidence_bytes = descriptor
            if not isinstance(profile, str) or not REPOSITORY_PROFILE_PATTERN.fullmatch(
                profile
            ):
                raise ValueError(f"PASSED_ROUTE_PROFILE_INVALID:{key}")
            evidence_ref = _safe_repository_ref(evidence_ref_raw)
            if not REPOSITORY_EVIDENCE_REF_PATTERN.fullmatch(evidence_ref):
                raise ValueError(f"PASSED_ROUTE_EVIDENCE_REF_INVALID:{key}")
            evidence_path = f"routes/{key}/{evidence_ref}"
            if evidence_path not in deployed_paths:
                raise ValueError(f"PASSED_ROUTE_EVIDENCE_NOT_DEPLOYED:{evidence_path}")
            if not isinstance(evidence_sha256, str) or not SHA256_PATTERN.fullmatch(
                evidence_sha256
            ):
                raise ValueError(f"PASSED_ROUTE_EVIDENCE_DIGEST_INVALID:{key}")
            if (
                not isinstance(evidence_bytes, int)
                or isinstance(evidence_bytes, bool)
                or evidence_bytes < 1
                or evidence_bytes > MAX_REPOSITORY_EVIDENCE_BYTES
            ):
                raise ValueError(f"PASSED_ROUTE_EVIDENCE_BYTES_INVALID:{key}")
            raw_evidence = root.joinpath(
                *PurePosixPath(evidence_path).parts
            ).read_bytes()
            if len(raw_evidence) != evidence_bytes:
                raise ValueError(f"PASSED_ROUTE_EVIDENCE_BYTES_MISMATCH:{key}")
            if hashlib.sha256(raw_evidence).hexdigest() != evidence_sha256:
                raise ValueError(f"PASSED_ROUTE_EVIDENCE_DIGEST_MISMATCH:{key}")
            passed_evidence_count += 1
        elif any(item is not None for item in descriptor):
            raise ValueError(f"NON_PASSED_ROUTE_EVIDENCE_DESCRIPTOR_STALE:{key}")
    return len(routes), passed_evidence_count


def validate(root: Path = ROOT) -> dict[str, object]:
    root = root.resolve(strict=True)
    validate_ignore_policy(root)
    paths = tracked_paths(root)
    validate_policy_is_tracked(paths)
    inventory = deployment_inventory(root, paths)
    file_count, byte_count = enforce_budget(inventory)
    deployed_paths = {path for path, _ in inventory}
    required = {
        "pom.xml",
        "routes/inventory.json",
        PRICING_CONTRACT,
        "apps/web-console/package.json",
        "apps/web-console/pnpm-lock.yaml",
        "apps/web-console/vercel.json",
    }
    missing = sorted(required - deployed_paths)
    if missing:
        raise ValueError("REQUIRED_DEPLOYMENT_SOURCE_MISSING:" + ",".join(missing))
    route_count, passed_evidence_count = validate_route_contracts(root, deployed_paths)
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.vercel-source-budget",
        "status": "PASSED",
        "claim_scope": "SOURCE_CONTEXT_ONLY",
        "source_file_count": file_count,
        "source_byte_count": byte_count,
        "max_source_files": MAX_SOURCE_FILES,
        "max_source_bytes": MAX_SOURCE_BYTES,
        "route_count": route_count,
        "passed_route_evidence_count": passed_evidence_count,
        "runtime_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = validate(args.root)
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"Vercel source budget BLOCKED: {error}", file=sys.stderr)
        return 1
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
