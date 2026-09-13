#!/usr/bin/env python3
"""Scaffold Elmos Trust Core directories without overwriting existing files."""

from __future__ import annotations
import argparse
import shutil
from pathlib import Path

DIRS = [
    "elmos-trust-core/contracts/schemas",
    "elmos-trust-core/authority-service/snapshot",
    "elmos-trust-core/authority-service/ticket",
    "elmos-trust-core/authority-service/verification",
    "elmos-trust-core/truth-runner-service/ticket-verifier",
    "elmos-trust-core/truth-runner-service/sandbox",
    "elmos-trust-core/truth-runner-service/executor",
    "elmos-trust-core/truth-runner-service/adapter",
    "elmos-trust-core/truth-runner-service/parser",
    "elmos-trust-core/truth-runner-service/evidence",
    "elmos-trust-core/evidence-service/event",
    "elmos-trust-core/evidence-service/artifact",
    "elmos-trust-core/evidence-service/provenance",
    "elmos-trust-core/evidence-service/persistence",
    "elmos-trust-core/policy-gate-service/opa",
    "elmos-trust-core/policy-gate-service/decision",
    "elmos-trust-core/policies/base",
    "elmos-trust-core/case-catalog/golden",
    "elmos-trust-core/runner-images/java-spring-e3",
    "elmos-trust-core/integration-tests/functional",
    "elmos-trust-core/integration-tests/adversarial",
    "elmos-trust-core/integration-tests/security",
]

README = """# Elmos Trust Core\n\nScaffolded by the `elmos-proof-driven-certification` skill.\n\nImplementation dependency order:\n\n1. WP-TRUST-001 Canonical Contracts\n2. WP-TRUST-002 Snapshot Authority\n3. WP-TRUST-003 VerificationTicket\n4. WP-TRUST-004 Golden Truth Runner (`java-spring-e3`)\n5. WP-TRUST-005 Evidence Append Store\n6. WP-TRUST-006 OPA Gate\n7. WP-TRUST-007 Anti-Fake Adversarial Suite\n\nDo not claim completion from generated files. Execute real validation.\n"""

WORK_PACKAGES = """# Work Packages\n\n- [ ] WP-TRUST-001 Canonical Contracts\n- [ ] WP-TRUST-002 Snapshot Authority\n- [ ] WP-TRUST-003 VerificationTicket issuer/verifier\n- [ ] WP-TRUST-004 Golden Truth Runner\n- [ ] WP-TRUST-005 Evidence Append Store\n- [ ] WP-TRUST-006 OPA Certification Gate\n- [ ] WP-TRUST-007 Anti-Fake Adversarial Suite\n\nProduction: WP-TRUST-101..116 only after the MVP trust loop is demonstrated.\n"""

RUNNER_PROFILE = """id: java-spring-e3\nversion: 1\nruntime:\n  network: restricted\nsteps:\n  - id: compile\n    executor: PROCESS\n    argv: [/opt/elmos/maven/bin/mvn, -B, package, -DskipTests]\n    required: true\n    timeoutSeconds: 600\n  - id: hidden-unit\n    executor: JUNIT_PLATFORM\n    required: true\n  - id: integration\n    executor: INTEGRATION_HARNESS\n    required: true\n  - id: smoke\n    executor: HTTP_HARNESS\n    required: true\n"""

CASE_SET = """id: spring-boot4-golden-e3\nversion: 1\nrunnerProfile: java-spring-e3\nrequiredSteps: [compile, hidden-unit, integration, smoke]\npolicy:\n  minimumTests: 20\n  zeroFailures: true\n  requireStructuredReport: true\n  failClosed: true\n"""


def create_file(path: Path, content: str, dry: bool) -> None:
    if path.exists():
        print(f"SKIP existing: {path}")
        return
    print(f"CREATE: {path}")
    if not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def copy_if_missing(src: Path, dst: Path, dry: bool) -> None:
    if dst.exists():
        print(f"SKIP existing: {dst}")
        return
    print(f"COPY: {src} -> {dst}")
    if not dry:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="target repository root")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    skill = Path(__file__).resolve().parent.parent

    for rel in DIRS:
        p = root / rel
        print(f"DIR: {p}")
        if not args.dry_run:
            p.mkdir(parents=True, exist_ok=True)

    create_file(root / "elmos-trust-core/README.md", README, args.dry_run)
    create_file(root / "elmos-trust-core/WORK_PACKAGES.md", WORK_PACKAGES, args.dry_run)
    create_file(root / "elmos-trust-core/runner-images/java-spring-e3/runner-profile.yaml", RUNNER_PROFILE, args.dry_run)
    create_file(root / "elmos-trust-core/case-catalog/golden/spring-boot4-golden-e3.yaml", CASE_SET, args.dry_run)

    for src in (skill / "schemas").glob("*.json"):
        copy_if_missing(src, root / "elmos-trust-core/contracts/schemas" / src.name, args.dry_run)
    for src in (skill / "policies/base").glob("*.rego"):
        copy_if_missing(src, root / "elmos-trust-core/policies/base" / src.name, args.dry_run)

    print("\nScaffold complete." if not args.dry_run else "\nDry run complete; no files changed.")
    print("Next: implement WP-TRUST-001 and execute real tests before marking it complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
