import json
from pathlib import Path

from etgb.evidence import EvidenceStore


def test_evidence_redaction_seal_signature_and_tamper_detection(tmp_path: Path) -> None:
    key = b"test-only-hmac-key"
    store = EvidenceStore(tmp_path / "bundle", hmac_key=key)
    artifact = store.add_bytes(
        logical_name="logs/run.log",
        data=b"Authorization: Bearer abcdefghijklmnopqrstuvwxyz password=secret",
        media_type="text/plain",
        producer_environment="env-1",
        redact=True,
    )
    blob = store.root / artifact["blob_path"]
    assert b"secret" not in blob.read_bytes()
    store.seal({"run_id": "run-1", "candidate_digest": "sha256:" + "a" * 64})
    assert store.verify()["signature_status"] == "valid"
    blob.write_bytes(blob.read_bytes() + b"tamper")
    report = store.verify()
    assert not report["valid"]
    assert any("digest mismatch" in error for error in report["errors"])


def test_event_chain_tamper_is_detected(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "bundle")
    store.add_json(logical_name="a.json", value={"ok": True}, producer_environment="env-1")
    manifest = json.loads(store.manifest_path.read_text())
    manifest["events"][0]["payload"]["logical_name"] = "changed.json"
    store.manifest_path.write_text(json.dumps(manifest))
    assert any("event digest mismatch" in e for e in store.verify()["errors"])
