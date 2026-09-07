import json
from pathlib import Path

import pytest

from etgb.candidate import freeze_candidate, validate_candidate
from etgb.checkpoint import CheckpointStore


def candidate() -> dict:
    return {
        "candidate_id": "rc-1", "source_commit": "a" * 40, "model": "gpt-5.6-pro",
        "model_revision": "2026-08-27", "prompt_digest": "sha256:" + "1" * 64,
        "skill_manifest_digest": "sha256:" + "2" * 64, "rule_bundle_digest": "sha256:" + "3" * 64,
        "toolchain_image_digest": "sha256:" + "4" * 64, "oracle_version": "etgb-oracle-v1.1.0",
        "normalization_version": "etgb-normalize-v1.1.0",
    }


def test_candidate_freeze_is_immutable_and_rejects_aliases() -> None:
    frozen = freeze_candidate(candidate())
    assert frozen["candidate_digest"].startswith("sha256:")
    bad = candidate(); bad["model_revision"] = "latest"
    assert any("mutable alias" in error for error in validate_candidate(bad))


def test_checkpoint_digest_artifact_and_resume_contract(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"; artifact.write_text("ok")
    import hashlib
    store = CheckpointStore(tmp_path / "cp")
    record = store.save(
        run_id="r", phase="BUILDING", candidate_digest="sha256:" + "a" * 64,
        plan_digest="sha256:" + "b" * 64, environment_digest="sha256:" + "c" * 64,
        fencing_token=3, artifacts=[{"path": str(artifact), "sha256": hashlib.sha256(b"ok").hexdigest()}],
        resume_payload={"next": "validate"},
    )
    assert store.verify("r")["valid"]
    assert not store.resume_contract("r", candidate_digest=record["candidate_digest"],
                                     plan_digest=record["plan_digest"], current_fencing_token=3)["resumable"]
    assert store.resume_contract("r", candidate_digest=record["candidate_digest"],
                                 plan_digest=record["plan_digest"], current_fencing_token=4)["resumable"]
    raw = json.loads((tmp_path / "cp/r.checkpoint.json").read_text())
    raw["phase"] = "TAMPERED"
    (tmp_path / "cp/r.checkpoint.json").write_text(json.dumps(raw))
    assert not store.verify("r")["valid"]
