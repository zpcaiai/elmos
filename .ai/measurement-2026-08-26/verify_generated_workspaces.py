"""Do the generated projects actually BUILD AND RUN? Nobody has ever checked.

`measure_generation_surface.py` answered "what does the generator accept" --
24 of 48 profile combinations, 8 languages, up to 20 entities. Its own evidence
file says, in the field that matters most:

    "verification_status": {"status": "NOT_RUN",
     "reason": "verification.verify_workspace needs the pinned macOS
                toolchains; build/startup/CRUD/RLS results are not produced
                by this run."}

So the accuracy/completeness question that started all of this -- how good are
the generated projects -- has an accepted-file-count answer and NO execution
answer. `pytest` passing is not that answer either: it exercises the generator,
not the artefact. This driver produces the missing half by running the engine's
own `verify_workspace` (build -> startup -> CRUD -> RLS) over every profile
combination the engine itself accepts.

Three rules it will not break:

1. **The accepted set is DERIVED, not hardcoded.** Cells come from asking
   `approve_request` and recording what it refuses. A stale hardcoded 24 would
   silently measure the wrong matrix the day the engine changes.
2. **NOT_RUN is never counted as either pass or fail.** A missing toolchain is
   an absent measurement. The headline is three numbers, never one percentage.
3. **Incremental.** Each cell's result is written before the next begins, so an
   interrupted multi-hour run keeps everything it earned; `--resume` skips what
   is already recorded.

    python verify_generated_workspaces.py --out ./ws --json evidence.json
    python verify_generated_workspaces.py --languages java,python --json e.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.verification import verify_workspace
from elmos_project_synthesis.workspace import generate_workspace

LANGUAGES = ("java", "python", "csharp", "typescript", "go", "kotlin", "php", "rust")
PERSISTENCE = ("in-memory", "postgresql")
AUTH_MODES = ("none", "jwt", "oidc")


def entity(index: int) -> dict[str, Any]:
    name = f"entity{index}"
    return {
        "singular": name,
        "plural": f"{name}s",
        "fields": [
            {"name": "label", "type": "string", "required": True},
            {"name": "amount", "type": "number", "required": True},
        ],
    }


def permissions(entities: tuple[dict[str, Any], ...]) -> tuple[dict[str, str], ...]:
    return tuple(
        {"actor": "api_user", "action": action, "resource": str(item["singular"]), "effect": "allow"}
        for item in entities
        for action in ("create", "read", "update", "delete")
    )


def request_for(language: str, persistence: str, auth_mode: str, entity_count: int):
    entities = tuple(entity(i) for i in range(1, entity_count + 1))
    return approve_request(
        create_draft(
            name=f"verify-{language}-{persistence}-{auth_mode}-{entity_count}",
            description="Execution verification of the ELMOS generation contract.",
            entities=entities,
            relations=(),
            languages=(language,),
            persistence=persistence,
            auth_mode=auth_mode,
            permissions=permissions(entities),
        ),
        actor="measurement:generated-workspace-verification",
        approved_at="2026-08-21T00:00:00+00:00",
    )


def stage_table(evidence: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Per verification stage: how many PASSED / FAILED / NOT_RUN.

    Kept as three separate counts on purpose. Collapsing NOT_RUN into either
    column is the single easiest way to publish a number that is not true.
    """

    table: dict[str, Counter[str]] = {}
    for result in evidence.get("results", []):
        kind = str(result.get("kind", "unknown"))
        table.setdefault(kind, Counter())[str(result.get("status", "unknown"))] += 1
    return {kind: dict(counts) for kind, counts in sorted(table.items())}


