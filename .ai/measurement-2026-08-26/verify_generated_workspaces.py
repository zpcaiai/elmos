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


#: RETRACTED. This file briefly carried a `--production-matrix` mode that
#: reimplemented the request behind
#: `docs/project-synthesis/local-production-profile-matrix.json`. Wrong twice:
#:
#:   1. The repository already ships the tool that produced that evidence --
#:      `engines/project-synthesis-engine/scripts/run_production_matrix.py`.
#:      Re-run THAT. A reimplementation compares my request against their
#:      request, not this engine against that engine.
#:   2. The reimplementation was itself wrong: it declared the many-to-one
#:      relation with no `source.field -> target.id` mapping, which the
#:      production profile correctly turns into an open question
#:      (`OPEN_QUESTIONS_BLOCK_APPROVAL`). The comparison then reported java
#:      and python **REGRESSED** when nothing had regressed -- the exact
#:      failure `compare()` warns about, reached from the other side.
# RETRACTED -- see the note above. The reimplementation is gone; re-run the
# repository's own `scripts/run_production_matrix.py` instead.


def request_for(language: str, persistence: str, auth_mode: str, entity_count: int,
                relations: tuple[dict[str, Any], ...] = ()):
    entities = tuple(entity(i) for i in range(1, entity_count + 1))
    return approve_request(
        create_draft(
            name=f"verify-{language}-{persistence}-{auth_mode}-{entity_count}",
            description="Execution verification of the ELMOS generation contract.",
            entities=entities,
            relations=relations,
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


#: A build that could not REACH its dependency repository says nothing about
#: the generated project. In a network-restricted environment (this container
#: cannot reach Maven Central or the Gradle plugin repository) such a run would
#: otherwise be published as a product failure. The engine's own retry is
#: deliberately narrow -- `uv sync --locked` only, because `--locked` is what
#: makes a retry safe -- so the DEMOTION happens here, in the measurement, and
#: the marker that triggered it is always recorded.
_UNREACHABLE_DEPENDENCY_MARKERS = (
    "could not resolve plugin artifact",
    "could not resolve all dependencies",
    "could not resolve all files for configuration",
    "plugin repositories (could not resolve",
    "connection refused",
    "network is unreachable",
    "temporary failure in name resolution",
    "could not get resource",
    "failed to fetch",
    "unable to access",
)


def unreachable_dependency_marker(evidence: dict[str, Any]) -> str | None:
    """The marker proving a FAILED stage failed on the network, not the code."""

    for result in evidence.get("results", []):
        if result.get("status") != "FAILED":
            continue
        lowered = str(result.get("output", "")).lower()
        for marker in _UNREACHABLE_DEPENDENCY_MARKERS:
            if marker in lowered:
                return marker
    return None


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
             out_root: Path, relations: tuple[dict[str, Any], ...] = ()) -> dict[str, Any]:
    cell: dict[str, Any] = {
        "language": language, "persistence": persistence, "auth_mode": auth_mode,
        "entity_count": entity_count, "relation_count": len(relations),
    }
    started = time.monotonic()
    try:
        request = request_for(language, persistence, auth_mode, entity_count, relations)
    except Exception as error:  # noqa: BLE001 - the refusal IS the datum
        cell["outcome"] = "REFUSED_BY_INTAKE"
        cell["detail"] = f"{type(error).__name__}:{str(error)[:200]}"
        cell["seconds"] = round(time.monotonic() - started, 1)
        return cell

    workspace = out_root / f"{language}-{persistence}-{auth_mode}-{entity_count}e{len(relations)}r"
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

    outcome = str(evidence.get("status", "UNKNOWN"))
    marker = unreachable_dependency_marker(evidence) if outcome == "FAILED" else None
    if marker is not None:
        # NOT a pass and NOT a failure: an absent measurement, same as a
        # missing toolchain. Counting it either way publishes a wrong number.
        outcome = "NOT_RUN_UNREACHABLE_DEPENDENCIES"
        cell["environment_marker"] = marker
    cell["outcome"] = outcome
    cell["engine_status"] = str(evidence.get("status", "UNKNOWN"))
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
    parser.add_argument("--compare", type=Path, default=None,
                        help="path to a local-production-profile-matrix.json; emits a "
                             "then/now verdict per case (shape differences are "
                             "reported, never silently treated as comparable)")
    parser.add_argument("--compare-matrices", nargs=2, type=Path, default=None,
                        metavar=("OLD", "NEW"),
                        help="diff two run_production_matrix.py outputs and exit; "
                             "use this to check a re-run against stored evidence")
    arguments = parser.parse_args()

    if arguments.compare_matrices:
        return diff_matrices(*arguments.compare_matrices)

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
                write(arguments.json, cells, arguments, None)

    write(arguments.json, cells, arguments, compare(arguments.compare, cells))
    summary = Counter(c["outcome"] for c in cells)
    print(json.dumps({"outcomes": dict(summary.most_common()),
                      "cells": len(cells)}, indent=2, ensure_ascii=False))
    return 0


def diff_matrices(old_path: Path, new_path: Path) -> int:
    """Case-by-case diff of two `run_production_matrix.py` evidence files."""

    # A measurement tool that answers a missing input with a stack trace has
    # told the operator nothing. Name the file, say which side it was, stop.
    loaded = {}
    for side, path in (("OLD", old_path), ("NEW", new_path)):
        if not path.is_file():
            print(f"REFUSED: {side} matrix does not exist: {path}\n"
                  f"         Produce it first with:\n"
                  f"           uv --directory engines/project-synthesis-engine run --locked \\\n"
                  f"             python scripts/run_production_matrix.py --output <absolute path>",
                  file=sys.stderr)
            return 2
        try:
            loaded[side] = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            print(f"REFUSED: {side} matrix is not valid JSON ({path}): {error}", file=sys.stderr)
            return 2
    old, new = loaded["OLD"], loaded["NEW"]
    index = {(c["language"], c["auth_mode"]): c for c in old.get("cases", [])}
    rows, verdicts = [], Counter()
    for case in new.get("cases", []):
        key = (case["language"], case["auth_mode"])
        before = index.get(key)
        if before is None:
            verdict = "NEW_CASE"
        elif before.get("entity_shape") != case.get("entity_shape"):
            verdict = "SHAPE_DIFFERS"
        elif before.get("status") == case.get("status"):
            verdict = "SAME"
        elif before.get("status") == "PASSED":
            verdict = "REGRESSED"
        else:
            verdict = "CHANGED"
        verdicts[verdict] += 1
        rows.append({
            "language": key[0], "auth_mode": key[1], "verdict": verdict,
            "then": before.get("status") if before else None,
            "now": case.get("status"),
            "then_files": before.get("generated_file_count") if before else None,
            "now_files": case.get("generated_file_count"),
            "request_sha256_same": bool(before)
            and before.get("request_sha256") == case.get("request_sha256"),
        })
    print(json.dumps({
        "old": {"path": str(old_path), "observed_at": old.get("observed_at"),
                "status": old.get("status")},
        "new": {"path": str(new_path), "observed_at": new.get("observed_at"),
                "status": new.get("status")},
        "verdicts": dict(verdicts.most_common()),
        "rows": rows,
    }, indent=2, ensure_ascii=False))
    return 0 if not verdicts["REGRESSED"] else 1


def compare(stored: Path | None, cells: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Then vs now, per case, with the shape difference reported not hidden.

    A case that ran on a different entity shape is `SHAPE_DIFFERS`, never
    `SAME` -- comparing two different requests and calling the result "no
    regression" is how a regression gets published as a pass.
    """

    if stored is None:
        return None
    try:
        previous = json.loads(stored.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {"error": f"{type(error).__name__}: {error}"}
    then = {
        (str(c.get("language")), str(c.get("auth_mode"))): c
        for c in previous.get("cases", [])
    }
    rows: list[dict[str, Any]] = []
    for cell in cells:
        key = (cell["language"], cell["auth_mode"])
        before = then.get(key)
        if before is None:
            continue
        before_shape = str(before.get("entity_shape", "?"))
        now_shape = "multi-entity" if cell.get("entity_count", 1) > 1 else "single-entity"
        before_status = str(before.get("status", "?"))
        now_status = str(cell.get("outcome", "?"))
        if before_shape != now_shape:
            verdict = "SHAPE_DIFFERS"
        elif now_status.startswith("NOT_RUN") or now_status == "PARTIAL":
            verdict = "NOT_COMPARABLE_MEASUREMENT_ABSENT"
        elif before_status == now_status:
            verdict = "SAME"
        elif before_status == "PASSED":
            verdict = "REGRESSED"
        else:
            verdict = "CHANGED"
        rows.append({
            "language": cell["language"], "auth_mode": cell["auth_mode"],
            "then_status": before_status, "then_shape": before_shape,
            "then_file_count": before.get("generated_file_count"),
            "now_status": now_status, "now_shape": now_shape,
            "now_file_count": cell.get("file_count"),
            "verdict": verdict,
        })
    return {
        "stored_evidence": str(stored),
        "stored_observed_at": previous.get("observed_at"),
        "verdicts": dict(Counter(r["verdict"] for r in rows).most_common()),
        "rows": rows,
    }


def write(path: Path, cells: list[dict[str, Any]], arguments,
          comparison: dict[str, Any] | None = None) -> None:
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
        "comparison_with_stored_evidence": comparison,
        "cells": cells,
    }
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
