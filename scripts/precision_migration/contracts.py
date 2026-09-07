#!/usr/bin/env python3
"""Compile and execute exact Precision Migration Skill contracts.

Every child Skill owns a distinct handler identity and immutable contract.  The
shared executor is deliberately data-only: a contract may select validation
rules and repository surfaces, but never a command, module, or executable.
Domain execution that is not represented by verified evidence remains
CONDITIONALLY_VERIFIED instead of being promoted by contract conformance.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = ROOT / "docs" / "precision-migration-b01-44" / "executable-contracts.json"
ALLOWED_MODES = frozenset({"assess", "transform", "validate", "repair", "certify"})
HIGH_RISK_BATCHES = frozenset({7, 19, 20, 21, 22, 23, 24, 25, 26, 30, 32, 33, 34, 35, 41, 42, 44})


class ContractError(ValueError):
    pass


def _section(markdown: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)",
        markdown,
    )
    return match.group(1).strip() if match else ""


def _items(text: str) -> list[str]:
    values: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.+?)\s*$", line)
        if match:
            values.append(match.group(1))
    return values


def _failure_codes(text: str) -> list[str]:
    section = _section(text, "Failure codes")
    return sorted(set(re.findall(r"`([A-Z][A-Z0-9_]+)`", section)))


def modes_for_batch(batch: int) -> list[str]:
    if batch <= 4:
        return ["assess"]
    if batch <= 10:
        return ["assess", "validate"]
    if batch <= 27:
        return ["transform", "validate", "repair"]
    if batch <= 35:
        return ["validate", "repair", "certify"]
    if batch <= 40:
        return ["assess", "transform", "validate"]
    if batch == 41:
        return ["validate", "certify"]
    if batch == 42:
        return ["validate", "repair", "certify"]
    if batch == 43:
        return ["assess", "validate", "repair"]
    return ["assess", "validate", "certify"]


def compile_contract(record: dict[str, Any], source_path: Path) -> dict[str, Any]:
    """Compile one immutable Markdown Skill into a bounded executable contract."""
    if record.get("kind") != "skill" or not isinstance(record.get("batch"), int):
        raise ContractError("only child Skills can be compiled")
    source = source_path.read_bytes()
    text = source.decode("utf-8")
    source_name = str(record["source_name"])
    inputs = _items(_section(text, "Inputs"))
    outputs = _items(_section(text, "Outputs"))
    workflow = _items(_section(text, "Workflow"))
    gates = _items(_section(text, "Validation gates"))
    done = _items(_section(text, "Definition of done"))
    purpose = _section(text, "Purpose")
    if not all((purpose, inputs, outputs, workflow, gates, done)):
        raise ContractError(f"Skill lacks executable contract sections: {source_name}")
    payload_without_digest = {
        "schema_version": 1,
        "namespace": "precision-migration-b01-44",
        "skill": record["name"],
        "source_skill": source_name,
        "batch": record["batch"],
        "handler_id": f"precision-skill-v1:{source_name}",
        "source_path": record["source_path"],
        "source_sha256": "sha256:" + hashlib.sha256(source).hexdigest(),
        "purpose": purpose,
        "inputs": inputs,
        "outputs": outputs,
        "workflow": workflow,
        "validation_gates": gates,
        "definition_of_done": done,
        "failure_codes": _failure_codes(text),
        "supported_modes": modes_for_batch(int(record["batch"])),
        "risk_tier": "P0" if int(record["batch"]) in HIGH_RISK_BATCHES else "P1",
        "execution_policy": {
            "repository_commands_from_contract": False,
            "network": "deny",
            "source": "read-only",
            "output": "write-once-dedicated-directory",
            "unresolved_differences": "block",
            "test_weakening": "forbidden",
            "external_evidence_default": "NOT_RUN",
        },
    }
    encoded = json.dumps(
        payload_without_digest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **payload_without_digest,
        "contract_digest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


class ContractRegistry:
    def __init__(self, payload: dict[str, Any]) -> None:
        if payload.get("schema_version") != 1 or payload.get("namespace") != "precision-migration-b01-44":
            raise ContractError("executable contract registry identity is invalid")
        contracts = payload.get("contracts")
        if not isinstance(contracts, list) or len(contracts) != 587:
            raise ContractError("executable contract registry must contain exactly 587 contracts")
        self.payload = payload
        self.by_skill: dict[str, dict[str, Any]] = {}
        self.by_handler: dict[str, dict[str, Any]] = {}
        for contract in contracts:
            if not isinstance(contract, dict):
                raise ContractError("executable contract entry must be an object")
            skill = contract.get("skill")
            handler = contract.get("handler_id")
            if not isinstance(skill, str) or not isinstance(handler, str):
                raise ContractError("executable contract identity is invalid")
            if skill in self.by_skill or handler in self.by_handler:
                raise ContractError("duplicate executable contract identity")
            expected = dict(contract)
            observed_digest = expected.pop("contract_digest", None)
            encoded = json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if observed_digest != "sha256:" + hashlib.sha256(encoded).hexdigest():
                raise ContractError(f"executable contract digest mismatch: {skill}")
            modes = contract.get("supported_modes")
            if not isinstance(modes, list) or not modes or set(modes) - ALLOWED_MODES:
                raise ContractError(f"executable contract modes are invalid: {skill}")
            self.by_skill[skill] = contract
            self.by_handler[handler] = contract

    @classmethod
    def load(cls, path: Path = CONTRACTS_PATH) -> "ContractRegistry":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def resolve(self, skill: str, handler_id: str) -> dict[str, Any]:
        contract = self.by_skill.get(skill)
        if contract is None or contract.get("handler_id") != handler_id:
            raise ContractError("Skill and handler are not bound by the executable contract registry")
        return contract


def validate_contract_binding(
    contract: dict[str, Any],
    *,
    skill: str,
    source_skill: str,
    mode: str,
) -> None:
    if contract.get("skill") != skill or contract.get("source_skill") != source_skill:
        raise ContractError("executable contract source identity diverged")
    if mode not in contract.get("supported_modes", []):
        raise ContractError(f"mode {mode} is not supported by exact Skill contract")


def contract_summary(contract: dict[str, Any], verified_assets: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return a deterministic execution record without interpreting text as code."""
    assets = [
        {
            "uri": item["uri"],
            "digest": item["digest"],
            "size_bytes": item["size_bytes"],
            "media_type": item["media_type"],
        }
        for item in verified_assets
    ]
    return {
        "schema_version": 1,
        "skill": contract["skill"],
        "source_skill": contract["source_skill"],
        "handler_id": contract["handler_id"],
        "contract_digest": contract["contract_digest"],
        "risk_tier": contract["risk_tier"],
        "verified_inputs": assets,
        "workflow": contract["workflow"],
        "validation_gates": contract["validation_gates"],
        "required_outputs": contract["outputs"],
        "domain_execution": "NOT_RUN",
        "native_toolchain": "NOT_RUN",
        "holdout": "NOT_RUN",
        "representative_workload": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "external_evidence": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }
