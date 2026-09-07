"""ActionKey construction and explainable cache-miss attribution.

An ActionKey is ``sha256(canonical_json(declared result-affecting inputs))``.
Two properties matter more than the hash itself:

* **Completeness** -- every input that can change the result is declared, so a
  hit is safe. A stage that reads an undeclared environment variable is a
  hermeticity bug, and :func:`StageFingerprintSpec.audit_environment` reports it
  rather than silently folding the value into the key.
* **Explainability** -- the fingerprint document is stored alongside the key, so
  a miss can be attributed to an exact dimension instead of "something changed".
"""

from __future__ import annotations

import os
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .canonical import canonical_json_bytes, digest_of, require_digest, sha256_bytes
from .enums import DIMENSION_MISS_REASON, MissReason
from .errors import ContractViolation

SCHEMA_VERSION = "1.0.0"
CANONICALIZATION = "canonical-json-v1"

#: Dimensions every stage fingerprint must supply.
REQUIRED_DIMENSIONS: tuple[str, ...] = (
    "stage_id",
    "stage_version",
    "stage_contract_schema",
    "input_artifact_digests",
    "target_language",
    "toolchain_digest",
)

#: Dimensions that must never influence a key, whatever a caller passes.
EXCLUDED_DIMENSIONS: frozenset[str] = frozenset(
    {
        "run_id",
        "node_id",
        "attempt",
        "workspace_absolute_path",
        "workspace_root",
        "wall_clock_time",
        "started_at",
        "finished_at",
        "host_name",
        "hostname",
        "worker_id",
        "lease_id",
        "lease_epoch",
        "temporary_filename",
        "temp_dir",
        "pid",
        "user",
        "home",
        "trace_id",
        "correlation_id",
    }
)

#: Dimensions that would leak secrets into a shared key space.
SECRET_DIMENSIONS: frozenset[str] = frozenset(
    {"api_key", "token", "password", "secret", "credential", "authorization", "private_key"}
)

_ALL_DIMENSIONS: tuple[str, ...] = (
    "stage_id",
    "stage_version",
    "stage_contract_schema",
    "input_artifact_digests",
    "source_semantic_digest",
    "dependency_public_interface_digests",
    "target_language",
    "target_framework",
    "target_runtime",
    "target_triple",
    "rule_pack_digest",
    "toolchain_digest",
    "compiler_flags",
    "dependency_lock_digests",
    "declared_environment",
    "prompt_template_digest",
    "model_snapshot_digest",
    "decoding_parameters",
    "tool_output_digests",
    "feature_flags",
)


def _normalize_flag(flag: str) -> str:
    """Canonicalise a compiler flag: ``--opt=x`` and ``--opt x`` are one flag."""
    text = unicodedata.normalize("NFC", flag.strip())
    if text.startswith("--") and "=" in text:
        name, _, value = text.partition("=")
        return f"{name}={value}"
    return text


def canonical_flags(flags: Iterable[str]) -> list[str]:
    """Order-insensitive for repeated independent flags, duplicates collapsed."""
    return sorted({_normalize_flag(flag) for flag in flags if flag is not None})


def canonical_digest_list(digests: Iterable[str]) -> list[str]:
    return sorted({require_digest(item) for item in digests})


def canonical_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): values[key] for key in sorted(values, key=str)}


@dataclass(frozen=True)
class StageFingerprintSpec:
    """Declares which dimensions a stage's key depends on."""

    stage_id: str
    stage_version: str
    stage_contract_schema: str
    include: tuple[str, ...] = _ALL_DIMENSIONS
    optional: tuple[str, ...] = ()
    declared_environment: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        unknown = sorted(set(self.include) - set(_ALL_DIMENSIONS))
        if unknown:
            raise ContractViolation("unknown fingerprint dimensions", dimensions=unknown)
        forbidden = sorted(set(self.include) & EXCLUDED_DIMENSIONS)
        if forbidden:
            raise ContractViolation("excluded dimensions cannot be included", dimensions=forbidden)
        secret_env = sorted(
            name for name in self.declared_environment if _looks_secret(name)
        )
        if secret_env:
            raise ContractViolation("secret-looking environment values cannot enter a key", names=secret_env)
        missing = sorted(set(REQUIRED_DIMENSIONS) - set(self.include))
        if missing:
            raise ContractViolation("fingerprint spec omits required dimensions", dimensions=missing)

    def audit_environment(self, observed: Mapping[str, str]) -> dict[str, list[str]]:
        """Report which observed environment values are declared or excluded.

        Undeclared values do **not** enter the key. They are reported so a
        hermeticity gate can fail the stage instead of caching a result that
        secretly depended on them.
        """
        declared = set(self.declared_environment)
        return {
            "declared": sorted(name for name in observed if name in declared),
            "undeclared": sorted(name for name in observed if name not in declared),
        }


