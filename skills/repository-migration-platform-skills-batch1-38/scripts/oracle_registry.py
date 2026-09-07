#!/usr/bin/env python3
"""Immutable Claim-to-Oracle registry for all Batch 1-38 obligations."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIRECTORY if (SCRIPT_DIRECTORY / "manifest.json").is_file() else SCRIPT_DIRECTORY.parent
REGISTRY_PATH = PACKAGE_ROOT / "oracle-registry.json"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class OracleObligation:
    batch: int
    claim_type: str
    claim_index: int
    claim: str
    claim_sha256: str
    oracle_id: str
    executor_id: str
    required_corpora: tuple[str, ...]
    subject_type: str


class OracleRegistry:
    def __init__(self, payload: dict[str, Any]):
        if payload.get("schema_version") != "1.0" or payload.get("namespace") != "repository-migration-platform-b01-38":
            raise ValueError("oracle registry identity is invalid")
        entries = payload.get("entries")
        if not isinstance(entries, list) or len(entries) != 347:
            raise ValueError("oracle registry must contain exactly 347 Claim obligations")
        self.payload = payload
        self.digest = digest(payload)
        self.by_claim: dict[tuple[int, str, int], OracleObligation] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("oracle registry entry must be an object")
            key = (entry.get("batch"), entry.get("claim_type"), entry.get("claim_index"))
            if key in self.by_claim or not isinstance(key[0], int) or key[1] not in {"output", "test", "external"} or not isinstance(key[2], int):
                raise ValueError("oracle registry Claim identity is invalid or duplicated")
            claim = entry.get("claim")
            if not isinstance(claim, str) or not claim or entry.get("claim_sha256") != digest(claim):
                raise ValueError("oracle registry Claim digest is invalid")
            corpora = entry.get("required_corpora")
            if not isinstance(corpora, list) or not corpora or any(item not in {"development", "negative", "holdout", "representative", "production"} for item in corpora):
                raise ValueError("oracle registry corpus obligations are invalid")
            self.by_claim[key] = OracleObligation(
                batch=key[0], claim_type=key[1], claim_index=key[2], claim=claim,
                claim_sha256=entry["claim_sha256"], oracle_id=str(entry.get("oracle_id", "")),
                executor_id=str(entry.get("executor_id", "")), required_corpora=tuple(corpora),
                subject_type=str(entry.get("subject_type", "")),
            )
        if any(not item.oracle_id or not item.executor_id or item.subject_type != "claim-oracle-result" for item in self.by_claim.values()):
            raise ValueError("oracle registry executable bindings are incomplete")

    @classmethod
    def load(cls, path: Path = REGISTRY_PATH) -> "OracleRegistry":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("oracle registry root must be an object")
        return cls(payload)

    def resolve(self, batch: int, claim_type: str, claim_index: int) -> OracleObligation:
        try:
            return self.by_claim[(batch, claim_type, claim_index)]
        except KeyError as exc:
            raise ValueError("Claim has no registered Oracle") from exc

    def validate_subject(self, value: Any, obligation: OracleObligation, corpus_role: str, outcome: str) -> None:
        required = {"schema_version", "oracle_id", "executor_id", "batch", "claim", "corpus", "decision", "checks", "limitations"}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("Claim Oracle result fields are invalid")
        if value.get("batch") != obligation.batch or value.get("claim") != {"type": obligation.claim_type, "index": obligation.claim_index, "sha256": obligation.claim_sha256}:
            raise ValueError("Claim Oracle result is bound to another Claim")
        if value.get("schema_version") != "1.0" or value.get("oracle_id") != obligation.oracle_id or value.get("executor_id") != obligation.executor_id:
            raise ValueError("Claim Oracle/executor identity is invalid")
        corpus = value.get("corpus")
        if (not isinstance(corpus, dict) or set(corpus) != {"role", "id", "sha256", "independent"} or
                corpus.get("role") != corpus_role or not isinstance(corpus.get("id"), str) or not corpus["id"] or
                not isinstance(corpus.get("sha256"), str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", corpus["sha256"]) or
                not isinstance(corpus.get("independent"), bool)):
            raise ValueError("Claim Oracle result corpus identity is invalid")
        if corpus_role in {"holdout", "representative", "production"} and corpus["independent"] is not True:
            raise ValueError(f"Claim Oracle {corpus_role} corpus is not independently owned")
        if corpus_role not in obligation.required_corpora:
            raise ValueError("Claim Oracle result corpus is not eligible")
        if value.get("decision") != outcome or outcome not in {"PASS", "FAIL", "INCONCLUSIVE", "BLOCKED", "NOT_RUN"}:
            raise ValueError("Claim Oracle result decision is invalid")
        checks = value.get("checks")
        if not isinstance(checks, list) or not checks or any(not isinstance(item, dict) or set(item) != {"name", "outcome", "detail"} for item in checks):
            raise ValueError("Claim Oracle result checks are invalid")
        if outcome == "PASS" and any(item.get("outcome") != "PASS" for item in checks):
            raise ValueError("Claim Oracle PASS contains a non-PASS check")
        if not isinstance(value.get("limitations"), list) or any(not isinstance(item, str) for item in value["limitations"]):
            raise ValueError("Claim Oracle result limitations are invalid")
