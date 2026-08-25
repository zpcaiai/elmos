#!/usr/bin/env python3
"""Evaluate content-addressed Spring project equivalence corpus evidence.

This tool deliberately computes only an observed rate for the declared exact
Spring tuple and eligible whole-repository corpus.  It does not certify a pack
and cannot turn an exact development fixture into a universal migration rate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.trust import (  # noqa: E402
    canonical_digest,
    read_regular_file_once,
)
from scripts.batch30.validate_external_certification_intake import (  # noqa: E402
    CUSTOMER_AUTHORIZATION_ROLE,
    EVIDENCE_ROLES,
    ExternalIntakeError,
    evaluate_external_intake_file,
)


MANIFEST_SCHEMA_VERSION = "elmos.spring-corpus-equivalence-manifest.v1"
PROJECT_EVIDENCE_SCHEMA_VERSION = "elmos.spring-project-equivalence-evidence.v1"
RESULT_SCHEMA_VERSION = "elmos.spring-corpus-equivalence-result.v1"

CORPUS_ROLES = ("development", "holdout", "representative", "customer")
AGGREGATE_ROLES = ("holdout", "representative", "customer")
PROJECT_SCOPES = {"EXACT_FIXTURE", "WHOLE_REPOSITORY"}
PROJECT_OUTCOMES = {"EQUIVALENT", "NOT_EQUIVALENT", "INCONCLUSIVE", "NOT_RUN"}
CHECK_STATUSES = {"PASS", "FAIL", "INCONCLUSIVE", "NOT_RUN"}
CHECK_NAMES = (
    "source_build",
    "target_build",
    "source_startup",
    "target_startup",
    "behavior_oracle",
    "test_integrity",
)
PROJECT_EVIDENCE_TYPES = {
    "holdout": "customer_holdout",
    "representative": "independent_review",
    "customer": "authorized_customer_repository",
}
EXTERNAL_INTAKE_STATUSES = {"SUBMITTED", "NOT_RUN"}
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{1,199}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
RELATIVE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+\-]*$")
MUTABLE_VERSION = re.compile(r"(^|[._+\-])(latest|current|snapshot|nightly|main|master|x)([._+\-]|$)", re.I)
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024


class CorpusEquivalenceError(ValueError):
    """Raised when the corpus manifest itself is unsafe or ambiguous."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CorpusEquivalenceError(f"{label} must be an object")
    return value