def _looks_secret(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in SECRET_DIMENSIONS)


@dataclass(frozen=True)
class FingerprintInputs:
    """Raw, un-canonicalised inputs. ``build_action_key`` normalises them."""

    input_artifact_digests: tuple[str, ...] = ()
    source_semantic_digest: str | None = None
    dependency_public_interface_digests: tuple[str, ...] = ()
    target_language: str = ""
    target_framework: str | None = None
    target_runtime: str | None = None
    target_triple: str | None = None
    rule_pack_digest: str | None = None
    toolchain_digest: str = ""
    compiler_flags: tuple[str, ...] = ()
    dependency_lock_digests: Mapping[str, str] = field(default_factory=dict)
    declared_environment: Mapping[str, str] = field(default_factory=dict)
    prompt_template_digest: str | None = None
    model_snapshot_digest: str | None = None
    decoding_parameters: Mapping[str, Any] = field(default_factory=dict)
    tool_output_digests: Mapping[str, str] = field(default_factory=dict)
    feature_flags: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Fingerprint:
    action_key: str
    dimensions: dict[str, Any]
    document: dict[str, Any]

    def explain(self) -> dict[str, Any]:
        return {
            "action_key": self.action_key,
            "canonicalization": CANONICALIZATION,
            "dimensions": {
                name: digest_of(value) for name, value in sorted(self.dimensions.items())
            },
        }


def build_action_key(spec: StageFingerprintSpec, inputs: FingerprintInputs) -> Fingerprint:
    """Compute the ActionKey and the explainable fingerprint document."""
    raw: dict[str, Any] = {
        "stage_id": spec.stage_id,
        "stage_version": spec.stage_version,
        "stage_contract_schema": spec.stage_contract_schema,
        "input_artifact_digests": canonical_digest_list(inputs.input_artifact_digests),
        "source_semantic_digest": inputs.source_semantic_digest,
        "dependency_public_interface_digests": canonical_digest_list(
            inputs.dependency_public_interface_digests
        ),
        "target_language": inputs.target_language,
        "target_framework": inputs.target_framework,
        "target_runtime": inputs.target_runtime,
        "target_triple": inputs.target_triple,
        "rule_pack_digest": inputs.rule_pack_digest,
        "toolchain_digest": inputs.toolchain_digest,
        "compiler_flags": canonical_flags(inputs.compiler_flags),
        "dependency_lock_digests": canonical_mapping(inputs.dependency_lock_digests),
        "declared_environment": canonical_mapping(
            {k: v for k, v in inputs.declared_environment.items() if k in set(spec.declared_environment)}
        ),
        "prompt_template_digest": inputs.prompt_template_digest,
        "model_snapshot_digest": inputs.model_snapshot_digest,
        "decoding_parameters": canonical_mapping(inputs.decoding_parameters),
        "tool_output_digests": canonical_mapping(inputs.tool_output_digests),
        "feature_flags": canonical_mapping(inputs.feature_flags),
    }

    included = set(spec.include) - set(spec.exclude)
    dimensions = {name: value for name, value in raw.items() if name in included}

    for name in REQUIRED_DIMENSIONS:
        if name not in dimensions:
            raise ContractViolation("required fingerprint dimension is missing", dimension=name)
        if dimensions[name] in (None, "", []):
            raise ContractViolation("required fingerprint dimension is empty", dimension=name)

    action_key = sha256_bytes(canonical_json_bytes(dimensions))

    document = {
        "schema_version": SCHEMA_VERSION,
        "stage_id": spec.stage_id,
        "stage_version": spec.stage_version,
        "stage_contract_schema": spec.stage_contract_schema,
        "inputs": {
            "input_artifact_digests": dimensions.get("input_artifact_digests", []),
            "source_semantic_digest": dimensions.get("source_semantic_digest"),
            "dependency_public_interface_digests": dimensions.get(
                "dependency_public_interface_digests", []
            ),
            "dependency_lock_digests": dimensions.get("dependency_lock_digests", {}),
            "tool_output_digests": dimensions.get("tool_output_digests", {}),
        },
        "target": {
            "language": dimensions.get("target_language"),
            "framework": dimensions.get("target_framework"),
            "runtime": dimensions.get("target_runtime"),
            "triple": dimensions.get("target_triple"),
        },
        "toolchain": {
            "toolchain_digest": dimensions.get("toolchain_digest"),
            "compiler_flags": dimensions.get("compiler_flags", []),
        },
        "rule_pack_digest": dimensions.get("rule_pack_digest"),
        "model_profile": (
            {
                "model_snapshot": dimensions.get("model_snapshot_digest"),
                "prompt_template_digest": dimensions.get("prompt_template_digest"),
                "decoding_parameters": dimensions.get("decoding_parameters", {}),
            }
            if "model_snapshot_digest" in dimensions or "prompt_template_digest" in dimensions
            else None
        ),
        "declared_environment": dimensions.get("declared_environment", {}),
        "feature_flags": dimensions.get("feature_flags", {}),
        "action_key": action_key,
        "explanation": {
            "canonicalization": CANONICALIZATION,
            "excluded_dimensions": sorted(EXCLUDED_DIMENSIONS),
            "dimension_digests": {name: digest_of(value) for name, value in sorted(dimensions.items())},
        },
    }
    return Fingerprint(action_key=action_key, dimensions=dimensions, document=document)


