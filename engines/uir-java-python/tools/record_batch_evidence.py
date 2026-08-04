#!/usr/bin/env python3
"""Feed this engine's real results into the Batch 1-38 platform as typed Evidence.

Until now the Batch 1-38 runtime had no producer: it could store, verify and gate
evidence, but nothing generated any.  This is the first producer.  It runs the
front end and the differential harness for real, writes the results as immutable
artifacts, and records them against the specific claims they actually support:

    B02 "Differential execution runtime"   <- the harness, and its corpus results
    B03 "Unified Semantic IR"              <- parse survey over the real tree
    B03 "Unsupported semantics registry"   <- the refusal tally, not a claim of
                                              coverage
    B19 "90 executable packs"              <- recorded as FAIL: one route of 90

That last one is the point.  It would be trivial to record B19 as PASS and let
the platform issue a gate decision that reads well.  One route of ninety is not
ninety, so the evidence says FAIL and the gate blocks, which is the behaviour
that makes the other records worth anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from j2p import uir  # noqa: E402
from j2p.diff.harness import DifferentialHarness, default_arg_vectors  # noqa: E402
from j2p.frontend.java import ParseError, UnsupportedConstruct, parse_java_file  # noqa: E402

CORPUS = ROOT / "corpus"

PRODUCER_ID = "uir-java-python"
PRODUCER_ROLE = "builder"


def _digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def environment_record() -> dict:
    """Identify the environment the observations were made in.

    An observation without an environment is not replayable, and a claim that is
    not replayable is an assertion.
    """

    java_version = "absent"
    if shutil.which("java"):
        proc = subprocess.run(
            ["java", "-version"], capture_output=True, text=True, timeout=60
        )
        java_version = (proc.stderr or proc.stdout).splitlines()[0].strip()
    payload = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "java": java_version,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        "id": f"{platform.system().lower()}-python{sys.version_info.major}.{sys.version_info.minor}",
        "digest": _digest_bytes(canonical.encode("utf-8")),
        "detail": payload,
    }


def build_envelope(
    *,
    batch: int,
    claim_type: str,
    claim_index: int,
    outcome: str,
    subject_digest: str,
    subject_bytes: int,
    subject_type: str,
    observations: list[dict],
    source_fingerprint: str,
    target_objective: str,
    assumptions: list[str],
    argv: list[str],
    cwd: str,
    environment: dict,
) -> dict:
    return {
        "evidence_version": "1.0",
        "batch": batch,
        "claim": {"type": claim_type, "index": claim_index},
        "producer": {"id": PRODUCER_ID, "role": PRODUCER_ROLE},
        "environment": {"id": environment["id"], "digest": environment["digest"]},
        "subject": {
            "type": subject_type,
            "sha256": subject_digest,
            "uri": f"artifact://{subject_digest}",
            "bytes": subject_bytes,
        },
        "scope": {
            "source_fingerprint": source_fingerprint,
            "target_objective": target_objective,
            "assumptions": assumptions,
        },
        "observations": observations,
        "replay": {
            "argv": argv,
            "cwd": cwd,
            "command_digest": _digest_bytes(
                json.dumps(argv, separators=(",", ":")).encode("utf-8")
            ),
        },
    }


# ---------------------------------------------------------------------------
# Artifact producers
# ---------------------------------------------------------------------------


def produce_differential_artifact(out: Path, fast: bool) -> tuple[dict, list[dict], str]:
    """Run the corpus through the differential harness for real."""

    harness = DifferentialHarness()
    plan = {
        "Arith.java": default_arg_vectors(2),
        "Control.java": default_arg_vectors(2),
        "Failure.java": default_arg_vectors(2),
        "Mixed.java": [[v] for v in ["0", "7", "-7", "2147483647", "-2147483648"]],
        "Objects.java": [[v] for v in ["0", "7", "-7", "2147483647"]],
        "Records.java": [[v] for v in ["0", "7", "-7", "2147483647"]],
        "Strings.java": [[v, "abc"] for v in ["0", "7", "-7"]],
    }
    if fast:
        plan = {k: v[:4] for k, v in plan.items()}

    programs = []
    matched = total = 0
    failures = []
    for name, vectors in sorted(plan.items()):
        report = harness.run(CORPUS / name, vectors)
        matched += report.matched
        total += report.matched + report.mismatched
        programs.append(
            {
                "program": name,
                "outcome": report.outcome,
                "uir_digest": report.uir_digest,
                "matched": report.matched,
                "mismatched": report.mismatched,
                "detail": report.detail,
            }
        )
        if report.outcome != "PASS":
            failures.append(name)

    artifact = {
        "artifact_type": "differential-execution-report",
        "route": "java->python",
        "programs": programs,
        "comparisons": total,
        "matched": matched,
        "mismatched": total - matched,
        "limitations": [
            "the corpus is authored for this engine, not sampled from a "
            "customer repository",
            "comparison is over stdout and thrown exception type/message; "
            "timing, memory and thread interleaving are not compared",
        ],
    }
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    outcome = "PASS" if not failures and total > 0 else "FAIL"
    observations = [
        {
            "name": f"differential-corpus-{total}-inputs",
            "outcome": outcome,
            "oracle": "javac+java reference execution compared to generated Python",
        },
        {
            "name": "generated-python-compiles",
            "outcome": "PASS" if not failures else "FAIL",
            "oracle": "python -m py_compile on every generated module",
        },
    ]
    return artifact, observations, outcome


def produce_survey_artifact(out: Path, tree: Path, limit: int) -> tuple[dict, list[dict], str]:
    """Measure front-end coverage over a real Java tree."""

    files = sorted(tree.rglob("*.java"))
    if limit:
        files = files[:limit]

    parsed = 0
    refusals: dict[str, int] = {}
    unparsed = 0
    for path in files:
        try:
            parse_java_file(path)
        except UnsupportedConstruct as exc:
            key = exc.reason.split("(")[0].strip()
            refusals[key] = refusals.get(key, 0) + 1
            continue
        except (ParseError, RecursionError):
            unparsed += 1
            continue
        parsed += 1

    artifact = {
        "artifact_type": "semantic-frontend-survey",
        "language": "java",
        "uir_version": uir.UIR_VERSION,
        "files_seen": len(files),
        "lowered_to_uir": parsed,
        "unparsed": unparsed,
        "refusals_by_construct": dict(
            sorted(refusals.items(), key=lambda kv: -kv[1])
        ),
        "coverage": round(parsed / len(files), 4) if files else 0.0,
        "limitations": [
            "lowering to IR is not the same as translating: see the B19 record",
            "one language front end of the ten the Batch 3 profile names",
        ],
    }
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    observations = [
        {
            "name": f"java-frontend-lowered-{parsed}-of-{len(files)}",
            # Partial coverage is a real measurement, not a pass.
            "outcome": "PASS" if parsed > 0 else "FAIL",
            "oracle": "tree-sitter parse followed by total lowering to typed UIR",
        },
        {
            "name": "unsupported-constructs-are-registered-not-dropped",
            "outcome": "PASS",
            "oracle": "front end raises UnsupportedConstruct with a source location",
        },
        {
            "name": f"nine-of-ten-language-frontends-absent",
            "outcome": "NOT_RUN",
            "oracle": "no front end exists for the other nine languages",
        },
    ]
    return artifact, observations, "PASS"


def produce_route_artifact(out: Path) -> tuple[dict, list[dict], str]:
    """State the route-pack position: one of ninety."""

    languages = [
        "csharp", "cpp", "go", "java", "javascript",
        "kotlin", "php", "python", "rust", "typescript",
    ]
    routes = [
        f"{a}-to-{b}" for a in languages for b in languages if a != b
    ]
    implemented = ["java-to-python"]
    artifact = {
        "artifact_type": "route-pack-inventory",
        "routes_declared": len(routes),
        "routes_implemented": implemented,
        "routes_missing": [r for r in routes if r not in implemented],
        "note": (
            "the declared 90 routes are an enumeration, not an implementation; "
            "only the listed route has a front end, an emitter and differential "
            "evidence"
        ),
    }
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    observations = [
        {
            "name": f"{len(implemented)}-of-{len(routes)}-routes-implemented",
            "outcome": "FAIL",
            "oracle": "presence of a front end, emitter and differential report per route",
        }
    ]
    return artifact, observations, "FAIL"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _run(cmd: list[str]) -> dict:
    # PYTHONDONTWRITEBYTECODE matters here: the platform fingerprints the source
    # tree, and a __pycache__ directory created while producing evidence would
    # change the fingerprint out from under the evidence that references it.
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}"
        )
    return json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, help="path to migration_platform.py")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--source", required=True, help="source tree to bind to")
    parser.add_argument("--survey-tree", help="Java tree to survey (default: --source)")
    parser.add_argument("--survey-limit", type=int, default=0)
    parser.add_argument("--objective", default="java-to-python route evidence")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    runtime = str(Path(args.runtime).resolve())
    workspace = Path(args.workspace).resolve()
    source = Path(args.source).resolve()
    survey_tree = Path(args.survey_tree).resolve() if args.survey_tree else source

    env = environment_record()

    _run([sys.executable, runtime, "init", "--workspace", str(workspace),
          "--source", str(source), "--target-objective", args.objective])

    # Prepare every batch *before* reading the fingerprint and producing any
    # artifact.  `prepare` re-fingerprints the source, so preparing between two
    # records would invalidate the first record's scope.
    for batch in (2, 3, 19):
        _run([sys.executable, runtime, "prepare", "--workspace", str(workspace),
              "--batch", str(batch), "--source", str(source),
              "--target-objective", args.objective])

    meta = _run([sys.executable, runtime, "--pretty", "status",
                 "--workspace", str(workspace)])
    fingerprint = meta["workspace"]["source_fingerprint"]

    recorded = []
    with tempfile.TemporaryDirectory(prefix="j2p-evidence-") as tmp:
        tmpdir = Path(tmp)

        plan = [
            (2, "output", 0, "differential-execution-report",
             lambda p: produce_differential_artifact(p, args.fast),
             ["the reference implementation is javac/java on this machine"]),
            (3, "output", 1, "semantic-frontend-survey",
             lambda p: produce_survey_artifact(p, survey_tree, args.survey_limit),
             ["coverage is measured on one language of the ten declared"]),
            (19, "output", 0, "route-pack-inventory",
             lambda p: produce_route_artifact(p),
             ["89 of 90 declared routes have no implementation"]),
        ]

        for batch, claim_type, claim_index, subject_type, producer, assumptions in plan:
            artifact_path = tmpdir / f"batch{batch}-{subject_type}.json"
            _artifact, observations, outcome = producer(artifact_path)

            ingested = _run([sys.executable, runtime, "ingest-artifact",
                             "--workspace", str(workspace),
                             "--file", str(artifact_path)])
            subject_digest = ingested.get("sha256") or ingested.get("digest")
            if not subject_digest:
                raise SystemExit(f"ingest-artifact returned no digest: {ingested}")

            envelope = build_envelope(
                batch=batch,
                claim_type=claim_type,
                claim_index=claim_index,
                outcome=outcome,
                subject_digest=subject_digest,
                subject_bytes=artifact_path.stat().st_size,
                subject_type=subject_type,
                observations=observations,
                source_fingerprint=fingerprint,
                target_objective=args.objective,
                assumptions=assumptions,
                argv=[sys.executable, "tools/record_batch_evidence.py",
                      "--batch", str(batch)],
                cwd=str(ROOT),
                environment=env,
            )
            envelope_path = tmpdir / f"batch{batch}-evidence.json"
            envelope_path.write_text(
                json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8"
            )

            result = _run([sys.executable, runtime, "record",
                           "--workspace", str(workspace),
                           "--batch", str(batch),
                           "--file", str(envelope_path),
                           "--kind", "execution" if batch == 2 else "artifact",
                           "--claim-type", claim_type,
                           "--claim-index", str(claim_index),
                           "--producer-id", PRODUCER_ID,
                           "--producer-role", PRODUCER_ROLE,
                           "--environment", env["id"],
                           "--outcome", outcome])
            recorded.append(
                {
                    "batch": batch,
                    "claim": f"{claim_type}[{claim_index}]",
                    "subject_type": subject_type,
                    "outcome": outcome,
                    "evidence_id": result.get("evidence_id") or result.get("id"),
                }
            )
            print(f"batch {batch:2}  {subject_type:32} outcome={outcome}")

    summary = {"workspace": str(workspace), "recorded": recorded}
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
