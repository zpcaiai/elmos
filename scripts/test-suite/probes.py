#!/usr/bin/env python3
"""Executable probes for the Batch 1-37 strict suite's own governance controls.

Each subcommand exercises one control of the strict suite (input rejection,
path containment, coverage completeness, evidence integrity, identity
separation, not-run semantics) and exits 0 only when every expected rejection
actually happened. These are real assertions against the shipped validators,
not simulations.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    ValidationError,
    load_json,
    resolve_beneath,
    sha256_file,
    sha256_json,
    validate_evidence_manifest_shape,
    validate_result_shape,
)

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "test-suites/batch1-37-strict"
CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' :: ' + detail) if detail else ''}")


def finish() -> int:
    failed = [name for name, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} controls held")
    if failed:
        print("failed controls: " + ", ".join(failed))
        return 1
    return 0


def run_validator(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts/test-suite" / script), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )


def temp_suite(tmp: Path) -> Path:
    target = tmp / "batch1-37-strict"
    shutil.copytree(SUITE, target, ignore=shutil.ignore_patterns("evidence", "results"))
    (target / "results").mkdir(exist_ok=True)
    return target


# --------------------------------------------------------------------------- #
# TS-GOV-01-003  malformed / missing / conflicting / unknown inputs
# --------------------------------------------------------------------------- #
def probe_negative_inputs() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        catalog = load_json(SUITE / "cases/catalog.json")

        broken = tmp / "malformed.json"
        broken.write_text('{"catalog_id": "batch1-37-strict", "cases": [', encoding="utf-8")
        check(
            "malformed-json-rejected",
            run_validator("validate_test_catalog.py", str(broken)).returncode != 0,
        )

        check(
            "missing-file-rejected",
            run_validator("validate_test_catalog.py", str(tmp / "absent.json")).returncode != 0,
        )

        stripped = copy.deepcopy(catalog)
        stripped["cases"][0].pop("assertions", None)
        path = tmp / "missing-field.json"
        path.write_text(json.dumps(stripped, ensure_ascii=False), encoding="utf-8")
        check(
            "missing-required-field-rejected",
            run_validator("validate_test_catalog.py", str(path)).returncode != 0,
        )

        duped = copy.deepcopy(catalog)
        duped["cases"][1]["id"] = duped["cases"][0]["id"]
        path = tmp / "conflicting-ids.json"
        path.write_text(json.dumps(duped, ensure_ascii=False), encoding="utf-8")
        check(
            "conflicting-case-ids-rejected",
            run_validator("validate_test_catalog.py", str(path)).returncode != 0,
        )

        unknown = copy.deepcopy(catalog)
        unknown["cases"][0]["severity"] = "P9"
        unknown["cases"][0]["test_type"] = "vibes"
        path = tmp / "unknown-enum.json"
        path.write_text(json.dumps(unknown, ensure_ascii=False), encoding="utf-8")
        check(
            "unknown-enum-values-rejected",
            run_validator("validate_test_catalog.py", str(path)).returncode != 0,
        )

        shrunk = copy.deepcopy(catalog)
        shrunk["cases"] = shrunk["cases"][:10]
        path = tmp / "count-mismatch.json"
        path.write_text(json.dumps(shrunk, ensure_ascii=False), encoding="utf-8")
        check(
            "declared-count-mismatch-rejected",
            run_validator("validate_test_catalog.py", str(path)).returncode != 0,
        )

        check(
            "pristine-catalog-accepted",
            run_validator("validate_test_catalog.py", str(SUITE / "cases/catalog.json")).returncode == 0,
        )
    return finish()


# --------------------------------------------------------------------------- #
# TS-GOV-01-005  path containment / unauthorized reference
# --------------------------------------------------------------------------- #
def probe_path_escape() -> int:
    base = SUITE
    for label, reference in (
        ("parent-traversal", "../../etc/passwd"),
        ("nested-traversal", "results/../../../../etc/passwd"),
        ("absolute-path", "/etc/passwd"),
        ("null-byte", "results/a\x00b.json"),
        ("empty-reference", ""),
    ):
        try:
            resolve_beneath(base, reference)
            check(f"escape-{label}-rejected", False, "resolve_beneath accepted it")
        except ValidationError:
            check(f"escape-{label}-rejected", True)
        except Exception as exc:  # noqa: BLE001
            check(f"escape-{label}-rejected", False, f"unexpected {type(exc).__name__}: {exc}")

    try:
        resolved = resolve_beneath(base, "cases/catalog.json")
        check("legitimate-reference-accepted", resolved.is_file())
    except Exception as exc:  # noqa: BLE001
        check("legitimate-reference-accepted", False, str(exc))

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        suite = temp_suite(tmp)
        outside = tmp / "outside-evidence.json"
        outside.write_text("{}", encoding="utf-8")
        catalog = load_json(suite / "cases/catalog.json")
        case = catalog["cases"][0]
        (suite / "results" / f"{case['id']}.json").write_text(
            json.dumps(
                {
                    "case_id": case["id"],
                    "status": "passed",
                    "artifact_digest": "sha256:" + "1" * 64,
                    "environment_digest": "sha256:" + "2" * 64,
                    "started_at": "2026-08-01T00:00:00Z",
                    "finished_at": "2026-08-01T00:01:00Z",
                    "execution_kind": "real",
                    "replay_command": "true",
                    "evidence": ["../outside-evidence.json"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        gate = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts/test-suite/run_strict_test_gate.py"),
                str(suite),
                "--output",
                str(tmp / "gate.json"),
            ],
            capture_output=True,
            text=True,
            cwd=REPO,
            check=False,
        )
        decision = json.loads((tmp / "gate.json").read_text(encoding="utf-8"))
        escaped = [b for b in decision["blockers"] if "outside-evidence" in b or "escapes" in b]
        check("gate-rejects-evidence-outside-suite", bool(escaped) and gate.returncode != 0, str(escaped[:1]))
    return finish()


# --------------------------------------------------------------------------- #
# TS-GOV-02-003  coverage completeness
# --------------------------------------------------------------------------- #
def probe_coverage_gap() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        matrix = load_json(SUITE / "coverage-matrix.json")
        catalog_path = SUITE / "cases/catalog.json"

        check(
            "pristine-coverage-accepted",
            run_validator("validate_coverage_matrix.py", str(SUITE / "coverage-matrix.json")).returncode == 0,
        )

        key = "batches" if "batches" in matrix else next(iter(matrix))
        gapped = copy.deepcopy(matrix)
        entries = gapped[key]
        if isinstance(entries, list) and entries:
            entries.pop()
        elif isinstance(entries, dict) and entries:
            entries.pop(next(iter(entries)))
        path = tmp / "gapped.json"
        path.write_text(json.dumps(gapped, ensure_ascii=False), encoding="utf-8")
        check(
            "dropped-coverage-entry-rejected",
            run_validator("validate_coverage_matrix.py", str(path)).returncode != 0,
        )

        ghost = copy.deepcopy(matrix)
        blob = json.dumps(ghost, ensure_ascii=False).replace("TS-GOV-01-001", "TS-GHOST-99-999", 1)
        path = tmp / "ghost-case.json"
        path.write_text(blob, encoding="utf-8")
        check(
            "unknown-case-reference-rejected",
            run_validator("validate_coverage_matrix.py", str(path)).returncode != 0,
        )
        check("catalog-still-authoritative", catalog_path.is_file())
    return finish()


# --------------------------------------------------------------------------- #
# TS-GOV-02-005  catalog -> skill binding
# --------------------------------------------------------------------------- #
def probe_skill_binding() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        catalog = load_json(SUITE / "cases/catalog.json")

        forged = copy.deepcopy(catalog)
        forged["cases"][0]["skill"] = "tst-skill-that-does-not-exist"
        path = tmp / "unknown-skill.json"
        path.write_text(json.dumps(forged, ensure_ascii=False), encoding="utf-8")
        check(
            "unknown-skill-reference-rejected",
            run_validator("validate_test_catalog.py", str(path)).returncode != 0,
        )

        traversal = copy.deepcopy(catalog)
        traversal["cases"][0]["skill"] = "../../../etc"
        path = tmp / "traversal-skill.json"
        path.write_text(json.dumps(traversal, ensure_ascii=False), encoding="utf-8")
        check(
            "skill-name-traversal-rejected",
            run_validator("validate_test_catalog.py", str(path)).returncode != 0,
        )

        skills = {case["skill"] for case in catalog["cases"]}
        missing = sorted(s for s in skills if not (REPO / ".agents/skills" / s / "SKILL.md").is_file())
        check("every-catalog-skill-exists-on-disk", not missing, f"missing={missing[:3]}")
    return finish()


# --------------------------------------------------------------------------- #
# TS-GOV-03-003  environment / result shape rejection
# --------------------------------------------------------------------------- #
def probe_environment_invalid() -> int:
    good = {
        "case_id": "TS-GOV-03-003",
        "status": "passed",
        "artifact_digest": "sha256:" + "a" * 64,
        "environment_digest": "sha256:" + "b" * 64,
        "started_at": "2026-08-01T00:00:00Z",
        "finished_at": "2026-08-01T00:01:00Z",
        "execution_kind": "real",
        "replay_command": "make qualify",
        "evidence": ["evidence/x/manifest.json"],
    }
    check("well-formed-result-accepted", not validate_result_shape(good))

    for label, mutate in (
        ("placeholder-artifact-digest", lambda r: r.update(artifact_digest="sha256:" + "0" * 64)),
        ("placeholder-environment-digest", lambda r: r.update(environment_digest="sha256:" + "0" * 64)),
        ("naive-timestamp", lambda r: r.update(started_at="2026-08-01T00:00:00")),
        ("reversed-interval", lambda r: r.update(finished_at="2025-01-01T00:00:00Z")),
        ("simulated-execution-kind", lambda r: r.update(execution_kind="simulated")),
        ("passed-without-evidence", lambda r: r.update(evidence=[])),
        ("passed-without-replay", lambda r: r.pop("replay_command")),
        ("not-run-carrying-evidence", lambda r: r.update(status="not-run")),
    ):
        candidate = copy.deepcopy(good)
        mutate(candidate)
        check(f"reject-{label}", bool(validate_result_shape(candidate)))
    return finish()


# --------------------------------------------------------------------------- #
# TS-GOV-04-001 / 04-003  evidence integrity
# --------------------------------------------------------------------------- #
def _sample_manifest(tmp: Path) -> dict:
    raw_log = tmp / "raw-log.txt"
    raw_log.write_text("probe evidence sample\n", encoding="utf-8")
    return {
        "manifest_version": 2,
        "manifest_id": "probe-0001",
        "case_id": "TS-GOV-04-001",
        "case_digest": "sha256:" + "c" * 64,
        "catalog_digest": "sha256:" + "d" * 64,
        "artifact_digest": "sha256:" + "e" * 64,
        "environment_digest": "sha256:" + "f" * 64,
        "execution_kind": "real",
        "started_at": "2026-08-01T00:00:00Z",
        "finished_at": "2026-08-01T00:01:00Z",
        "executor": {"id": "runner-a", "role": "executor"},
        "verifier": {"id": "reviewer-b", "role": "independent-verifier", "independent": True},
        "authorization_refs": ["CHG-0001"],
        "files": [
            {
                "role": "raw-log",
                "path": "raw-log.txt",
                "sha256": sha256_file(raw_log),
                "bytes": raw_log.stat().st_size,
                "immutable": True,
            }
        ],
        "corpora": [
            {"kind": "development", "digest": "sha256:" + "1" * 64},
            {"kind": "negative", "digest": "sha256:" + "2" * 64},
        ],
    }


def probe_evidence_valid() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        manifest = _sample_manifest(tmp)
        errors = validate_evidence_manifest_shape(manifest)
        check("reference-evidence-manifest-accepted", not errors, str(errors[:2]))
        check("case-digest-is-deterministic", sha256_json({"a": 1}) == sha256_json({"a": 1}))
        check("case-digest-is-order-independent", sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1}))
        check("case-digest-changes-on-mutation", sha256_json({"a": 1}) != sha256_json({"a": 2}))
    return finish()


def probe_evidence_tamper() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        for label, mutate in (
            ("wrong-manifest-version", lambda m: m.update(manifest_version=1)),
            ("placeholder-case-digest", lambda m: m.update(case_digest="sha256:" + "0" * 64)),
            ("truncated-digest", lambda m: m.update(catalog_digest="sha256:dead")),
            ("simulated-execution", lambda m: m.update(execution_kind="simulated")),
            ("no-authorization", lambda m: m.update(authorization_refs=[])),
            ("mutable-evidence-file", lambda m: m["files"][0].update(immutable=False)),
            ("zero-byte-evidence", lambda m: m["files"][0].update(bytes=0)),
            ("bad-file-digest", lambda m: m["files"][0].update(sha256="not-a-digest")),
            ("duplicate-corpus-digest", lambda m: m["corpora"][1].update(digest=m["corpora"][0]["digest"])),
            ("duplicate-corpus-kind", lambda m: m["corpora"][1].update(kind="development")),
            ("holdout-not-independent", lambda m: m["corpora"].append(
                {"kind": "holdout", "digest": "sha256:" + "3" * 64, "independent": False, "authoring_access": False})),
            ("holdout-authored-by-executor", lambda m: m["corpora"].append(
                {"kind": "holdout", "digest": "sha256:" + "4" * 64, "independent": True, "authoring_access": True})),
        ):
            manifest = _sample_manifest(tmp)
            mutate(manifest)
            check(f"detect-{label}", bool(validate_evidence_manifest_shape(manifest)))

        # Raw-file tampering must be caught by digest re-computation, not by shape alone.
        manifest = _sample_manifest(tmp)
        (tmp / "raw-log.txt").write_text("tampered\n", encoding="utf-8")
        recomputed = sha256_file(tmp / "raw-log.txt")
        check("detect-raw-log-byte-tamper", recomputed != manifest["files"][0]["sha256"])

        suite = temp_suite(tmp / "gatecheck")
        catalog = load_json(suite / "cases/catalog.json")
        case = catalog["cases"][0]
        evidence_dir = suite / "evidence" / case["id"]
        evidence_dir.mkdir(parents=True, exist_ok=True)
        log = evidence_dir / "raw-log.txt"
        log.write_text("original evidence body\n", encoding="utf-8")
        declared = sha256_file(log)
        declared_bytes = log.stat().st_size
        em = _sample_manifest(tmp)
        em["case_id"] = case["id"]
        em["case_digest"] = sha256_json(case)
        em["catalog_digest"] = "sha256:" + sha256_file(suite / "cases/catalog.json")
        em["artifact_digest"] = "sha256:" + "7" * 64
        em["environment_digest"] = "sha256:" + "8" * 64
        em["files"] = [{"role": "raw-log", "path": "raw-log.txt", "sha256": declared, "bytes": declared_bytes, "immutable": True}]
        (evidence_dir / "manifest.json").write_text(json.dumps(em, ensure_ascii=False), encoding="utf-8")
        (suite / "results" / f"{case['id']}.json").write_text(json.dumps({
            "case_id": case["id"], "status": "passed",
            "artifact_digest": "sha256:" + "7" * 64, "environment_digest": "sha256:" + "8" * 64,
            "started_at": "2026-08-01T00:00:00Z", "finished_at": "2026-08-01T00:01:00Z",
            "execution_kind": "real", "replay_command": "true",
            "evidence": [f"evidence/{case['id']}/manifest.json"],
        }, ensure_ascii=False), encoding="utf-8")
        log.write_text("SILENTLY REWRITTEN AFTER THE FACT\n", encoding="utf-8")
        out = tmp / "tamper-gate.json"
        subprocess.run(
            [sys.executable, str(REPO / "scripts/test-suite/run_strict_test_gate.py"), str(suite), "--output", str(out)],
            capture_output=True, text=True, cwd=REPO, check=False,
        )
        gate = json.loads(out.read_text(encoding="utf-8"))
        hits = [b for b in gate["blockers"] if "raw evidence digest mismatch" in b or "raw evidence size mismatch" in b]
        check("gate-detects-post-hoc-raw-evidence-rewrite", bool(hits), str(hits[:1]))
        check("summary-status-cannot-override-raw-evidence", gate["decision"] == "BLOCKED")
    return finish()


# --------------------------------------------------------------------------- #
# TS-GOV-04-005  identity separation and not-run semantics
# --------------------------------------------------------------------------- #
def probe_identity_separation() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        for label, mutate in (
            ("self-verified", lambda m: m["verifier"].update(id=m["executor"]["id"])),
            ("verifier-not-independent", lambda m: m["verifier"].update(independent=False)),
            ("verifier-wrong-role", lambda m: m["verifier"].update(role="executor")),
            ("executor-missing-id", lambda m: m["executor"].update(id="")),
        ):
            manifest = _sample_manifest(tmp)
            mutate(manifest)
            check(f"reject-{label}", bool(validate_evidence_manifest_shape(manifest)))
        check("distinct-identities-accepted", not validate_evidence_manifest_shape(_sample_manifest(tmp)))
    return finish()


def probe_not_run_not_pass() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        suite = temp_suite(tmp)
        catalog = load_json(suite / "cases/catalog.json")
        for case in catalog["cases"]:
            (suite / "results" / f"{case['id']}.json").write_text(
                json.dumps(
                    {
                        "case_id": case["id"],
                        "status": "not-run",
                        "artifact_digest": "sha256:" + "0" * 64,
                        "environment_digest": "sha256:" + "0" * 64,
                        "started_at": "",
                        "finished_at": "",
                        "evidence": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        out = tmp / "gate.json"
        code = subprocess.run(
            [sys.executable, str(REPO / "scripts/test-suite/run_strict_test_gate.py"), str(suite), "--output", str(out)],
            capture_output=True,
            text=True,
            cwd=REPO,
            check=False,
        ).returncode
        gate = json.loads(out.read_text(encoding="utf-8"))
        check("gate-exits-non-zero-when-nothing-ran", code != 0)
        check("decision-is-blocked", gate["decision"] == "BLOCKED")
        check("field-evidence-status-is-not-run", gate["field_evidence_status"] == "NOT_RUN")
        check("every-p0-p1-not-run-is-a-blocker", len(gate["blockers"]) == len(catalog["cases"]))
        check("zero-cases-counted-as-passed", gate["metrics"]["counts"]["passed"] == 0)

        # A single self-declared pass without signed certification must not certify.
        first = catalog["cases"][0]
        (suite / "results" / f"{first['id']}.json").write_text(
            json.dumps(
                {
                    "case_id": first["id"],
                    "status": "passed",
                    "artifact_digest": "sha256:" + "5" * 64,
                    "environment_digest": "sha256:" + "6" * 64,
                    "started_at": "2026-08-01T00:00:00Z",
                    "finished_at": "2026-08-01T00:01:00Z",
                    "execution_kind": "real",
                    "replay_command": "true",
                    "evidence": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(REPO / "scripts/test-suite/run_strict_test_gate.py"), str(suite), "--output", str(out)],
            capture_output=True,
            text=True,
            cwd=REPO,
            check=False,
        )
        gate = json.loads(out.read_text(encoding="utf-8"))
        unsigned = [b for b in gate["blockers"] if "certification" in b]
        check("unsigned-self-declared-pass-blocked", gate["decision"] == "BLOCKED" and bool(unsigned), str(unsigned[:1]))
    return finish()



# --------------------------------------------------------------------------- #
# TS-GOV-02-001  control-manifest integrity (catalog/coverage/profile/schemas)
# --------------------------------------------------------------------------- #
def probe_control_manifest() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        out = tmp / "gate.json"
        subprocess.run(
            [sys.executable, str(REPO / "scripts/test-suite/run_strict_test_gate.py"), str(SUITE), "--output", str(out)],
            capture_output=True, text=True, cwd=REPO, check=False,
        )
        gate = json.loads(out.read_text(encoding="utf-8"))
        control_blockers = [b for b in gate["blockers"] if "manifest" in b or "control" in b or "catalog:" in b or "coverage:" in b]
        check("live-controls-match-recorded-digests", not control_blockers, str(control_blockers[:2]))
        controls = gate["control_digests"]
        check("gate-reports-four-control-digests", sorted(controls) == ["catalog", "coverage_matrix", "strict_profile", "suite"])
        for name, expected in controls.items():
            check(f"control-digest-nonzero-{name}", expected != "sha256:" + "0" * 64)

        suite = temp_suite(tmp)
        catalog = load_json(suite / "cases/catalog.json")
        catalog["cases"][0]["title"] = catalog["cases"][0]["title"] + " (tampered)"
        (suite / "cases/catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        out2 = tmp / "gate-tampered.json"
        subprocess.run(
            [sys.executable, str(REPO / "scripts/test-suite/run_strict_test_gate.py"), str(suite), "--output", str(out2)],
            capture_output=True, text=True, cwd=REPO, check=False,
        )
        tampered = json.loads(out2.read_text(encoding="utf-8"))
        stale = [b for b in tampered["blockers"] if "stale or tampered" in b]
        check("catalog-tamper-detected-by-control-manifest", bool(stale), str(stale[:1]))
    return finish()


# --------------------------------------------------------------------------- #
# TS-GOV-03-001  environment / fixture factory determinism and isolation
# --------------------------------------------------------------------------- #
def probe_fixture_factory() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        first = temp_suite(tmp / "a")
        second = temp_suite(tmp / "b")
        for name in ("suite.json", "strict-profile.json", "coverage-matrix.json", "cases/catalog.json"):
            check(
                f"fixture-deterministic-{name}",
                sha256_file(first / name) == sha256_file(second / name) == sha256_file(SUITE / name),
            )
        check("fixture-starts-with-empty-results", not list((first / "results").iterdir()))
        catalog = load_json(first / "cases/catalog.json")
        catalog["cases"][0]["title"] = "mutated inside fixture"
        (first / "cases/catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        check("fixture-mutation-does-not-leak-to-source", "mutated inside fixture" not in (SUITE / "cases/catalog.json").read_text(encoding="utf-8"))
        check("fixture-mutation-does-not-leak-across-fixtures", "mutated inside fixture" not in (second / "cases/catalog.json").read_text(encoding="utf-8"))
        check("source-suite-digest-unchanged", sha256_file(SUITE / "cases/catalog.json") == sha256_file(second / "cases/catalog.json"))

        secret_markers = (
            "BEGIN RSA PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY", "BEGIN PRIVATE KEY",
            "aws_secret_access_key", "AKIA", "xoxb-", "ghp_", "sk-live", "password=",
        )
        offenders: list[str] = []
        for path in sorted(second.rglob("*")):
            if not path.is_file() or path.stat().st_size > 8_000_000:
                continue
            blob = path.read_text(encoding="utf-8", errors="ignore")
            for marker in secret_markers:
                if marker in blob:
                    offenders.append(f"{path.relative_to(second)}::{marker}")
        check("fixture-contains-no-production-secrets", not offenders, str(offenders[:3]))

        blob = (second / "cases/catalog.json").read_text(encoding="utf-8")
        check("fixture-carries-no-wall-clock-values", "generated_at" not in blob and "Z\", \"random" not in blob)
        check("fixture-rebuild-is-byte-identical", sha256_file(second / "suite.json") == sha256_file(SUITE / "suite.json"))
    return finish()



# --------------------------------------------------------------------------- #
# TS-GOV-02-001  capability -> case -> evidence traceability
# --------------------------------------------------------------------------- #
def probe_traceability() -> int:
    catalog = load_json(SUITE / "cases/catalog.json")
    cases = catalog["cases"]
    check("catalog-count-matches-declaration", catalog.get("case_count") == len(cases), f"{catalog.get('case_count')} vs {len(cases)}")

    positive: dict[int, int] = {}
    negative: dict[int, int] = {}
    for case in cases:
        if case.get("severity") != "P0":
            continue
        bucket = positive if case.get("test_type") == "happy_path" else (
            negative if case.get("test_type") in {"negative", "security"} else None
        )
        if bucket is None:
            continue
        for batch in case.get("batches", []):
            bucket[batch] = bucket.get(batch, 0) + 1
    missing_pos = [b for b in range(1, 38) if not positive.get(b)]
    missing_neg = [b for b in range(1, 38) if not negative.get(b)]
    check("every-batch-has-a-P0-positive-case", not missing_pos, f"missing={missing_pos}")
    check("every-batch-has-a-P0-negative-case", not missing_neg, f"missing={missing_neg}")

    unbound = [c["id"] for c in cases if not c.get("evidence_required")]
    check("every-case-declares-required-evidence", not unbound, str(unbound[:3]))
    unskilled = [c["id"] for c in cases if not (REPO / ".agents/skills" / c["skill"] / "SKILL.md").is_file()]
    check("every-case-binds-an-implemented-skill", not unskilled, str(unskilled[:3]))

    jsonl = SUITE / "cases/catalog.jsonl"
    check("append-only-case-history-exists", jsonl.is_file())
    if jsonl.is_file():
        history = {json.loads(line)["id"] for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()}
        live = {c["id"] for c in cases}
        check("history-covers-every-live-case", live <= history, str(sorted(live - history)[:3]))
        check("history-is-never-truncated", len(history) >= len(live), f"{len(history)} >= {len(live)}")
    return finish()


PROBES = {
    "negative-inputs": probe_negative_inputs,
    "path-escape": probe_path_escape,
    "coverage-gap": probe_coverage_gap,
    "skill-binding": probe_skill_binding,
    "environment-invalid": probe_environment_invalid,
    "evidence-valid": probe_evidence_valid,
    "evidence-tamper": probe_evidence_tamper,
    "identity-separation": probe_identity_separation,
    "not-run-not-pass": probe_not_run_not_pass,
    "control-manifest": probe_control_manifest,
    "fixture-factory": probe_fixture_factory,
    "traceability": probe_traceability,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", choices=sorted(PROBES))
    args = parser.parse_args()
    print(f"=== probe: {args.probe} ===")
    return PROBES[args.probe]()


if __name__ == "__main__":
    raise SystemExit(main())
