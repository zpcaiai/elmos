"""Command line for the java->python route.

Every command reports one of a small set of outcomes and sets the exit code
accordingly.  ``REFUSED`` is a first-class outcome, not an error to be worked
around: a route that declines to translate what it does not understand is
behaving correctly, and the number of refusals is a coverage measurement rather
than a failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import uir
from .diff.harness import DifferentialHarness, default_arg_vectors
from .emit.python import EmitError, PythonEmitter
from .frontend.java import ParseError, UnsupportedConstruct, parse_java_file

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_REFUSED = 3


def _parse(path: Path):
    return parse_java_file(path)


def cmd_parse(args: argparse.Namespace) -> int:
    try:
        module = _parse(Path(args.source))
    except (UnsupportedConstruct, ParseError) as exc:
        print(json.dumps({"outcome": "REFUSED", "reason": str(exc)}, indent=2))
        return EXIT_REFUSED
    unknowns = uir.unknown_types(module)
    print(
        json.dumps(
            {
                "outcome": "OK",
                "uir_version": module.uir_version,
                "digest": uir.digest(module),
                "types": [t.name for t in module.types],
                "methods": sum(len(t.methods) for t in module.types),
                "unknown_types": len(unknowns),
                "unknown_reasons": sorted({u.reason for u in unknowns}),
            },
            indent=2,
        )
    )
    return EXIT_OK


def cmd_emit(args: argparse.Namespace) -> int:
    try:
        module = _parse(Path(args.source))
        emitter = PythonEmitter(module)
        code = emitter.emit()
    except (UnsupportedConstruct, ParseError, EmitError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    if args.out:
        out = Path(args.out)
        out.write_text(code, encoding="utf-8")
        if args.source_map:
            Path(args.source_map).write_text(
                json.dumps(
                    [e.__dict__ for e in emitter.source_map_entries()], indent=2
                ),
                encoding="utf-8",
            )
    else:
        sys.stdout.write(code)
    return EXIT_OK


def cmd_diff(args: argparse.Namespace) -> int:
    vectors = (
        [json.loads(args.args_json)]
        if args.args_json
        else default_arg_vectors(args.arity)
    )
    report = DifferentialHarness(timeout=args.timeout).run(Path(args.source), vectors)
    payload = json.loads(report.to_json())
    if not args.include_source:
        payload.pop("generated_python", None)
    if not args.include_cases:
        payload["cases"] = [c for c in payload["cases"] if c["outcome"] != "MATCH"]
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    if report.outcome == "PASS":
        return EXIT_OK
    if report.outcome == "TRANSLATION_REFUSED":
        return EXIT_REFUSED
    return EXIT_FAIL


def cmd_survey(args: argparse.Namespace) -> int:
    """Measure front-end coverage over a tree of real Java files.

    This is the honest version of "we support Java": a count of files that
    actually lower to IR, with the refusal reasons tallied so the next
    increment is chosen from data rather than from taste.
    """

    root = Path(args.root)
    files = sorted(root.rglob("*.java"))
    if args.limit:
        files = files[: args.limit]

    parsed = 0
    refused: dict[str, int] = {}
    unparsed = 0
    crashed: list[dict] = []
    emitted = 0
    emit_refused: dict[str, int] = {}
    per_file: list[dict] = []

    for path in files:
        record = {"file": str(path.relative_to(root))}
        try:
            module = _parse(path)
        except UnsupportedConstruct as exc:
            key = exc.reason.split("(")[0].strip()
            refused[key] = refused.get(key, 0) + 1
            record.update(stage="parse", outcome="REFUSED", reason=key)
            per_file.append(record)
            continue
        except ParseError:
            unparsed += 1
            record.update(stage="parse", outcome="UNPARSED")
            per_file.append(record)
            continue
        except RecursionError:
            unparsed += 1
            record.update(stage="parse", outcome="UNPARSED", reason="recursion")
            per_file.append(record)
            continue
        except Exception as exc:  # noqa: BLE001 - see below
            # An unexpected exception is a defect in the front end, not a
            # property of the file.  It is counted separately and reported
            # rather than aborting the survey, so one bad file cannot hide the
            # measurement for the other 883.
            crashed.append({"file": record["file"], "error": repr(exc)[:200]})
            record.update(stage="parse", outcome="CRASHED", reason=type(exc).__name__)
            per_file.append(record)
            continue
        parsed += 1
        try:
            PythonEmitter(module).emit()
        except EmitError as exc:
            key = exc.reason.split(";")[0].strip()
            emit_refused[key] = emit_refused.get(key, 0) + 1
            record.update(stage="emit", outcome="REFUSED", reason=key)
            per_file.append(record)
            continue
        except RecursionError:
            emit_refused["recursion"] = emit_refused.get("recursion", 0) + 1
            record.update(stage="emit", outcome="REFUSED", reason="recursion")
            per_file.append(record)
            continue
        except Exception as exc:  # noqa: BLE001 - a defect, reported not hidden
            crashed.append({"file": record["file"], "error": repr(exc)[:200]})
            record.update(stage="emit", outcome="CRASHED", reason=type(exc).__name__)
            per_file.append(record)
            continue
        emitted += 1
        record.update(stage="emit", outcome="OK", digest=uir.digest(module))
        per_file.append(record)

    summary = {
        "root": str(root),
        "files_seen": len(files),
        "parsed_to_uir": parsed,
        "unparsed": unparsed,
        "crashed": len(crashed),
        "crash_detail": crashed[:20],
        "parse_refusals": dict(sorted(refused.items(), key=lambda kv: -kv[1])),
        "emitted_python": emitted,
        "emit_refusals": dict(sorted(emit_refused.items(), key=lambda kv: -kv[1])),
        "parse_rate": round(parsed / len(files), 4) if files else 0.0,
        "emit_rate": round(emitted / len(files), 4) if files else 0.0,
    }
    if args.out:
        Path(args.out).write_text(
            json.dumps({"summary": summary, "files": per_file}, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="j2p", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("parse", help="lower Java to UIR and report the digest")
    p.add_argument("source")
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("emit", help="generate Python from Java")
    p.add_argument("source")
    p.add_argument("--out")
    p.add_argument("--source-map")
    p.set_defaults(func=cmd_emit)

    p = sub.add_parser("diff", help="run both sides and compare observable behaviour")
    p.add_argument("source")
    p.add_argument("--arity", type=int, default=2)
    p.add_argument("--args-json")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--out")
    p.add_argument("--include-source", action="store_true")
    p.add_argument("--include-cases", action="store_true")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("survey", help="measure front-end coverage over a real tree")
    p.add_argument("root")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out")
    p.set_defaults(func=cmd_survey)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
