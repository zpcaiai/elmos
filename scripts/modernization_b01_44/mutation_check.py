#!/usr/bin/env python3
"""Prove the conformance suite is load bearing.

A test that passes proves nothing on its own - it might assert something the
code never had to do.  This harness deletes one enforcement at a time from the
runtime, re-runs the suite in an isolated copy of the tree, and requires the
suite to go red.  A mutation that the tests survive is reported as SURVIVED and
fails the check: it marks a rule nothing actually verifies.

Run:  python3 -m scripts.modernization_b01_44.mutation_check
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
PKG = "scripts/modernization_b01_44"
TESTS = "tests/modernization-b01-44"


@dataclass(frozen=True)
class Mutation:
    """Delete one enforcement by rewriting a single source fragment."""

    mutation_id: str
    target: str
    old: str
    new: str
    expects: str

    def apply(self, tree: Path) -> None:
        path = tree / self.target
        text = path.read_text(encoding="utf-8")
        if self.old not in text:
            raise SystemExit(f"mutation {self.mutation_id}: anchor not found in {self.target}")
        path.write_text(text.replace(self.old, self.new, 1), encoding="utf-8")


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        "M01-tenant-isolation",
        f"{PKG}/policy.py",
        "        if principal.tenant_id != resource_tenant_id:",
        "        if False:",
        "T005 cross-tenant access must be denied",
    ),
    Mutation(
        "M02-trust-boundary",
        f"{PKG}/policy.py",
        "            raise TrustBoundaryViolation(",
        "            return None or TrustBoundaryViolation(",
        "T002 unknown input fields must be refused",
    ),
    Mutation(
        "M03-agent-boundary",
        f"{PKG}/policy.py",
        "        if not principal.is_agent:\n            return",
        "        if True:\n            return",
        "T006 agents must not write tests/golden/gate",
    ),
    Mutation(
        "M04-upstream-certificate",
        f"{PKG}/certification.py",
        "        if not refs:\n            raise UpstreamCertificateMissing(",
        "        if False:\n            raise UpstreamCertificateMissing(",
        "T003 a missing upstream certificate must block execution",
    ),
    Mutation(
        "M05-conservative-gate",
        f"{PKG}/certification.py",
        '        granted = "blocked"\n        for candidate in ("experimental", "limited", "certified"):\n            if required_evidence(candidate, cert_policy) <= satisfied:\n                granted = candidate',
        '        granted = requested_status',
        "T004 status must be derived from evidence, not requested",
    ),
    Mutation(
        "M06-holdout-requirement",
        f"{PKG}/certification.py",
        "    extra = {\n        scope\n        for flag, scope in POLICY_EVIDENCE_FLAGS.items()\n        if (policy or {}).get(flag, True)\n    }",
        "    extra = set()",
        "T011 holdout/representative evidence must be required for certified",
    ),
    Mutation(
        "M07-provider-drift",
        f"{PKG}/adapters.py",
        "        reports = [r for r in self.detect_drift(pins) if r.breaking]",
        "        reports = []",
        "T007 breaking provider drift must be refused",
    ),
    Mutation(
        "M08-event-idempotency",
        f"{PKG}/workflow.py",
        "        if event_id in run.applied_events:",
        "        if False:",
        "T008 duplicate events must produce one effect",
    ),
    Mutation(
        "M09-lease-reaping",
        f"{PKG}/workflow.py",
        '            if run.lease.is_expired(now) and run.state in ("running", "created"):',
        "            if False:",
        "T009 an expired lease must move the run to reconciling",
    ),
    Mutation(
        "M10-compensation",
        f"{PKG}/workflow.py",
        "        for step, undo in reversed(run.compensations):",
        "        for step, undo in []:",
        "T010 compensations must actually run",
    ),
    Mutation(
        "M11-evidence-expiry",
        f"{PKG}/evidence.py",
        "    def is_expired(self, now: datetime) -> bool:\n        if self.expires_at is None:\n            return False",
        "    def is_expired(self, now: datetime) -> bool:\n        if True:\n            return False",
        "T012 expired evidence must turn certificates stale",
    ),
    Mutation(
        "M12-model-claim-is-evidence",
        f"{PKG}/evidence.py",
        "NON_EXECUTION_TRUST = frozenset({\"unknown\", \"model-inferred\"})",
        "NON_EXECUTION_TRUST = frozenset()",
        "a model claim must not count as execution evidence",
    ),
    Mutation(
        "M13-worker-invariance",
        f"{PKG}/engine.py",
        "            if result.output_digest != baseline.output_digest:",
        "            if False:",
        "determinism under varying worker counts must be verified",
    ),
    Mutation(
        "M14-stable-ordering",
        f"{PKG}/engine.py",
        "        ordered: Sequence[Any] = stable_sort(units)",
        "        ordered: Sequence[Any] = list(units)",
        "work units must be stably ordered before execution",
    ),
    Mutation(
        "M15-unknown-preservation",
        f"{PKG}/evidence.py",
        "        if left is UNKNOWN or right is UNKNOWN:\n            unknown.append(key)",
        "        if False:\n            unknown.append(key)",
        "reconciliation must never collapse unknown into match",
    ),
    Mutation(
        "M16-budget-ceiling",
        f"{PKG}/corpus.py",
        "        if self.spent + amount > self.limit:",
        "        if False:",
        "an exhausted budget must refuse rather than continue",
    ),
    Mutation(
        "M17-approval-binding",
        f"{PKG}/approval.py",
        "            if approval.request_digest != request_digest:",
        "            if False:",
        "an approval must not survive a change to the request",
    ),
    Mutation(
        "M18-dual-control",
        f"{PKG}/approval.py",
        '        needed = 2 if criticality == "critical" else 1',
        "        needed = 1",
        "critical actions must require two distinct approvers",
    ),
    Mutation(
        "M19-manifest-verification",
        f"{PKG}/packages.py",
        "        if actual != entry[\"sha256\"]:",
        "        if False:",
        "package digests must be verified against the manifest",
    ),
    Mutation(
        "M20-schema-closure",
        f"{PKG}/validation.py",
        '        if schema.get("additionalProperties") is False:',
        "        if False:",
        "closed schemas must reject undeclared properties",
    ),
)


def build_tree(destination: Path) -> None:
    """An isolated copy: real code, symlinked package data."""

    (destination / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / PKG, destination / PKG)
    shutil.copytree(ROOT / TESTS, destination / TESTS)
    (destination / "skills").mkdir(exist_ok=True)
    os.symlink(
        ROOT / "skills" / "modernization-skills-batch-01-44",
        destination / "skills" / "modernization-skills-batch-01-44",
    )


def run_suite(tree: Path, *, pattern: str = "test_*.py") -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(tree)
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", TESTS, "-p", pattern],
        cwd=tree,
        capture_output=True,
        text=True,
        env=env,
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="run a subset of mutation ids")
    parser.add_argument("--pattern", default="test_*.py")
    args = parser.parse_args(list(argv) if argv is not None else None)

    selected = [m for m in MUTATIONS if not args.only or m.mutation_id in args.only]

    with tempfile.TemporaryDirectory(prefix="b0144-baseline-") as tmp:
        baseline_tree = Path(tmp) / "tree"
        build_tree(baseline_tree)
        baseline = run_suite(baseline_tree, pattern=args.pattern)
    if baseline.returncode != 0:
        print("BASELINE IS RED - fix the suite before mutation testing")
        print(baseline.stdout[-4000:])
        print(baseline.stderr[-4000:])
        return 2
    print(f"baseline: green ({_ran(baseline)} tests)")

    survived: list[Mutation] = []
    for mutation in selected:
        with tempfile.TemporaryDirectory(prefix="b0144-mut-") as tmp:
            tree = Path(tmp) / "tree"
            build_tree(tree)
            mutation.apply(tree)
            proc = run_suite(tree, pattern=args.pattern)
        killed = proc.returncode != 0
        status = "killed " if killed else "SURVIVED"
        print(f"  {status} {mutation.mutation_id:<28} {mutation.expects}")
        if not killed:
            survived.append(mutation)

    print()
    print(f"{len(selected) - len(survived)}/{len(selected)} mutations killed")
    if survived:
        print("SURVIVING MUTATIONS - these rules are not verified by any test:")
        for mutation in survived:
            print(f"  {mutation.mutation_id}: {mutation.expects}")
        return 1
    return 0


def _ran(proc: subprocess.CompletedProcess) -> str:
    for line in proc.stderr.splitlines():
        if line.startswith("Ran "):
            return line.split()[1]
    return "?"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
