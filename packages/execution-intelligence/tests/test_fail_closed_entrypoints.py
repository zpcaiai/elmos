import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from conftest import ROOT

MAKEFILE = ROOT / "Makefile"
WORKFLOW = ROOT.parents[1] / ".github" / "workflows" / "execution-intelligence.yml"
MAKE = shutil.which("make")


def _blocked_evidence(directory: Path) -> None:
    directory.mkdir()
    (directory / "calibration.json").write_text(
        json.dumps({"valid_samples": 3, "runtime_samples": 3, "token_samples": 0}),
        encoding="utf-8",
    )


def _run_make(*args: str) -> subprocess.CompletedProcess[str]:
    assert MAKE is not None
    return subprocess.run(  # noqa: S603 - resolved executable and test-owned arguments
        [MAKE, *args, f"PY={sys.executable}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_make_certify_returns_nonzero_for_blocked_evidence(tmp_path):
    evidence = tmp_path / "blocked"
    _blocked_evidence(evidence)

    completed = _run_make("certify", f"OUT={evidence}")

    assert completed.returncode != 0
    assert "Decision: BLOCK" in completed.stdout
    report = json.loads((evidence / "production-readiness.json").read_text(encoding="utf-8"))
    assert report["decision"] == "block"
    calibrated = next(gate for gate in report["gates"] if gate["id"] == "calibrated")
    assert calibrated["status"] == "FAIL"
    assert "门槛 20" in calibrated["detail"]


def test_make_all_propagates_the_certification_failure(tmp_path):
    evidence = tmp_path / "blocked"
    _blocked_evidence(evidence)
    harness = tmp_path / "Makefile"
    harness.write_text(
        f"include {MAKEFILE}\n\n"
        "lint test scan audit dag validate forecast plan execute route chaos calibrate advise mix schemas:\n"
        "\t@:\n",
        encoding="utf-8",
    )

    completed = _run_make("-f", str(harness), "all", f"OUT={evidence}")

    assert completed.returncode != 0
    assert "Decision: BLOCK" in completed.stdout


def test_ci_treats_synthetic_block_as_a_negative_control_not_readiness_pass():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "|| true" not in workflow
    assert re.search(
        r'- name: "Negative control: synthetic evidence must remain BLOCK"\s+run: \|',
        workflow,
    )
    assert "make certify OUT=/tmp/ci" in workflow
    assert 'test "$status" -ne 0' in workflow
    assert 'report["decision"] == "block"' in workflow