@dataclass(frozen=True)
class MissExplanation:
    action_key: str
    previous_action_key: str | None
    reasons: tuple[MissReason, ...]
    changed_dimensions: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_key": self.action_key,
            "previous_action_key": self.previous_action_key,
            "reasons": [str(reason) for reason in self.reasons],
            "changed_dimensions": list(self.changed_dimensions),
        }


def explain_miss(
    current: Fingerprint,
    previous: Fingerprint | None,
    extra_reasons: Sequence[MissReason] = (),
    disclose_values: bool = False,
) -> MissExplanation:
    """Attribute a miss to exact dimensions.

    Values are disclosed only when policy allows; digests are always safe
    because they carry no source text.
    """
    if previous is None:
        return MissExplanation(
            action_key=current.action_key,
            previous_action_key=None,
            reasons=tuple([MissReason.NO_ENTRY, *extra_reasons]),
            changed_dimensions=(),
        )

    reasons: list[MissReason] = []
    changed: list[dict[str, Any]] = []
    names = sorted(set(current.dimensions) | set(previous.dimensions))
    for name in names:
        before = previous.dimensions.get(name)
        after = current.dimensions.get(name)
        if before == after:
            continue
        entry: dict[str, Any] = {
            "dimension": name,
            "previous_digest": digest_of(before),
            "current_digest": digest_of(after),
        }
        if disclose_values:
            entry["previous_value"] = before
            entry["current_value"] = after
        changed.append(entry)
        reason = DIMENSION_MISS_REASON.get(name)
        if reason is not None and reason not in reasons:
            reasons.append(reason)

    for reason in extra_reasons:
        if reason not in reasons:
            reasons.append(reason)
    if not reasons and current.action_key != previous.action_key:
        reasons.append(MissReason.STAGE_CONTRACT_CHANGED)

    return MissExplanation(
        action_key=current.action_key,
        previous_action_key=previous.action_key,
        reasons=tuple(reasons),
        changed_dimensions=tuple(changed),
    )


def observed_environment(names: Iterable[str]) -> dict[str, str]:
    """Read declared environment values only; never the whole environment."""
    return {name: os.environ[name] for name in sorted(set(names)) if name in os.environ}
