from __future__ import annotations

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest
from elmos_project_synthesis.scientific_sandbox import (
    ResourceBoundedSandbox,
    generate_reproducibility_receipt,
    probe_compute_hardware,
    probe_distributed_hardware,
    run_deterministic_smoke,
)


def test_probe_compute_hardware() -> None:
    hw = probe_compute_hardware()
    assert isinstance(hw, dict)
    assert "platform" in hw
    assert "architecture" in hw
    assert "cpu_count" in hw
    assert hw["cpu_count"] >= 1
    assert hw["accelerator"] in {"cpu", "cuda", "mps"}
    assert isinstance(hw["cuda_available"], bool)
    assert isinstance(hw["mps_available"], bool)


def test_probe_distributed_hardware() -> None:
    dist_hw = probe_distributed_hardware()
    assert isinstance(dist_hw, dict)
    assert "device_count" in dist_hw
    assert "supported_backends" in dist_hw
    assert "gloo" in dist_hw["supported_backends"]
    assert "cluster_orchestrator" in dist_hw
    assert "is_distributed_env" in dist_hw
    assert isinstance(dist_hw["is_distributed_env"], bool)


def test_resource_bounded_sandbox() -> None:
    sandbox = ResourceBoundedSandbox(max_cpu_seconds=10, max_memory_mb=512, timeout_seconds=10.0)

    # 1. Normal command execution
    res = sandbox.run_command(["python3", "-c", "import math; print(int(math.sqrt(64)))"])
    assert res["status"] == "PASS"
    assert res["exit_code"] == 0
    assert res["stdout"].strip() == "8"
    assert res["timed_out"] is False

    # 2. Timeout watchdog enforcement
    quick_sandbox = ResourceBoundedSandbox(timeout_seconds=0.4)
    res_timeout = quick_sandbox.run_command(["python3", "-c", "import time; time.sleep(3.0)"])
    assert res_timeout["status"] == "TIMEOUT"
    assert res_timeout["timed_out"] is True
    assert res_timeout["exit_code"] != 0


def test_run_deterministic_smoke_seed_locking() -> None:
    res1 = run_deterministic_smoke(seed=42, epochs=2)
    res2 = run_deterministic_smoke(seed=42, epochs=2)
    res_diff_seed = run_deterministic_smoke(seed=999, epochs=2)

    assert res1["status"] == "DETERMINISTIC_PASS"
    assert res2["status"] == "DETERMINISTIC_PASS"
    assert res1["deterministic_loss_sha256"] == res2["deterministic_loss_sha256"]
    assert res1["loss_history"] == res2["loss_history"]
    assert res1["deterministic_loss_sha256"] != res_diff_seed["deterministic_loss_sha256"]


def test_generate_reproducibility_receipt() -> None:
    draft = create_draft(
        name="receipt-test",
        description="Scientific experiment receipt generation test.",
        project_kind="scientific",
        languages=["python"],
    )
    approved = approve_request(
        draft,
        actor="researcher:auditor",
        approved_at="2026-09-15T12:00:00+00:00",
    )
    request = SynthesisRequest.from_mapping(approved)

    sample_files = {
        "reproducibility.py": "def set_seed(): pass\n",
        "train.py": "print('training')\n",
        "distributed_train.py": "print('distributed training')\n",
        "datasets/data_loader.py": "class Dataset: pass\n",
        "models/neural_net.py": "class Model: pass\n",
        "experiments/ablation.py": "def run_ablation(): pass\n",
    }

    receipt = generate_reproducibility_receipt(request, sample_files)
    assert receipt["kind"] == "elmos.scientific-reproducibility-receipt"
    assert receipt["project_name"] == "receipt-test"
    assert receipt["project_kind"] == "scientific"
    assert receipt["seed_lock"]["global_seed"] == 42
    assert receipt["code_tree"]["tracked_file_count"] == len(sample_files)
    assert len(receipt["code_tree"]["code_tree_sha256"]) == 64
    assert "distributed_hardware" in receipt
    assert "sandbox_isolation" in receipt
    assert receipt["sandbox_isolation"]["posix_rlimits_enforced"] is True
    assert receipt["authority_and_certification"]["evidence_grade"] == "LOCAL_EXECUTED_SELF_ATTESTED"
    assert receipt["authority_and_certification"]["production_certification"] == "NOT_CERTIFIED"
    assert len(receipt["receipt_sha256"]) == 64