def failures(evidence: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for result in evidence.get("results", []):
        if result.get("status") != "FAILED":
            continue
        output = str(result.get("output", ""))
        out.append({
            "kind": result.get("kind"),
            "command": result.get("command"),
            "exit_code": result.get("exit_code"),
            "output_tail": output.strip().splitlines()[-12:],
        })
        if len(out) >= limit:
            break
    return out


def run_cell(language: str, persistence: str, auth_mode: str, entity_count: int,
             out_root: Path) -> dict[str, Any]:
    cell: dict[str, Any] = {
        "language": language, "persistence": persistence, "auth_mode": auth_mode,
        "entity_count": entity_count,
    }
    started = time.monotonic()
    try:
        request = request_for(language, persistence, auth_mode, entity_count)
    except Exception as error:  # noqa: BLE001 - the refusal IS the datum
        cell["outcome"] = "REFUSED_BY_INTAKE"
        cell["detail"] = f"{type(error).__name__}:{str(error)[:200]}"
        cell["seconds"] = round(time.monotonic() - started, 1)
        return cell

    workspace = out_root / f"{language}-{persistence}-{auth_mode}-{entity_count}"
    try:
        manifest = generate_workspace(request, workspace)
        cell["file_count"] = int(manifest["file_count"])
    except Exception as error:  # noqa: BLE001
        cell["outcome"] = "GENERATION_ERROR"
        cell["detail"] = f"{type(error).__name__}:{str(error)[:400]}"
        cell["seconds"] = round(time.monotonic() - started, 1)
        return cell

    try:
        evidence = verify_workspace(workspace)
    except Exception as error:  # noqa: BLE001
        cell["outcome"] = "VERIFICATION_ERROR"
        cell["detail"] = f"{type(error).__name__}:{str(error)[:400]}"
        cell["traceback_tail"] = traceback.format_exc().strip().splitlines()[-4:]
        cell["seconds"] = round(time.monotonic() - started, 1)
        return cell

    cell["outcome"] = str(evidence.get("status", "UNKNOWN"))
    cell["stages"] = stage_table(evidence)
    cell["exact_toolchain_match"] = evidence.get("environment", {}).get("exact_toolchain_match", {})
    cell["failures"] = failures(evidence)
    cell["seconds"] = round(time.monotonic() - started, 1)
    return cell


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("./elmos-generated-workspaces"))
    parser.add_argument("--json", type=Path, default=Path("./generated-workspace-evidence.json"))
    parser.add_argument("--entity-count", type=int, default=3)
    parser.add_argument("--languages", default="", help="comma-separated subset")
    parser.add_argument("--persistence", default="", help="comma-separated subset")
    parser.add_argument("--auth-modes", default="", help="comma-separated subset")
    parser.add_argument("--resume", action="store_true",
                        help="skip cells already present in --json")
    arguments = parser.parse_args()

    languages = tuple(x for x in arguments.languages.split(",") if x) or LANGUAGES
    persistences = tuple(x for x in arguments.persistence.split(",") if x) or PERSISTENCE
    auth_modes = tuple(x for x in arguments.auth_modes.split(",") if x) or AUTH_MODES
    arguments.out.mkdir(parents=True, exist_ok=True)

    done: dict[str, dict[str, Any]] = {}
    if arguments.resume and arguments.json.is_file():
        try:
            previous = json.loads(arguments.json.read_text(encoding="utf-8"))
            done = {c["key"]: c for c in previous.get("cells", []) if "key" in c}
            print(f"[resume] {len(done)} cells already recorded", file=sys.stderr)
        except (OSError, ValueError, KeyError):
            done = {}

    cells: list[dict[str, Any]] = []
    for persistence in persistences:
        for auth_mode in auth_modes:
            for language in languages:
                key = f"{persistence}|{auth_mode}|{language}"
                if key in done:
                    cells.append(done[key])
                    continue
                print(f"[verify] {key}", file=sys.stderr, flush=True)
                cell = run_cell(language, persistence, auth_mode,
                                arguments.entity_count, arguments.out)
                cell["key"] = key
                cells.append(cell)
                print(f"         -> {cell['outcome']}  ({cell['seconds']}s)",
                      file=sys.stderr, flush=True)
                # Written before the next cell starts: a run that dies at hour
                # three keeps everything it earned.
                write(arguments.json, cells, arguments)

    write(arguments.json, cells, arguments)
    summary = Counter(c["outcome"] for c in cells)
    print(json.dumps({"outcomes": dict(summary.most_common()),
                      "cells": len(cells)}, indent=2, ensure_ascii=False))
    return 0


def write(path: Path, cells: list[dict[str, Any]], arguments) -> None:
    stages: dict[str, Counter[str]] = {}
    for cell in cells:
        for kind, counts in (cell.get("stages") or {}).items():
            for status, count in counts.items():
                stages.setdefault(kind, Counter())[status] += count
    report = {
        "kind": "elmos.generated-workspace-execution-verification",
        "schema_version": "1.0.0",
        "instrument": "verify_generated_workspaces.py",
        "method": "generate_workspace() then the engine's own verify_workspace() "
                  "(build -> startup -> CRUD -> RLS). NOT_RUN is reported as an "
                  "absent measurement, never as a pass or a failure.",
        "entity_count": arguments.entity_count,
        "outcome_summary": dict(Counter(c["outcome"] for c in cells).most_common()),
        "stage_summary": {k: dict(v) for k, v in sorted(stages.items())},
        "cells": cells,
    }
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
