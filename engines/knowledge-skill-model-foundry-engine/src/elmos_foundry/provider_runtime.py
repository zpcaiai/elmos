"""Compile an exact host Provider manifest into the production command Broker.

The Foundry repository owns route contracts, while a production host owns the
provider executables and credentials.  This loader joins those two authorities
without accepting wildcard routes, catalog drift, relative executables, or
partial coverage when a complete runtime is requested.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
from types import MappingProxyType
from typing import Any, Protocol

from .adapters import ExternalExecutionBroker
from .canonical import (
    CanonicalLimits,
    canonical_digest,
    require_identifier,
    strict_json_loads,
    validate_digest,
)
from .external_assurance import ProviderCommandRoute, SignatureVerifier, build_subprocess_broker
from .external_bindings import exact_external_binding
from .local_semantics import LOCAL_SEMANTIC_SKILLS
from .native_semantics import load_native_programs
from .pipelines import PIPELINE_PROFILE_REGISTRY, exact_pipeline_binding


MANIFEST_SCHEMA_VERSION = "elmos.foundry.provider-runtime-manifest.v1"
_MANIFEST_LIMITS = CanonicalLimits(
    max_document_bytes=32 * 1024 * 1024,
    max_string_bytes=1024 * 1024,
    max_key_bytes=512,
    max_depth=64,
    max_items=250_000,
)
_ROOT_FIELDS = {
    "schema_version",
    "broker_id",
    "broker_version",
    "catalog_digest",
    "skill_routes",
    "pipeline_routes",
}
_ROUTE_FIELDS = {
    "skill_name",
    "adapter_id",
    "adapter_version",
    "adapter_digest",
    "route_id",
    "route_version",
    "route_digest",
    "operation",
    "semantic_program_digest",
    "provider_id",
    "provider_version",
    "executable",
    "executable_digest",
    "arguments",
    "inherited_environment",
    "timeout_seconds",
    "max_output_bytes",
}
_PIPELINE_ROUTE_FIELDS = _ROUTE_FIELDS - {"skill_name", "semantic_program_digest"} | {
    "pipeline_name"
}


class ProviderRuntimeCatalog(Protocol):
    @property
    def content_sha256(self) -> str: ...

    @property
    def atomic_skills(self) -> Mapping[str, Mapping[str, Any]]: ...

    @property
    def pipelines(self) -> Mapping[str, Mapping[str, Any]]: ...


class ProviderRuntimeManifestError(ValueError):
    """A host Provider manifest is incomplete, ambiguous, or drifted."""


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderRuntimeManifest:
    broker_id: str
    broker_version: str
    catalog_digest: str
    routes: tuple[ProviderCommandRoute, ...]
    configured_skills: tuple[str, ...]
    configured_pipelines: tuple[str, ...]
    complete_catalog: bool
    document_digest: str

    def __post_init__(self) -> None:
        require_identifier(self.broker_id, "broker_id")
        require_identifier(self.broker_version, "broker_version")
        validate_digest(self.catalog_digest, "catalog_digest")
        validate_digest(self.document_digest, "document_digest")
        if not self.routes or len(self.routes) != (
            len(self.configured_skills) + len(self.configured_pipelines)
        ):
            raise ValueError("provider runtime route inventory must be non-empty and exact")
        if self.configured_skills != tuple(sorted(set(self.configured_skills))):
            raise ValueError("configured_skills must be unique and sorted")
        if self.configured_pipelines != tuple(sorted(set(self.configured_pipelines))):
            raise ValueError("configured_pipelines must be unique and sorted")

    def build_broker(self, *, receipt_verifier: SignatureVerifier) -> ExternalExecutionBroker:
        return build_subprocess_broker(
            broker_id=self.broker_id,
            version=self.broker_version,
            routes=self.routes,
            receipt_verifier=receipt_verifier,
        )

    def validate_installed_executables(self) -> Mapping[str, Any]:
        """Verify every installed executable without starting a Provider process."""

        verified: dict[tuple[Path, str], str] = {}
        for route in self.routes:
            key = (route.executable, route.executable_digest)
            if key in verified:
                continue
            path = route.executable
            try:
                status = path.lstat()
            except OSError as exc:
                raise ProviderRuntimeManifestError(
                    f"provider executable is unavailable: {path}"
                ) from exc
            if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
                raise ProviderRuntimeManifestError(
                    f"provider executable must be a regular non-symlink file: {path}"
                )
            if status.st_mode & stat.S_IWOTH:
                raise ProviderRuntimeManifestError(
                    f"provider executable must not be world-writable: {path}"
                )
            if not os.access(path, os.X_OK):
                raise ProviderRuntimeManifestError(
                    f"provider executable is not executable: {path}"
                )
            observed = _file_digest(path)
            if observed != route.executable_digest:
                raise ProviderRuntimeManifestError(
                    f"provider executable digest drifted: {path}"
                )
            verified[key] = observed
        return MappingProxyType(
            {
                "status": "HOST_PROVIDER_RUNTIME_VALIDATED",
                "manifest_digest": self.document_digest,
                "configured_routes": len(self.routes),
                "configured_skills": len(self.configured_skills),
                "configured_pipelines": len(self.configured_pipelines),
                "unique_executables": len(verified),
                "complete_catalog": self.complete_catalog,
                "execution_status": "NOT_RUN",
                "external_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            }
        )


def _exact_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProviderRuntimeManifestError(f"{label} must be an object")
    observed = set(value)
    if observed != fields:
        missing = sorted(fields - observed)
        extra = sorted(observed - fields)
        raise ProviderRuntimeManifestError(
            f"{label} fields are not exact; missing={missing}, extra={extra}"
        )
    return value


def _catalog_digest(catalog: ProviderRuntimeCatalog) -> str:
    digest = str(catalog.content_sha256)
    if not digest.startswith("sha256:"):
        digest = "sha256:" + digest
    return validate_digest(digest, "catalog.content_sha256")


def _strings(value: Any, label: str, *, canonical_set: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ProviderRuntimeManifestError(f"{label} must be an array of strings")
    result = tuple(value)
    if canonical_set and result != tuple(sorted(set(result))):
        raise ProviderRuntimeManifestError(f"{label} must be unique and sorted")
    return result


def _command_route(
    row: Mapping[str, Any],
    route_id: str,
    route_digest: str,
    operation: str,
    label: str,
) -> ProviderCommandRoute:
    arguments = _strings(row["arguments"], f"route[{label}].arguments", canonical_set=False)
    environment = _strings(
        row["inherited_environment"],
        f"route[{label}].inherited_environment",
        canonical_set=True,
    )
    executable = row["executable"]
    if not isinstance(executable, str) or not executable:
        raise ProviderRuntimeManifestError("provider executable must be a non-empty path")
    provider_id = row["provider_id"]
    provider_version = row["provider_version"]
    if not isinstance(provider_id, str) or not provider_id:
        raise ProviderRuntimeManifestError("provider_id must be a non-empty identifier")
    if not isinstance(provider_version, str) or not provider_version:
        raise ProviderRuntimeManifestError("provider_version must be a non-empty identifier")
    return ProviderCommandRoute(
        route_id=route_id,
        route_digest=route_digest,
        operation=operation,
        provider_id=provider_id,
        provider_version=provider_version,
        executable=Path(executable),
        executable_digest=str(row["executable_digest"]),
        arguments=arguments,
        inherited_environment=environment,
        timeout_seconds=row["timeout_seconds"],
        max_output_bytes=row["max_output_bytes"],
    )


def load_provider_runtime_manifest(
    source: Path | bytes,
    *,
    catalog: ProviderRuntimeCatalog,
    require_complete: bool = True,
) -> ProviderRuntimeManifest:
    """Load and bind a host manifest to the exact compiled Foundry catalog."""

    if isinstance(source, Path):
        try:
            source_status = source.lstat()
        except OSError as exc:
            raise ProviderRuntimeManifestError("provider runtime manifest is unavailable") from exc
        if stat.S_ISLNK(source_status.st_mode) or not stat.S_ISREG(source_status.st_mode):
            raise ProviderRuntimeManifestError(
                "provider runtime manifest must be a regular non-symlink file"
            )
        if source_status.st_size > _MANIFEST_LIMITS.max_document_bytes:
            raise ProviderRuntimeManifestError("provider runtime manifest exceeds its byte limit")
        raw = source.read_bytes()
    else:
        raw = source
    if not isinstance(raw, bytes):
        raise TypeError("provider runtime manifest source must be a Path or bytes")
    parsed = strict_json_loads(raw, limits=_MANIFEST_LIMITS)
    root = _exact_mapping(parsed, _ROOT_FIELDS, "provider runtime manifest")
    if root["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ProviderRuntimeManifestError("provider runtime manifest schema is unsupported")
    expected_catalog_digest = _catalog_digest(catalog)
    if root["catalog_digest"] != expected_catalog_digest:
        raise ProviderRuntimeManifestError("provider runtime manifest targets a different catalog")
    broker_id = root["broker_id"]
    broker_version = root["broker_version"]
    try:
        require_identifier(broker_id, "broker_id")
        require_identifier(broker_version, "broker_version")
    except (TypeError, ValueError) as exc:
        raise ProviderRuntimeManifestError("broker identity is invalid") from exc
    raw_routes = root["skill_routes"]
    raw_pipeline_routes = root["pipeline_routes"]
    if not isinstance(raw_routes, list) or not isinstance(raw_pipeline_routes, list):
        raise ProviderRuntimeManifestError(
            "provider runtime Skill and pipeline routes must be arrays"
        )
    if not raw_routes and not raw_pipeline_routes:
        raise ProviderRuntimeManifestError("provider runtime route inventory must be non-empty")

    programs = load_native_programs()
    expected_skills = set(catalog.atomic_skills) - set(LOCAL_SEMANTIC_SKILLS)
    if set(programs) != expected_skills:
        raise ProviderRuntimeManifestError("native program inventory differs from the catalog")
    configured: dict[str, ProviderCommandRoute] = {}
    route_ids: set[str] = set()
    for index, value in enumerate(raw_routes):
        row = _exact_mapping(value, _ROUTE_FIELDS, f"provider runtime route[{index}]")
        skill_name = row["skill_name"]
        if not isinstance(skill_name, str) or skill_name not in expected_skills:
            raise ProviderRuntimeManifestError(f"unknown or local Skill route: {skill_name!r}")
        if skill_name in configured:
            raise ProviderRuntimeManifestError(f"duplicate Provider route for {skill_name}")
        binding, route = exact_external_binding(skill_name, catalog.atomic_skills[skill_name])
        expected = {
            "adapter_id": binding.adapter_id,
            "adapter_version": binding.version,
            "adapter_digest": binding.digest,
            "route_id": route.route_id,
            "route_version": route.version,
            "route_digest": route.digest,
            "operation": route.operation,
            "semantic_program_digest": "sha256:" + programs[skill_name].digest,
        }
        if any(row[field] != expected_value for field, expected_value in expected.items()):
            raise ProviderRuntimeManifestError(
                f"Provider route for {skill_name} drifted from its compiled binding"
            )
        if route.route_id in route_ids:
            raise ProviderRuntimeManifestError(f"duplicate route identity: {route.route_id}")
        route_ids.add(route.route_id)
        configured[skill_name] = _command_route(
            row, route.route_id, route.digest, route.operation, skill_name
        )

    configured_skills = tuple(sorted(configured))
    expected_pipelines = set(PIPELINE_PROFILE_REGISTRY)
    if set(catalog.pipelines) != expected_pipelines:
        raise ProviderRuntimeManifestError("pipeline inventory differs from the catalog")
    configured_pipelines: dict[str, ProviderCommandRoute] = {}
    for index, value in enumerate(raw_pipeline_routes):
        row = _exact_mapping(
            value, _PIPELINE_ROUTE_FIELDS, f"provider pipeline route[{index}]"
        )
        pipeline_name = row["pipeline_name"]
        if not isinstance(pipeline_name, str) or pipeline_name not in expected_pipelines:
            raise ProviderRuntimeManifestError(f"unknown pipeline route: {pipeline_name!r}")
        if pipeline_name in configured_pipelines:
            raise ProviderRuntimeManifestError(f"duplicate Provider route for {pipeline_name}")
        binding, route = exact_pipeline_binding(
            pipeline_name, catalog.pipelines[pipeline_name]
        )
        expected = {
            "adapter_id": binding.adapter_id,
            "adapter_version": binding.version,
            "adapter_digest": binding.digest,
            "route_id": route.route_id,
            "route_version": route.version,
            "route_digest": route.digest,
            "operation": route.operation,
        }
        if any(row[field] != expected_value for field, expected_value in expected.items()):
            raise ProviderRuntimeManifestError(
                f"Provider pipeline route for {pipeline_name} drifted from its compiled binding"
            )
        if route.route_id in route_ids:
            raise ProviderRuntimeManifestError(f"duplicate route identity: {route.route_id}")
        route_ids.add(route.route_id)
        configured_pipelines[pipeline_name] = _command_route(
            row, route.route_id, route.digest, route.operation, pipeline_name
        )

    configured_pipeline_names = tuple(sorted(configured_pipelines))
    complete = (
        set(configured_skills) == expected_skills
        and set(configured_pipeline_names) == expected_pipelines
    )
    if require_complete and not complete:
        missing = sorted(expected_skills - set(configured_skills))
        missing_pipelines = sorted(expected_pipelines - set(configured_pipeline_names))
        raise ProviderRuntimeManifestError(
            "complete Provider runtime requires 1,244 Skill and 14 pipeline routes; "
            f"missing Skills={len(missing)}, pipelines={len(missing_pipelines)}"
        )
    return ProviderRuntimeManifest(
        broker_id=broker_id,
        broker_version=broker_version,
        catalog_digest=expected_catalog_digest,
        routes=(
            tuple(configured[name] for name in configured_skills)
            + tuple(configured_pipelines[name] for name in configured_pipeline_names)
        ),
        configured_skills=configured_skills,
        configured_pipelines=configured_pipeline_names,
        complete_catalog=complete,
        document_digest=canonical_digest(root, limits=_MANIFEST_LIMITS),
    )


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "ProviderRuntimeManifest",
    "ProviderRuntimeManifestError",
    "load_provider_runtime_manifest",
]
