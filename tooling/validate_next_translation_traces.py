"""Verify that production Next.js traces carry repository translation assets."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST_DIR = ROOT / "apps" / "web-console" / ".next"
EVIDENCE_REF_PATTERN = re.compile(r"^certification/[a-z0-9][a-z0-9._/-]{1,260}\.json$")
ROUTE_HANDLER_NAMES = frozenset({"route.js", "route.jsx", "route.ts", "route.tsx"})


def required_assets(root: Path) -> set[Path]:
    inventory = json.loads((root / "routes" / "inventory.json").read_text())
    routes = inventory.get("routes") if isinstance(inventory, dict) else None
    if not isinstance(routes, list) or len(routes) != 72:
        raise ValueError("TRANSLATION_ROUTE_CONTRACT_COUNT_MISMATCH")
    required = {
        root / "pom.xml",
        root / "routes" / "inventory.json",
    }
    for route in routes:
        if not isinstance(route, dict):
            raise TypeError("TRANSLATION_ROUTE_ENTRY_INVALID")
        key = route.get("route_key")
        if not isinstance(key, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9-]{2,120}", key
        ):
            raise ValueError("TRANSLATION_ROUTE_KEY_INVALID")
        required.add(root / "routes" / key / "route.json")
        if route.get("repository_execution_status") == "PASSED":
            reference = route.get("repository_evidence_ref")
            if (
                not isinstance(reference, str)
                or not EVIDENCE_REF_PATTERN.fullmatch(reference)
                or ".." in reference
                or "\\" in reference
                or PurePosixPath(reference).as_posix() != reference
            ):
                raise ValueError("TRANSLATION_ROUTE_EVIDENCE_REF_INVALID")
            required.add(root.joinpath("routes", key, *PurePosixPath(reference).parts))
    unsafe = sorted(
        str(path) for path in required if not path.is_file() or path.is_symlink()
    )
    if unsafe:
        raise ValueError(
            "TRANSLATION_TRACE_ASSET_MISSING_OR_UNSAFE:" + ",".join(unsafe)
        )
    return {path.resolve(strict=True) for path in required}


def expected_trace_paths(root: Path) -> set[PurePosixPath]:
    api_root = root / "apps" / "web-console" / "app" / "api"
    source_scopes = {
        "capabilities/translation": api_root / "capabilities" / "translation",
        "translation": api_root / "translation",
    }
    expected: set[PurePosixPath] = set()
    for scope_name, scope in source_scopes.items():
        if scope.is_symlink() or not scope.is_dir():
            raise ValueError(f"TRANSLATION_ROUTE_SOURCE_SCOPE_UNSAFE:{scope_name}")
        handlers = sorted(
            path
            for path in scope.rglob("*")
            if path.name in ROUTE_HANDLER_NAMES
            and (path.is_file() or path.is_symlink())
        )
        if not handlers:
            raise ValueError(f"TRANSLATION_ROUTE_HANDLER_SET_EMPTY:{scope_name}")
        for handler in handlers:
            if handler.is_symlink() or not handler.is_file():
                raise ValueError(f"TRANSLATION_ROUTE_HANDLER_UNSAFE:{handler}")
            relative_parent = handler.relative_to(api_root).parent
            trace_path = PurePosixPath(
                "server", "app", "api", *relative_parent.parts, "route.js.nft.json"
            )
            if trace_path in expected:
                raise ValueError(
                    f"TRANSLATION_ROUTE_HANDLER_DUPLICATE:{relative_parent.as_posix()}"
                )
            expected.add(trace_path)
    return expected


def trace_files(root: Path, dist_dir: Path) -> list[Path]:
    server = dist_dir / "server" / "app" / "api"
    trace_scopes = (
        server / "capabilities" / "translation",
        server / "translation",
    )
    actual_files = sorted(
        path
        for scope in trace_scopes
        if scope.is_dir()
        for path in scope.rglob("route.js.nft.json")
        if path.is_file() or path.is_symlink()
    )
    actual_paths = {
        PurePosixPath(path.relative_to(dist_dir).as_posix()) for path in actual_files
    }
    expected_paths = expected_trace_paths(root)
    missing = sorted(path.as_posix() for path in expected_paths - actual_paths)
    extra = sorted(path.as_posix() for path in actual_paths - expected_paths)
    if missing or extra:
        raise ValueError(
            f"TRANSLATION_SERVER_TRACE_SET_MISMATCH:missing={missing}:extra={extra}"
        )
    if any(path.is_symlink() or not path.is_file() for path in actual_files):
        raise ValueError("TRANSLATION_SERVER_TRACE_UNSAFE")
    return actual_files


def resolved_trace_assets(trace: Path) -> set[Path]:
    raw = json.loads(trace.read_text(encoding="utf-8"))
    files = raw.get("files") if isinstance(raw, dict) else None
    if not isinstance(files, list) or not files:
        raise ValueError(f"NEXT_TRACE_FILES_INVALID:{trace}")
    resolved: set[Path] = set()
    for value in files:
        if not isinstance(value, str) or not value:
            raise ValueError(f"NEXT_TRACE_PATH_INVALID:{trace}")
        pure = PurePosixPath(value)
        if pure.is_absolute():
            raise ValueError(f"NEXT_TRACE_PATH_ABSOLUTE:{trace}:{value}")
        resolved.add(trace.parent.joinpath(*pure.parts).resolve())
    return resolved


def validate(root: Path = ROOT, dist_dir: Path = DEFAULT_DIST_DIR) -> dict[str, object]:
    root = root.resolve(strict=True)
    dist_dir = dist_dir.resolve(strict=True)
    expected = required_assets(root)
    traces = trace_files(root, dist_dir)
    for trace in traces:
        missing = sorted(str(path) for path in expected - resolved_trace_assets(trace))
        if missing:
            relative = trace.relative_to(dist_dir).as_posix()
            raise ValueError(
                f"TRANSLATION_TRACE_ASSETS_MISSING:{relative}:" + ",".join(missing)
            )
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.next-translation-trace-validation",
        "status": "PASSED",
        "trace_count": len(traces),
        "required_asset_count": len(expected),
        "runtime_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = validate(args.root, args.dist_dir)
    except (
        OSError,
        TypeError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"Next translation trace validation BLOCKED: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
