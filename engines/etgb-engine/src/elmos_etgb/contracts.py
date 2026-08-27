"""Requirement-contract compilation and domain case validation."""

from __future__ import annotations

import re
from typing import Any, Mapping


class ContractError(ValueError):
    """Raised for unsafe, contradictory, or incomplete generation requirements."""


_UNSAFE_PATTERNS = (
    re.compile(r"(?i)plain\s*text\s*password|plaintext\s*password|明文密码"),
    re.compile(r"(?i)embed\s+(?:the\s+)?production\s+secret|hardcode\s+(?:the\s+)?api\s*key|嵌入生产密钥"),
)


def compile_requirement(requirement: str | Mapping[str, Any], *, contract_id: str = "REQ-ETGB") -> dict[str, Any]:
    """Compile a minimal executable contract without hiding assumptions."""

    if isinstance(requirement, Mapping):
        raw_text = str(requirement.get("text", requirement.get("requirement", "")))
        supplied = dict(requirement)
    else:
        raw_text = str(requirement)
        supplied = {}
    if not raw_text.strip():
        raise ContractError("requirement text is required")
    unsafe = [pattern.pattern for pattern in _UNSAFE_PATTERNS if pattern.search(raw_text)]
    if unsafe:
        raise ContractError("unsafe requirement refused: production secrets or plaintext passwords")
    actors = list(supplied.get("actors", [{"id": "operator", "responsibility": "invoke the service"}]))
    functional = list(supplied.get("functional_requirements", [{"id": "FR-001", "text": raw_text, "critical": True}]))
    qualities = list(supplied.get("quality_attributes", [{"id": "QA-SEC-001", "text": "credentials are externalized and least-privileged", "critical": True}, {"id": "QA-REL-001", "text": "retries are idempotent and failures are observable", "critical": True}]))
    acceptance = list(supplied.get("acceptance_tests", [{"id": "AT-001", "given": "a valid request", "when": "the generated service is started", "then": "the request contract and failure semantics are satisfied"}]))
    assumptions = list(supplied.get("assumptions", [{"id": "ASM-001", "text": "deployment credentials and external endpoints are supplied at runtime", "editable": True}]))
    conflicts = list(supplied.get("conflicts", []))
    if not conflicts and re.search(r"(?i)impossible|unbounded|no\s+retention|without\s+authentication", raw_text):
        conflicts.append({"id": "CONFLICT-001", "text": "requirement contains a potentially unsafe or unbounded constraint", "resolution": "human-review-required"})
    return {
        "id": contract_id,
        "source_text": raw_text,
        "actors": actors,
        "functional_requirements": functional,
        "quality_attributes": qualities,
        "acceptance_tests": acceptance,
        "assumptions": assumptions,
        "conflicts": conflicts,
        "change_sequence": list(supplied.get("change_sequence", [])),
        "decision": "human-review-required" if conflicts else "ready-for-generation",
        "unsupported_or_manual": [],
    }


def validate_case_contract(case: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    required = ("id", "business_line", "source", "target", "requirements", "execution", "oracles", "coverage", "gates", "provenance")
    errors.extend(f"missing field: {field}" for field in required if field not in case)
    execution = case.get("execution", {})
    if isinstance(execution, Mapping):
        if not execution.get("adapter"):
            errors.append("execution.adapter is required")
        if not isinstance(execution.get("timeout_seconds"), int) or execution.get("timeout_seconds", 0) < 1:
            errors.append("execution.timeout_seconds must be a positive integer")
    else:
        errors.append("execution must be an object")
    coverage = case.get("coverage", {})
    if not isinstance(coverage, Mapping) or not coverage.get("capability_id") or not isinstance(coverage.get("dimensions"), Mapping) or not coverage.get("dimensions"):
        errors.append("coverage must contain a capability_id and non-empty dimensions")
    if not isinstance(case.get("oracles"), list) or not case.get("oracles"):
        errors.append("at least one independent oracle is required")
    if not isinstance(case.get("requirements"), list) or not case.get("requirements"):
        errors.append("at least one requirement is required")
    return errors


DOMAIN_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "spring-modernization": ("inventory", "baseline", "transform", "build", "dual-run", "state-diff"),
    "cross-language": ("inventory", "source-baseline", "translate", "target-build", "differential-execute", "state-diff"),
    "project-generation": ("requirements", "generate", "build", "acceptance"),
    "sql-conversion": ("provision-source-target", "seed-normalized-data", "execute-source", "convert", "execute-target", "result-diff", "state-diff"),
    "cross-cutting": (),
}


def validate_domain_case(case: Mapping[str, Any]) -> list[str]:
    errors = validate_case_contract(case)
    line = case.get("business_line")
    phases = set(case.get("execution", {}).get("phases", [])) if isinstance(case.get("execution"), Mapping) else set()
    # The offline smoke fixtures exercise the same contracts through a concrete
    # local adapter and intentionally do not model the full external phase graph.
    if case.get("family") == "smoke" or line == "cross-cutting" or case.get("family") == "requirement-reasoning":
        required_phases: tuple[str, ...] = ()
    elif line == "project-generation" and case.get("family") == "evolution":
        required_phases = ("baseline", "change-impact", "generate-diff", "migrate", "old-tests", "new-tests", "rollback-test")
    else:
        required_phases = DOMAIN_REQUIREMENTS.get(str(line), ())
    missing = [phase for phase in required_phases if phase not in phases]
    errors.extend(f"missing {line} phase: {phase}" for phase in missing)
    return errors
