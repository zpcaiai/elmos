"""SARIF 2.1.0 output.

Findings from verification, security and anti-cheat all leave this package in
one machine-readable format, so a consumer needs one parser rather than three.
Only the subset of SARIF that carries meaning here is emitted, and every
``result`` is anchored to a real file and line — a finding with no location is
not actionable and is not produced.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .contracts import sha256_payload

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"

#: SARIF levels, ordered by severity so a run's worst level is computable.
LEVELS = ("none", "note", "warning", "error")


@dataclass(frozen=True, slots=True)
class SarifRule:
    id: str
    name: str
    short_description: str
    full_description: str = ""
    default_level: str = "warning"
    help_uri: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "shortDescription": {"text": self.short_description},
            "defaultConfiguration": {"level": self.default_level},
        }
        if self.full_description:
            payload["fullDescription"] = {"text": self.full_description}
        if self.help_uri:
            payload["helpUri"] = self.help_uri
        return payload


@dataclass(frozen=True, slots=True)
class SarifResult:
    rule_id: str
    level: str
    message: str
    path: str
    start_line: int = 1
    end_line: int | None = None
    start_column: int | None = None
    fingerprint: str = ""
    properties: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        region: dict[str, Any] = {"startLine": max(1, self.start_line)}
        if self.end_line is not None:
            region["endLine"] = max(region["startLine"], self.end_line)
        if self.start_column is not None:
            region["startColumn"] = max(1, self.start_column)
        payload: dict[str, Any] = {
            "ruleId": self.rule_id,
            "level": self.level,
            "message": {"text": self.message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": self.path},
                        "region": region,
                    }
                }
            ],
        }
        payload["partialFingerprints"] = {
            "elmos/v1": self.fingerprint
            or sha256_payload({"rule": self.rule_id, "path": self.path, "line": self.start_line})[:32]
        }
        if self.properties:
            payload["properties"] = dict(sorted(self.properties.items()))
        return payload


@dataclass(frozen=True, slots=True)
class SarifRun:
    tool_name: str
    tool_version: str
    rules: tuple[SarifRule, ...]
    results: tuple[SarifResult, ...]
    invocation_successful: bool = True
    properties: Mapping[str, Any] = field(default_factory=dict)

    @property
    def worst_level(self) -> str:
        found = [item.level for item in self.results if item.level in LEVELS]
        return max(found, key=LEVELS.index) if found else "none"

    def to_payload(self) -> dict[str, Any]:
        return {
            "tool": {
                "driver": {
                    "name": self.tool_name,
                    "version": self.tool_version,
                    "informationUri": "https://schemas.elmos.dev/repository-refactoring",
                    "rules": [rule.to_payload() for rule in self.rules],
                }
            },
            "invocations": [{"executionSuccessful": self.invocation_successful}],
            "results": [item.to_payload() for item in self.results],
            "properties": dict(sorted(self.properties.items())),
        }


def build_log(runs: Sequence[SarifRun]) -> dict[str, Any]:
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [run.to_payload() for run in runs],
    }


def log_digest(log: Mapping[str, Any]) -> str:
    return sha256_payload(log)


def count_by_level(runs: Iterable[SarifRun]) -> dict[str, int]:
    counts = dict.fromkeys(LEVELS, 0)
    for run in runs:
        for result in run.results:
            if result.level in counts:
                counts[result.level] += 1
    return counts


def blocking_results(runs: Iterable[SarifRun]) -> tuple[SarifResult, ...]:
    return tuple(result for run in runs for result in run.results if result.level == "error")


__all__ = [
    "LEVELS",
    "SARIF_SCHEMA",
    "SARIF_VERSION",
    "SarifResult",
    "SarifRule",
    "SarifRun",
    "blocking_results",
    "build_log",
    "count_by_level",
    "log_digest",
]