def _exact_fields(
    value: dict[str, Any],
    required: set[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    missing = sorted(required - set(value))
    extra = sorted(set(value) - allowed)
    if missing or extra:
        raise CorpusEquivalenceError(f"{label} fields are invalid; missing={missing}, extra={extra}")


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CorpusEquivalenceError(f"{label} must be a non-empty string")
    return value


def _identity(value: Any, label: str) -> str:
    observed = _string(value, label)
    if IDENTITY.fullmatch(observed) is None:
        raise CorpusEquivalenceError(f"{label} is not an exact identity")
    if observed.upper() in {"UNKNOWN", "NOT_RUN", "NOT_EVALUATED", "INCONCLUSIVE", "TBD", "TODO"}:
        raise CorpusEquivalenceError(f"{label} must not be a non-success sentinel")
    return observed


def _digest(value: Any, label: str) -> str:
    observed = _string(value, label)
    if DIGEST.fullmatch(observed) is None:
        raise CorpusEquivalenceError(f"{label} must be sha256:<64 lowercase hex>")
    return observed


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CorpusEquivalenceError(f"{label} must be a positive integer")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CorpusEquivalenceError(f"{label} must be a non-negative integer")
    return value


def _exact_version(value: Any, label: str) -> str:
    observed = _string(value, label)
    lowered = observed.lower()
    if (
        any(char.isspace() for char in observed)
        or any(char in observed for char in "*<>=^~|,[](){}")
        or MUTABLE_VERSION.search(lowered) is not None
        or lowered in {"unknown", "not_run", "not_evaluated", "tbd", "todo"}
    ):
        raise CorpusEquivalenceError(f"{label} must be one exact immutable version")
    return observed


def _validate_side(value: Any, label: str) -> dict[str, Any]:
    side = _object(value, label)
    _exact_fields(side, {"framework", "runtime", "build_tool", "providers"}, label)
    for component_name in ("framework", "runtime", "build_tool"):
        component = _object(side[component_name], f"{label}.{component_name}")
        _exact_fields(component, {"name", "version"}, f"{label}.{component_name}")
        _identity(component["name"], f"{label}.{component_name}.name")
        _exact_version(component["version"], f"{label}.{component_name}.version")
    providers = side["providers"]
    if not isinstance(providers, list) or not providers:
        raise CorpusEquivalenceError(f"{label}.providers must contain at least one exact provider")
    names: set[str] = set()
    for index, item in enumerate(providers):
        provider = _object(item, f"{label}.providers[{index}]")
        _exact_fields(provider, {"name", "version"}, f"{label}.providers[{index}]")
        name = _identity(provider["name"], f"{label}.providers[{index}].name")
        _exact_version(provider["version"], f"{label}.providers[{index}].version")
        if name in names:
            raise CorpusEquivalenceError(f"{label}.providers contains duplicate provider {name}")
        names.add(name)
    return side


def _validate_tuple(value: Any) -> dict[str, Any]:
    exact_tuple = _object(value, "tuple")
    _exact_fields(
        exact_tuple,
        {"route_id", "pack", "recipe", "source", "target"},
        "tuple",
    )
    _identity(exact_tuple["route_id"], "tuple.route_id")
    for item_name in ("pack", "recipe"):
        item = _object(exact_tuple[item_name], f"tuple.{item_name}")
        _exact_fields(item, {"id", "version", "sha256"}, f"tuple.{item_name}")
        _identity(item["id"], f"tuple.{item_name}.id")
        _exact_version(item["version"], f"tuple.{item_name}.version")
        _digest(item["sha256"], f"tuple.{item_name}.sha256")
    source = _validate_side(exact_tuple["source"], "tuple.source")
    target = _validate_side(exact_tuple["target"], "tuple.target")
    if source == target:
        raise CorpusEquivalenceError("tuple source and target must be directional and distinct")
    return exact_tuple


def _relative_parts(value: Any, label: str) -> tuple[str, ...]:
    observed = _string(value, label)
    candidate = Path(observed)
    if candidate.is_absolute() or not candidate.parts:
        raise CorpusEquivalenceError(f"{label} must be a relative path")
    if any(part in {"", ".", ".."} or RELATIVE_PART.fullmatch(part) is None for part in candidate.parts):
        raise CorpusEquivalenceError(f"{label} contains an unsafe path component")
    return candidate.parts


def _validate_content_reference(value: Any, label: str) -> dict[str, Any]:
    reference = _object(value, label)
    _exact_fields(reference, {"path", "sha256", "size_bytes", "media_type"}, label)
    _relative_parts(reference["path"], f"{label}.path")
    _digest(reference["sha256"], f"{label}.sha256")
    _positive_int(reference["size_bytes"], f"{label}.size_bytes")
    _string(reference["media_type"], f"{label}.media_type")
    return reference


def validate_manifest(value: Any) -> dict[str, Any]:
    manifest = _object(value, "manifest")
    _exact_fields(
        manifest,
        {
            "schema_version",
            "evaluation_id",
            "tuple",
            "tuple_sha256",
            "corpus_roots",
            "external_intake",
            "projects",
        },
        "manifest",
        optional={"$schema"},
    )
    if manifest["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise CorpusEquivalenceError(f"manifest.schema_version must be {MANIFEST_SCHEMA_VERSION}")
    _identity(manifest["evaluation_id"], "manifest.evaluation_id")
    exact_tuple = _validate_tuple(manifest["tuple"])
    declared_tuple_digest = _digest(manifest["tuple_sha256"], "manifest.tuple_sha256")
    observed_tuple_digest = canonical_digest(exact_tuple)
    if declared_tuple_digest != observed_tuple_digest:
        raise CorpusEquivalenceError(
            f"manifest.tuple_sha256 mismatch: expected {observed_tuple_digest}"
        )

    roots = _object(manifest["corpus_roots"], "manifest.corpus_roots")
    _exact_fields(roots, set(CORPUS_ROLES), "manifest.corpus_roots")
    for role in CORPUS_ROLES:
        _relative_parts(roots[role], f"manifest.corpus_roots.{role}")

    external_intake = _object(manifest["external_intake"], "manifest.external_intake")
    _exact_fields(external_intake, {"status", "content"}, "manifest.external_intake")
    if external_intake["status"] not in EXTERNAL_INTAKE_STATUSES:
        raise CorpusEquivalenceError("manifest.external_intake.status is invalid")
    if external_intake["status"] == "SUBMITTED":
        reference = _validate_content_reference(
            external_intake["content"], "manifest.external_intake.content"
        )
        if reference["media_type"] != "application/json":
            raise CorpusEquivalenceError(
                "manifest.external_intake.content.media_type must be application/json"
            )
    elif external_intake["content"] is not None:
        raise CorpusEquivalenceError(
            "manifest.external_intake.content must be null while status is NOT_RUN"
        )

    projects = manifest["projects"]
    if not isinstance(projects, list):
        raise CorpusEquivalenceError("manifest.projects must be an array")
    project_ids: set[str] = set()
    project_paths: set[str] = set()
    for index, item in enumerate(projects):
        label = f"manifest.projects[{index}]"
        project = _object(item, label)
        _exact_fields(
            project,
            {
                "project_id",
                "corpus_role",
                "corpus_path",
                "tuple_sha256",
                "evaluation_scope",
                "artifacts",
            },
            label,
        )
        project_id = _identity(project["project_id"], f"{label}.project_id")
        if project_id in project_ids:
            raise CorpusEquivalenceError(f"manifest.projects contains duplicate project_id {project_id}")
        project_ids.add(project_id)
        role = project["corpus_role"]
        if role not in CORPUS_ROLES:
            raise CorpusEquivalenceError(f"{label}.corpus_role is invalid")
        project_path = project["corpus_path"]
        _relative_parts(project_path, f"{label}.corpus_path")
        if project_path in project_paths:
            raise CorpusEquivalenceError(f"manifest.projects contains duplicate corpus_path {project_path}")
        project_paths.add(project_path)
        if _digest(project["tuple_sha256"], f"{label}.tuple_sha256") != declared_tuple_digest:
            raise CorpusEquivalenceError(f"{label}.tuple_sha256 does not bind the exact manifest tuple")
        if project["evaluation_scope"] not in PROJECT_SCOPES:
            raise CorpusEquivalenceError(f"{label}.evaluation_scope is invalid")
        artifacts = _object(project["artifacts"], f"{label}.artifacts")
        _exact_fields(
            artifacts,
            {"source_snapshot", "target_snapshot", "outcome_evidence"},
            f"{label}.artifacts",
        )
        for artifact_name in ("source_snapshot", "target_snapshot", "outcome_evidence"):
            reference = _validate_content_reference(
                artifacts[artifact_name], f"{label}.artifacts.{artifact_name}"
            )
            if artifact_name == "outcome_evidence" and reference["media_type"] != "application/json":
                raise CorpusEquivalenceError(
                    f"{label}.artifacts.outcome_evidence.media_type must be application/json"
                )
    return manifest


def _root_path(evidence_root: Path) -> Path:
    expanded = evidence_root.expanduser()
    if expanded.is_symlink():
        raise CorpusEquivalenceError("evidence root must not be a symlink")
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as exc:
        raise CorpusEquivalenceError(f"evidence root does not exist: {evidence_root}") from exc
    if not resolved.is_dir():
        raise CorpusEquivalenceError("evidence root must be a directory")
    return resolved


def _resolve_relative(
    root: Path,
    relative: Any,
    label: str,
    *,
    directory: bool,
) -> Path:
    parts = _relative_parts(relative, label)
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise CorpusEquivalenceError(f"{label} contains a symlink")
    try:
        resolved = current.resolve(strict=True)
    except OSError as exc:
        raise CorpusEquivalenceError(f"{label} does not exist") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CorpusEquivalenceError(f"{label} escapes the evidence root") from exc
    if directory and not resolved.is_dir():
        raise CorpusEquivalenceError(f"{label} must be a directory")
    if not directory and not resolved.is_file():
        raise CorpusEquivalenceError(f"{label} must be a regular file")
    return resolved


def _is_within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _validate_corpus_layout(
    manifest: dict[str, Any], evidence_root: Path
) -> tuple[dict[str, Path], dict[str, Path]]:
    role_roots = {
        role: _resolve_relative(
            evidence_root,
            manifest["corpus_roots"][role],
            f"manifest.corpus_roots.{role}",
            directory=True,
        )
        for role in CORPUS_ROLES
    }
    for index, left_role in enumerate(CORPUS_ROLES):
        for right_role in CORPUS_ROLES[index + 1 :]:
            left = role_roots[left_role]
            right = role_roots[right_role]
            if _is_within(left, right) or _is_within(right, left):
                raise CorpusEquivalenceError(
                    f"corpus roots must be physically separate: {left_role}, {right_role}"
                )

    project_roots: dict[str, Path] = {}
    for project in manifest["projects"]:
        project_id = project["project_id"]
        project_root = _resolve_relative(
            evidence_root,
            project["corpus_path"],
            f"project {project_id} corpus_path",
            directory=True,
        )
        if not _is_within(project_root, role_roots[project["corpus_role"]]):
            raise CorpusEquivalenceError(
                f"project {project_id} is outside its declared {project['corpus_role']} corpus root"
            )
        for other_id, other_root in project_roots.items():
            if _is_within(project_root, other_root) or _is_within(other_root, project_root):
                raise CorpusEquivalenceError(
                    f"project corpus paths must be separate: {other_id}, {project_id}"
                )
        project_roots[project_id] = project_root
    return role_roots, project_roots


def _verify_reference(
    reference: dict[str, Any],
    *,
    evidence_root: Path,
    project_root: Path,
    label: str,
    max_bytes: int,
) -> tuple[dict[str, Any], bytes | None]:
    try:
        path = _resolve_relative(evidence_root, reference["path"], f"{label}.path", directory=False)
        if not _is_within(path, project_root):
            raise CorpusEquivalenceError(f"{label}.path is outside its project corpus path")
        raw = read_regular_file_once(path, max_bytes=max_bytes, label=label)
        observed_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        observed_size = len(raw)
        if observed_digest != reference["sha256"]:
            raise CorpusEquivalenceError(
                f"{label} digest mismatch: expected {reference['sha256']}, observed {observed_digest}"
            )
        if observed_size != reference["size_bytes"]:
            raise CorpusEquivalenceError(
                f"{label} size mismatch: expected {reference['size_bytes']}, observed {observed_size}"
            )
        return {
            "status": "VERIFIED",
            "sha256": observed_digest,
            "size_bytes": observed_size,
        }, raw
    except (OSError, ValueError, CorpusEquivalenceError) as exc:
        return {
            "status": "INVALID",
            "sha256": reference["sha256"],
            "size_bytes": reference["size_bytes"],
            "reason": str(exc),
        }, None


def _validate_project_evidence(value: Any, project: dict[str, Any]) -> dict[str, Any]:
    evidence = _object(value, f"project {project['project_id']} outcome evidence")
    _exact_fields(
        evidence,
        {
            "schema_version",
            "project_id",
            "tuple_sha256",
            "corpus_role",
            "evaluation_scope",
            "outcome",
            "source_snapshot_digest",
            "source_snapshot_size_bytes",
            "target_snapshot_digest",
            "target_snapshot_size_bytes",
            "external_bindings",
            "checks",
            "observation_count",
            "regression_count",
            "unknowns",
        },
        f"project {project['project_id']} outcome evidence",
    )
    if evidence["schema_version"] != PROJECT_EVIDENCE_SCHEMA_VERSION:
        raise CorpusEquivalenceError("project outcome evidence schema_version is invalid")
    expected = {
        "project_id": project["project_id"],
        "tuple_sha256": project["tuple_sha256"],
        "corpus_role": project["corpus_role"],
        "evaluation_scope": project["evaluation_scope"],
        "source_snapshot_digest": project["artifacts"]["source_snapshot"]["sha256"],
        "source_snapshot_size_bytes": project["artifacts"]["source_snapshot"]["size_bytes"],
        "target_snapshot_digest": project["artifacts"]["target_snapshot"]["sha256"],
        "target_snapshot_size_bytes": project["artifacts"]["target_snapshot"]["size_bytes"],
    }
    for field, expected_value in expected.items():
        if evidence[field] != expected_value:
            raise CorpusEquivalenceError(
                f"project outcome evidence {field} mismatch: expected {expected_value!r}"
            )
    external_bindings = evidence["external_bindings"]
    if project["corpus_role"] == "development":
        if external_bindings is not None:
            raise CorpusEquivalenceError(
                "development outcome evidence external_bindings must be null"
            )
    else:
        bindings = _object(external_bindings, "project outcome evidence external_bindings")
        _exact_fields(
            bindings,
            {
                "artifact_digest",
                "execution_profile_digest",
                "runnable_evidence_digests",
                "supporting_evidence_digests",
            },
            "project outcome evidence external_bindings",
        )
        _digest(bindings["artifact_digest"], "project outcome evidence artifact_digest")
        _digest(
            bindings["execution_profile_digest"],
            "project outcome evidence execution_profile_digest",
        )
        runnable = _object(
            bindings["runnable_evidence_digests"],
            "project outcome evidence runnable_evidence_digests",
        )
        _exact_fields(
            runnable,
            {"rootless_runner", "rootless_transformer", "rootless_verifier"},
            "project outcome evidence runnable_evidence_digests",
        )
        for evidence_type, digest in runnable.items():
            _digest(
                digest,
                f"project outcome evidence runnable_evidence_digests.{evidence_type}",
            )
        supporting = _object(
            bindings["supporting_evidence_digests"],
            "project outcome evidence supporting_evidence_digests",
        )
        expected_supporting = (
            {"customer_acceptance"} if project["corpus_role"] == "customer" else set()
        )
        _exact_fields(
            supporting,
            expected_supporting,
            "project outcome evidence supporting_evidence_digests",
        )
        for evidence_type, digest in supporting.items():
            _digest(
                digest,
                f"project outcome evidence supporting_evidence_digests.{evidence_type}",
            )
    _positive_int(
        evidence["source_snapshot_size_bytes"],
        "project outcome evidence source_snapshot_size_bytes",
    )
    _positive_int(
        evidence["target_snapshot_size_bytes"],
        "project outcome evidence target_snapshot_size_bytes",
    )
    outcome = evidence["outcome"]
    if outcome not in PROJECT_OUTCOMES:
        raise CorpusEquivalenceError("project outcome evidence outcome is invalid")
    checks = _object(evidence["checks"], "project outcome evidence checks")
    _exact_fields(checks, set(CHECK_NAMES), "project outcome evidence checks")
    if any(status not in CHECK_STATUSES for status in checks.values()):
        raise CorpusEquivalenceError("project outcome evidence contains an invalid check status")
    observation_count = _non_negative_int(
        evidence["observation_count"], "project outcome evidence observation_count"
    )
    regression_count = _non_negative_int(
        evidence["regression_count"], "project outcome evidence regression_count"
    )
    unknowns = evidence["unknowns"]
    if not isinstance(unknowns, list) or any(not isinstance(item, str) or not item for item in unknowns):
        raise CorpusEquivalenceError("project outcome evidence unknowns must be non-empty strings")

    statuses = set(checks.values())
    if outcome == "EQUIVALENT":
        if statuses != {"PASS"} or observation_count <= 0 or regression_count != 0 or unknowns:
            raise CorpusEquivalenceError(
                "EQUIVALENT requires all checks PASS, observations, zero regressions, and no unknowns"
            )
    elif outcome == "NOT_EQUIVALENT":
        if "FAIL" not in statuses or regression_count <= 0:
            raise CorpusEquivalenceError(
                "NOT_EQUIVALENT requires a failed check and at least one regression"
            )
    elif outcome == "INCONCLUSIVE":
        if not unknowns and statuses.isdisjoint({"INCONCLUSIVE", "NOT_RUN"}):
            raise CorpusEquivalenceError(
                "INCONCLUSIVE requires an explicit unknown or inconclusive/not-run check"
            )
    elif outcome == "NOT_RUN" and "NOT_RUN" not in statuses:
        raise CorpusEquivalenceError("NOT_RUN requires at least one NOT_RUN check")
    return evidence


def _evaluate_project(
    project: dict[str, Any],
    *,
    evidence_root: Path,
    project_root: Path,
) -> dict[str, Any]:
    content_reasons: list[str] = []
    artifact_results: dict[str, dict[str, Any]] = {}
    outcome_raw: bytes | None = None
    for artifact_name in ("source_snapshot", "target_snapshot", "outcome_evidence"):
        result, raw = _verify_reference(
            project["artifacts"][artifact_name],
            evidence_root=evidence_root,
            project_root=project_root,
            label=f"project {project['project_id']} {artifact_name}",
            max_bytes=MAX_JSON_BYTES if artifact_name == "outcome_evidence" else MAX_ARTIFACT_BYTES,
        )
        artifact_results[artifact_name] = result
        if result["status"] != "VERIFIED":
            content_reasons.append(f"{artifact_name.upper()}_CONTENT_INVALID")
        if artifact_name == "outcome_evidence":
            outcome_raw = raw

    outcome = "NOT_EVALUATED"
    evidence_payload: dict[str, Any] | None = None
    if outcome_raw is not None:
        try:
            decoded = json.loads(outcome_raw.decode("utf-8"))
            evidence_payload = _validate_project_evidence(decoded, project)
            outcome = evidence_payload["outcome"]
        except (UnicodeDecodeError, json.JSONDecodeError, CorpusEquivalenceError) as exc:
            content_reasons.append(f"OUTCOME_EVIDENCE_INVALID: {exc}")
    if outcome not in {"EQUIVALENT", "NOT_EQUIVALENT"}:
        content_reasons.append(f"OUTCOME_{outcome}")

    aggregate_reasons = list(content_reasons)
    if project["evaluation_scope"] != "WHOLE_REPOSITORY":
        aggregate_reasons.append("EXACT_FIXTURE_EXCLUDED_FROM_OVERALL_RATE")
    if project["corpus_role"] not in AGGREGATE_ROLES:
        aggregate_reasons.append("DEVELOPMENT_CORPUS_EXCLUDED_FROM_OVERALL_RATE")
    else:
        aggregate_reasons.append("SIGNED_EXTERNAL_INTAKE_NOT_VERIFIED")

    return {
        "project_id": project["project_id"],
        "corpus_role": project["corpus_role"],
        "evaluation_scope": project["evaluation_scope"],
        "outcome": outcome,
        "signed_evidence_type": PROJECT_EVIDENCE_TYPES.get(project["corpus_role"]),
        "evidence_eligible": not content_reasons and project["corpus_role"] == "development",
        "aggregate_eligible": not aggregate_reasons,
        "executor_verifier_separation": {
            "signature_verified": False,
            "separate_subjects": False,
            "separate_organizations": False,
        },
        "signed_evidence_status": (
            "NOT_APPLICABLE" if project["corpus_role"] == "development" else "NOT_VERIFIED"
        ),
        "artifact_verification": artifact_results,
        "evidence_exclusion_reasons": sorted(set(content_reasons)),
        "aggregate_exclusion_reasons": sorted(set(aggregate_reasons)),
        "_evidence_payload": evidence_payload,
    }


def _external_side_matches(side: dict[str, Any], external: dict[str, Any]) -> bool:
    providers = {item["name"]: item["version"] for item in side["providers"]}
    build_tool = f"{side['build_tool']['name']}-{side['build_tool']['version']}"
    return (
        side["framework"]["name"] == external.get("framework")
        and side["framework"]["version"] == external.get("framework_version")
        and side["runtime"]["name"] == external.get("runtime")
        and side["runtime"]["version"] == external.get("runtime_version")
        and build_tool == external.get("build_tool")
        and providers == external.get("provider_versions")
    )


def _validate_external_tuple_binding(
    exact_tuple: dict[str, Any],
    intake: dict[str, Any],
    pack_dir: Path,
) -> None:
    binding = _object(intake.get("binding"), "external intake binding")
    if exact_tuple["route_id"] != binding.get("pack_key"):
        raise CorpusEquivalenceError("exact tuple route_id does not match external pack_key")
    if (
        exact_tuple["pack"]["id"] != binding.get("pack_key")
        or exact_tuple["pack"]["version"] != binding.get("pack_version")
        or exact_tuple["pack"]["sha256"] != binding.get("pack_manifest_digest")
    ):
        raise CorpusEquivalenceError("exact tuple pack identity is not bound to actual pack.json bytes")
    if (
        exact_tuple["recipe"]["version"] != binding.get("pack_version")
        or exact_tuple["recipe"]["sha256"] != binding.get("recipe_manifest_digest")
    ):
        raise CorpusEquivalenceError(
            "exact tuple recipe identity is not bound to actual recipe manifest bytes"
        )
    try:
        recipe_raw = read_regular_file_once(
            pack_dir / "recipes" / "manifest.json",
            max_bytes=MAX_JSON_BYTES,
            label="recipe manifest",
        )
        observed_recipe_digest = "sha256:" + hashlib.sha256(recipe_raw).hexdigest()
        if observed_recipe_digest != exact_tuple["recipe"]["sha256"]:
            raise CorpusEquivalenceError(
                "actual recipe manifest bytes changed after external binding verification"
            )
        recipe_manifest = _object(json.loads(recipe_raw.decode("utf-8")), "recipe manifest")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CorpusEquivalenceError(f"actual recipe manifest is invalid: {exc}") from exc
    recipes = recipe_manifest.get("recipes")
    if not isinstance(recipes, list) or exact_tuple["recipe"]["id"] not in recipes:
        raise CorpusEquivalenceError("exact tuple recipe id is absent from actual recipe manifest bytes")
    if not _external_side_matches(exact_tuple["source"], binding.get("source_tuple", {})):
        raise CorpusEquivalenceError("exact source tuple does not match signed external binding")
    if not _external_side_matches(exact_tuple["target"], binding.get("target_tuple", {})):
        raise CorpusEquivalenceError("exact target tuple does not match signed external binding")


def _not_evaluated_external(status: str, reason: str) -> dict[str, Any]:
    return {
        "status": status,
        "intake_content_digest": None,
        "binding_digest": None,
        "trust_store_digest": None,
        "verified_roles": [],
        "reason": reason,
        "_intake": None,
        "_result": None,
    }


def _verify_external_bundle(
    manifest: dict[str, Any],
    evidence_root: Path,
    *,
    pack_dir: Path | None,
    trust_store: Path | None,
    now: datetime | None,
) -> dict[str, Any]:
    declared = manifest["external_intake"]
    if declared["status"] == "NOT_RUN":
        return _not_evaluated_external(
            "NOT_RUN",
            "No content-bound signed Batch 30 external intake was supplied.",
        )
    if pack_dir is None or trust_store is None:
        return _not_evaluated_external(
            "NOT_EVALUATED",
            "A submitted intake requires explicit --pack-dir and --trust-store inputs.",
        )
    reference = declared["content"]
    verification, raw = _verify_reference(
        reference,
        evidence_root=evidence_root,
        project_root=evidence_root,
        label="external intake",
        max_bytes=MAX_JSON_BYTES,
    )
    if verification["status"] != "VERIFIED" or raw is None:
        return _not_evaluated_external(
            "INVALID",
            verification.get("reason", "External intake content reference is invalid."),
        )
    try:
        intake_path = _resolve_relative(
            evidence_root,
            reference["path"],
            "manifest.external_intake.content.path",
            directory=False,
        )
        intake = _object(json.loads(raw.decode("utf-8")), "external intake")
        result = evaluate_external_intake_file(
            intake_path,
            pack_dir=pack_dir,
            trust_store=trust_store,
            evidence_roots=[evidence_root],
            now=now,
        )
        if (
            result.get("evidence_status") != "VERIFIED_EXTERNAL_INTAKE"
            or result.get("intake_content_digest") != reference["sha256"]
            or result.get("intake_size_bytes") != reference["size_bytes"]
            or result.get("certification_decision") != "NOT_CERTIFIED"
        ):
            raise CorpusEquivalenceError("external intake verifier returned an ineligible result")
        expected_roles = {CUSTOMER_AUTHORIZATION_ROLE, *EVIDENCE_ROLES.values()}
        if set(result.get("verified_roles", [])) != expected_roles:
            raise CorpusEquivalenceError("external intake did not verify every required signed role")
        expected_content = {"artifact", "execution_profile", *EVIDENCE_ROLES}
        if set(result.get("verified_content_digests", {})) != expected_content:
            raise CorpusEquivalenceError("external intake did not verify every runnable evidence role")
        _validate_external_tuple_binding(manifest["tuple"], intake, pack_dir)
    except (
        ExternalIntakeError,
        CorpusEquivalenceError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        return _not_evaluated_external("INVALID", str(exc))
    return {
        "status": "VERIFIED",
        "intake_content_digest": result["intake_content_digest"],
        "binding_digest": result["binding_digest"],
        "trust_store_digest": result["trust_store_digest"],
        "verified_roles": result["verified_roles"],
        "reason": "All content-bound external authorization, execution, and verification roles passed.",
        "_intake": intake,
        "_result": result,
    }


def _apply_signed_project_binding(
    project: dict[str, Any],
    result: dict[str, Any],
    external: dict[str, Any],
    *,
    aggregate_role_counts: dict[str, int],
) -> None:
    if project["corpus_role"] == "development":
        return
    reasons = list(result["evidence_exclusion_reasons"])
    aggregate_reasons = [
        reason
        for reason in result["aggregate_exclusion_reasons"]
        if reason != "SIGNED_EXTERNAL_INTAKE_NOT_VERIFIED"
    ]
    if aggregate_role_counts[project["corpus_role"]] != 1:
        reasons.append("MULTIPLE_PROJECTS_PER_SIGNED_ROLE_UNSUPPORTED")
    if external["status"] != "VERIFIED":
        reasons.append(f"EXTERNAL_INTAKE_{external['status']}")
    payload = result.pop("_evidence_payload")
    if payload is None:
        reasons.append("SIGNED_PROJECT_OUTCOME_MISSING")
    if not reasons:
        intake = external["_intake"]
        external_result = external["_result"]
        evidence_type = PROJECT_EVIDENCE_TYPES[project["corpus_role"]]
        evidence_item = intake["evidence"][evidence_type]
        attestation = evidence_item["attestation"]["payload"]
        executor = intake["evidence_executors"][evidence_type]
        bindings = payload["external_bindings"]
        expected = {
            "artifact_digest": intake["binding"]["artifact_digest"],
            "execution_profile_digest": intake["binding"]["execution_profile_digest"],
        }
        for field, expected_value in expected.items():
            if bindings[field] != expected_value:
                reasons.append(f"SIGNED_PROJECT_BINDING_MISMATCH_{field.upper()}")
        signed_content_digest = external_result["verified_content_digests"][evidence_type]
        if project["artifacts"]["outcome_evidence"]["sha256"] != signed_content_digest:
            reasons.append("PROJECT_OUTCOME_NOT_SIGNED_FOR_ROLE")
        expected_runnable = {
            evidence_name: external_result["verified_content_digests"][evidence_name]
            for evidence_name in ("rootless_runner", "rootless_transformer", "rootless_verifier")
        }
        if bindings["runnable_evidence_digests"] != expected_runnable:
            reasons.append("RUNNABLE_EVIDENCE_DIGESTS_NOT_BOUND")
        expected_supporting = {}
        if project["corpus_role"] == "customer":
            expected_supporting = {
                "customer_acceptance": external_result["verified_content_digests"][
                    "customer_acceptance"
                ]
            }
        if bindings["supporting_evidence_digests"] != expected_supporting:
            reasons.append("SUPPORTING_EVIDENCE_DIGESTS_NOT_BOUND")
        separate_subjects = executor["actor_id"] != attestation["actor_id"]
        separate_organizations = executor["organization_id"] != attestation["organization_id"]
        if not separate_subjects:
            reasons.append("EXECUTOR_VERIFIER_SUBJECT_NOT_SEPARATE")
        if not separate_organizations:
            reasons.append("EXECUTOR_VERIFIER_ORGANIZATION_NOT_SEPARATE")
        result["executor_verifier_separation"] = {
            "signature_verified": not reasons,
            "separate_subjects": separate_subjects,
            "separate_organizations": separate_organizations,
        }
    if reasons:
        aggregate_reasons.extend(reasons)
        result["signed_evidence_status"] = "INVALID"
    else:
        result["signed_evidence_status"] = "VERIFIED"
    result["evidence_eligible"] = not reasons
    result["aggregate_eligible"] = not aggregate_reasons
    result["evidence_exclusion_reasons"] = sorted(set(reasons))
    result["aggregate_exclusion_reasons"] = sorted(set(aggregate_reasons))


def evaluate_manifest(
    value: Any,
    evidence_root: Path,
    *,
    pack_dir: Path | None = None,
    trust_store: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate a validated manifest without changing certification state."""
    manifest = validate_manifest(value)
    approved_root = _root_path(evidence_root)
    _, project_roots = _validate_corpus_layout(manifest, approved_root)
    external = _verify_external_bundle(
        manifest,
        approved_root,
        pack_dir=pack_dir,
        trust_store=trust_store,
        now=now,
    )
    projects = [
        _evaluate_project(
            project,
            evidence_root=approved_root,
            project_root=project_roots[project["project_id"]],
        )
        for project in manifest["projects"]
    ]
    aggregate_role_counts = {
        role: sum(project["corpus_role"] == role for project in manifest["projects"])
        for role in AGGREGATE_ROLES
    }
    for project_input, project_result in zip(manifest["projects"], projects, strict=True):
        _apply_signed_project_binding(
            project_input,
            project_result,
            external,
            aggregate_role_counts=aggregate_role_counts,
        )
        project_result.pop("_evidence_payload", None)

    aggregate = [project for project in projects if project["aggregate_eligible"]]
    covered_roles = sorted({project["corpus_role"] for project in aggregate})
    missing_roles = [role for role in AGGREGATE_ROLES if role not in covered_roles]
    if aggregate and not missing_roles:
        numerator: int | None = sum(project["outcome"] == "EQUIVALENT" for project in aggregate)
        denominator: int | None = len(aggregate)
        percentage: float | None = round(100.0 * numerator / denominator, 6)
        status = "EVALUATED"
        reason = "All required independent whole-repository corpus roles are covered."
    else:
        numerator = None
        denominator = None
        percentage = None
        status = "NOT_EVALUATED"
        if not aggregate:
            reason = "No eligible independent whole-repository evidence is available."
        else:
            reason = "Required corpus roles are missing: " + ", ".join(missing_roles)

    role_summaries: dict[str, dict[str, int]] = {}
    for role in CORPUS_ROLES:
        role_projects = [project for project in projects if project["corpus_role"] == role]
        role_summaries[role] = {
            "total_projects": len(role_projects),
            "evidence_eligible_projects": sum(project["evidence_eligible"] for project in role_projects),
            "aggregate_eligible_projects": sum(project["aggregate_eligible"] for project in role_projects),
            "reported_equivalent_projects": sum(
                project["outcome"] == "EQUIVALENT" for project in role_projects
            ),
            "reported_not_equivalent_projects": sum(
                project["outcome"] == "NOT_EQUIVALENT" for project in role_projects
            ),
            "aggregate_equivalent_projects": sum(
                project["aggregate_eligible"] and project["outcome"] == "EQUIVALENT"
                for project in role_projects
            ),
            "aggregate_not_equivalent_projects": sum(
                project["aggregate_eligible"] and project["outcome"] == "NOT_EQUIVALENT"
                for project in role_projects
            ),
            "inconclusive_or_not_evaluated_projects": sum(
                project["outcome"] not in {"EQUIVALENT", "NOT_EQUIVALENT"}
                for project in role_projects
            ),
        }

    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "evaluation_id": manifest["evaluation_id"],
        "tuple": manifest["tuple"],
        "tuple_sha256": manifest["tuple_sha256"],
        "external_intake_verification": {
            key: value
            for key, value in external.items()
            if not key.startswith("_")
        },
        "projects": projects,
        "role_summaries": role_summaries,
        "overall_equivalence": {
            "status": status,
            "scope": "SIGNED_EXTERNAL_EXACT_TUPLE_INDEPENDENT_WHOLE_REPOSITORY_CORPUS_ONLY",
            "required_roles": list(AGGREGATE_ROLES),
            "covered_roles": covered_roles,
            "missing_roles": missing_roles,
            "eligible_conclusive_projects_observed": len(aggregate),
            "numerator_equivalent_projects": numerator,
            "denominator_eligible_projects": denominator,
            "percentage": percentage,
            "reason": reason,
        },
        "universal_legacy_spring_equivalence": {
            "status": "NOT_EVALUATED",
            "percentage": None,
            "reason": (
                "A declared corpus cannot establish a percentage for arbitrary legacy Spring "
                "projects; exact fixtures and observed repositories do not support a universal claim."
            ),
        },
        "certification": {
            "decision": "NOT_CERTIFYING",
            "reason": "Only scripts/batch30/run_framework_gate.py may determine Batch 30 readiness.",
        },
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = read_regular_file_once(path, max_bytes=MAX_JSON_BYTES, label="manifest")
        return _object(json.loads(raw.decode("utf-8")), "manifest")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CorpusEquivalenceError(f"manifest is not bounded regular UTF-8 JSON: {exc}") from exc


def _write_result(path: Path, result: dict[str, Any]) -> None:
    if path.exists() and path.is_symlink():
        raise CorpusEquivalenceError("output must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate typed, content-addressed Spring corpus equivalence evidence."
    )
    parser.add_argument("manifest", type=Path, help="equivalence corpus manifest JSON")
    parser.add_argument(
        "--evidence-root",
        type=Path,
        required=True,
        help="explicit root containing the four physically separate corpus directories",
    )
    parser.add_argument(
        "--pack-dir",
        type=Path,
        help="actual framework pack whose pack/recipe bytes are bound by the signed intake",
    )
    parser.add_argument(
        "--trust-store",
        type=Path,
        help="Batch 30 Ed25519 external-evidence trust store",
    )
    parser.add_argument("--output", type=Path, help="write the typed result JSON here")
    args = parser.parse_args(argv)
    try:
        result = evaluate_manifest(
            _load_manifest(args.manifest),
            args.evidence_root,
            pack_dir=args.pack_dir,
            trust_store=args.trust_store,
        )
        if args.output:
            _write_result(args.output, result)
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except CorpusEquivalenceError as exc:
        print(f"spring corpus equivalence evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
