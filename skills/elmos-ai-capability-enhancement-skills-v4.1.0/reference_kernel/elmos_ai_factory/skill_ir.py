from __future__ import annotations
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable

@dataclass(frozen=True)
class SkillIssue:
    code: str
    path: str
    message: str
    severity: str = "error"

@dataclass(frozen=True)
class SkillValidation:
    valid: bool
    issues: tuple[SkillIssue, ...]
    resource_paths: tuple[str, ...]


def _safe_relative(path: str) -> bool:
    p = PurePosixPath(path)
    return bool(path) and not p.is_absolute() and ".." not in p.parts and "" not in p.parts


def validate_skill_ir(document: dict[str, Any]) -> SkillValidation:
    issues: list[SkillIssue] = []
    for field in ("skillId", "version", "trigger", "instructions", "resources", "authority", "tests"):
        if field not in document:
            issues.append(SkillIssue("missing-field", field, f"required field {field} is missing"))
    trigger = document.get("trigger", {})
    if not isinstance(trigger, dict) or not str(trigger.get("description", "")).strip():
        issues.append(SkillIssue("invalid-trigger", "trigger.description", "trigger description must be non-empty"))
    resources = document.get("resources", [])
    seen: set[str] = set()
    paths: list[str] = []
    if not isinstance(resources, list):
        issues.append(SkillIssue("invalid-resources", "resources", "resources must be an array"))
        resources = []
    for idx, resource in enumerate(resources):
        if not isinstance(resource, dict):
            issues.append(SkillIssue("invalid-resource", f"resources[{idx}]", "resource must be an object")); continue
        path = str(resource.get("path", ""))
        if not _safe_relative(path):
            issues.append(SkillIssue("unsafe-path", f"resources[{idx}].path", path or "empty path"))
        if path in seen:
            issues.append(SkillIssue("duplicate-resource", f"resources[{idx}].path", path))
        seen.add(path); paths.append(path)
        executable = bool(resource.get("executable", False))
        if executable and resource.get("kind") not in {"script", "binary"}:
            issues.append(SkillIssue("executable-kind", f"resources[{idx}]", "executable resource must declare script or binary kind"))
        digest = str(resource.get("digest", ""))
        if not digest.startswith("sha256:") or len(digest) != 71:
            issues.append(SkillIssue("missing-digest", f"resources[{idx}].digest", "sha256 digest is required"))
    authority = document.get("authority", {})
    if not isinstance(authority, dict) or authority.get("defaultDecision") != "deny":
        issues.append(SkillIssue("unsafe-authority-default", "authority.defaultDecision", "default deny is required"))
    tests = document.get("tests", [])
    if not isinstance(tests, list) or not any(isinstance(t, dict) and t.get("expectedActivation") is False for t in tests):
        issues.append(SkillIssue("missing-negative-trigger-tests", "tests", "at least one should-not-trigger test is required"))
    return SkillValidation(not any(i.severity == "error" for i in issues), tuple(issues), tuple(paths))


def permission_expansions(canonical: dict[str, Iterable[str]], emitted: dict[str, Iterable[str]]) -> dict[str, tuple[str, ...]]:
    expansions: dict[str, tuple[str, ...]] = {}
    keys = set(canonical) | set(emitted)
    for key in sorted(keys):
        allowed = set(canonical.get(key, ()))
        actual = set(emitted.get(key, ()))
        delta = tuple(sorted(actual - allowed))
        if delta:
            expansions[key] = delta
    return expansions


def portability_decision(losses: Iterable[dict[str, Any]], permission_delta: dict[str, tuple[str, ...]]) -> str:
    if permission_delta:
        return "BLOCKED"
    statuses = {str(item.get("status", "unknown")) for item in losses}
    critical = any(bool(item.get("critical", True)) and item.get("status") in {"unsupported", "unknown", "blocked"} for item in losses)
    if critical:
        return "BLOCKED"
    return "BOUNDED" if statuses - {"preserved"} else "SUPPORTED"
