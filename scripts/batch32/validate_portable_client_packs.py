#!/usr/bin/env python3
"""Validate all client packs without fabricating host-bound native replay.

Ordinary packs run through the production client gate in read-only portable
mode so CI cannot rewrite repository evidence.  The two receipt-bound formal
packs run the repository validators with native execution disabled.  This
validates captured artifact, schema, digest, proof, and governance while keeping
live repository comparison, Node/Z3/browser/device execution, and
certification explicitly NOT_RUN.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK_ROOT = ROOT / "client-packs"
CLIENT_GATE = ROOT / "scripts/batch32/run_client_gate.py"
DEPENDENCY_VERSIONS = {
    "jsonschema": "4.25.1",
    "pyyaml": "6.0.2",
}
COMMAND_TIMEOUT_SECONDS = 360
EXPECTED_PACK_MODES = {
    "elmos-batch105-108-proof-loop-console": "ordinary",
    "elmos-web-console-account-usage": "ordinary",
    "elmos-web-console-enterprise-identity": "ordinary",
    "elmos-web-console-navigation-modernization": "ordinary",
    "frontend-72-route-equivalence-v1": "formal-v1",
    "frontend-72-route-equivalence-v2": "formal-v2",
    "frontend-to-miniapp-vue3-wechat-v1": "ordinary",
    "frt-g01-g30-platform": "ordinary",
    "web-console-next16-react19-wechat-v1": "ordinary",
}


class PortableGateError(RuntimeError):
    """A portable pack failed closed."""


@dataclass(frozen=True)
class PackOutcome:
    pack_key: str
    mode: str
    structural_status: str
    certification_decision: str
    native_receipt_replay: str


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PortableGateError(f"{path} must contain a JSON object")
    return value


def parse_last_json(stdout: str, label: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise PortableGateError(f"{label} emitted no JSON result")
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise PortableGateError(f"{label} emitted invalid JSON") from error
    if not isinstance(value, dict):
        raise PortableGateError(f"{label} result must be an object")
    return value


def run_checked(command: list[str], *, cwd: Path, label: str) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    result = parse_last_json(completed.stdout, label)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-4000:]
        raise PortableGateError(
            f"{label} failed with exit {completed.returncode}: {detail}"
        )
    return result


def formal_command(pack: Path, manifest: dict[str, Any]) -> tuple[int, list[str]]:
    replay = pack / "formal-campaign/replay"
    if manifest.get("frontend_formal_route_campaign_v2") is not None:
        schema_root = replay / "schemas/batch32"
        return 2, [
            sys.executable,
            str(
                ROOT
                / "scripts/batch32/validate_frontend_formal_route_campaign_v2.py"
            ),
            str(pack),
            "--schema",
            str(schema_root / "frontend-formal-route-campaign-v2.schema.json"),
            "--route-schema",
            str(schema_root / "frontend-formal-route-evidence-v2.schema.json"),
            "--no-replay-execute",
            "--portable-evidence-only",
            "--json",
        ]
    if manifest.get("frontend_formal_route_campaign") is not None:
        schema_root = replay / "schemas/batch32"
        return 1, [
            sys.executable,
            str(ROOT / "scripts/batch32/validate_frontend_formal_route_campaign.py"),
            str(pack),
            "--schema",
            str(schema_root / "frontend-formal-route-campaign.schema.json"),
            "--route-schema",
            str(schema_root / "frontend-formal-route-evidence.schema.json"),
            "--no-replay-execute",
            "--portable-evidence-only",
            "--json",
        ]
    raise PortableGateError(f"{pack.name} is not a declared formal client pack")


def validate_formal(pack: Path, manifest: dict[str, Any]) -> PackOutcome:
    version, command = formal_command(pack, manifest)
    missing = [item for item in command if item.startswith(str(pack)) and not Path(item).exists()]
    if missing:
        raise PortableGateError(f"{pack.name} portable replay files are missing: {missing}")
    result = run_checked(command, cwd=ROOT, label=f"{pack.name} v{version} captured gate")
    failures: list[str] = []
    if result.get("status") != "valid":
        failures.append("status is not valid")
    if result.get("structural_status") != "PASSED":
        failures.append("structural_status is not PASSED")
    if result.get("certification_ready") is not False:
        failures.append("portable evidence must not be certification-ready")
    if version == 2 and result.get("live_engine_verifier_status") != "NOT_RUN":
        failures.append("v2 live engine verifier status must remain NOT_RUN")
    if failures:
        raise PortableGateError(f"{pack.name}: {'; '.join(failures)}")
    return PackOutcome(
        pack_key=str(manifest.get("pack_key", pack.name)),
        mode=f"captured-formal-v{version}",
        structural_status="PASSED",
        certification_decision="NOT_CERTIFIED",
        native_receipt_replay="NOT_RUN",
    )


def validate_ordinary(pack: Path, manifest: dict[str, Any]) -> PackOutcome:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, str(CLIENT_GATE), str(pack), "--portable"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-4000:]
        raise PortableGateError(
            f"{pack.name} client gate failed with exit "
            f"{completed.returncode}: {detail}"
        )
    if "GATE PASS:" not in completed.stdout:
        raise PortableGateError(f"{pack.name} client gate omitted pass receipt")
    if "decision=NOT_CERTIFIED" not in completed.stdout:
        raise PortableGateError(f"{pack.name} portable gate may not grant certification")
    return PackOutcome(
        pack_key=str(manifest.get("pack_key", pack.name)),
        mode="portable-production-gate",
        structural_status="PASSED",
        certification_decision="NOT_CERTIFIED",
        native_receipt_replay="NOT_APPLICABLE",
    )


def validate_all(pack_root: Path) -> list[PackOutcome]:
    resolved_root = pack_root.resolve(strict=True)
    if not resolved_root.is_dir() or resolved_root.is_symlink():
        raise PortableGateError("client pack root must be a real directory")
    packs = sorted(path for path in resolved_root.iterdir() if path.is_dir())
    actual_names = {pack.name for pack in packs}
    expected_names = set(EXPECTED_PACK_MODES)
    if actual_names != expected_names:
        raise PortableGateError(
            "client pack inventory mismatch: "
            f"missing={sorted(expected_names - actual_names)} "
            f"unexpected={sorted(actual_names - expected_names)}"
        )
    prepared: list[tuple[Path, dict[str, Any], bool, bool]] = []
    seen_pack_keys: set[str] = set()
    for pack in packs:
        if pack.is_symlink():
            raise PortableGateError(f"client pack may not be a symlink: {pack}")
        manifest = load_object(pack / "pack.json")
        pack_key = manifest.get("pack_key")
        if not isinstance(pack_key, str) or not pack_key:
            raise PortableGateError(f"{pack.name} has no valid pack_key")
        if pack_key in seen_pack_keys:
            raise PortableGateError(f"duplicate client pack_key: {pack_key}")
        seen_pack_keys.add(pack_key)
        if pack_key != pack.name:
            raise PortableGateError(
                f"client pack path/key mismatch: {pack.name} != {pack_key}"
            )
        formal_v1 = manifest.get("frontend_formal_route_campaign") is not None
        formal_v2 = manifest.get("frontend_formal_route_campaign_v2") is not None
        if formal_v1 and formal_v2:
            raise PortableGateError(f"{pack.name} declares both formal contracts")
        declared_mode = "formal-v2" if formal_v2 else "formal-v1" if formal_v1 else "ordinary"
        expected_mode = EXPECTED_PACK_MODES[pack.name]
        if declared_mode != expected_mode:
            raise PortableGateError(
                f"{pack.name} mode mismatch: expected {expected_mode}, "
                f"found {declared_mode}"
            )
        prepared.append((pack, manifest, formal_v1, formal_v2))

    outcomes: list[PackOutcome] = []
    for pack, manifest, formal_v1, formal_v2 in prepared:
        outcomes.append(
            validate_formal(pack, manifest)
            if formal_v1 or formal_v2
            else validate_ordinary(pack, manifest)
        )
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-root", type=Path, default=DEFAULT_PACK_ROOT)
    args = parser.parse_args()
    try:
        outcomes = validate_all(args.pack_root)
    except (OSError, ValueError, PortableGateError, subprocess.TimeoutExpired) as error:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "FAILED",
                    "certification_decision": "NOT_CERTIFIED",
                    "error": str(error),
                },
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "schema_version": 1,
                "status": "PASSED",
                "pack_count": len(outcomes),
                "dependency_versions": DEPENDENCY_VERSIONS,
                "native_receipt_replay": "NOT_RUN",
                "certification_decision": "NOT_CERTIFIED",
                "packs": [outcome.__dict__ for outcome in outcomes],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
