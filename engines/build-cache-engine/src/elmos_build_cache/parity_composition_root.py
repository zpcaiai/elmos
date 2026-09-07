"""Durable production composition root for the five cache-parity layers.

The pure composition and its HTTP wiring intentionally accept server-owned
ports.  This module supplies the concrete local production root: prompt,
context, environment and affinity material are registered in the tenant's CAS
and bound to the exact serving identity in durable metadata.  Reopening the
metadata store and CAS therefore preserves the same verified probes.

Action is deliberately absent.  It is the only layer allowed to skip fallback
execution and remains wired per request from the real :class:`ActionCache` by
``CompositionRunner``.  A deployment cannot register an Action result here or
replace that authority with a generic artifact.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .canonical import canonical_json_bytes, digest_of, require_digest, sha256_bytes
from .cas import ContentAddressableStore
from .db import MetadataStore
from .enums import ArtifactStorageState, ValidationLevel
from .errors import (
    ContractViolation,
    ElmosCacheError,
    IdempotencyConflict,
    NotFound,
    TenantMismatch,
)
from .parity_composition import CompositionLayer, CompositionRequest, SignedServingBoundary
from .parity_composition_wiring import LayerProbe, LayerProbeFn, ServingCompositionWiring

PARITY_LAYER_MANIFEST_SCHEMA_VERSION = "1.0.0"
PARITY_LAYER_MANIFEST_KIND = "elmos.cache-parity-layer-material/v1"
PARITY_LAYER_BINDING_SOURCE_KIND = "cache-parity-layer-binding"
PARITY_LAYER_MANIFEST_SOURCE_KIND = "cache-parity-layer-manifest"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")
_PRODUCTION_LAYERS = (
    CompositionLayer.PROMPT,
    CompositionLayer.CONTEXT,
    CompositionLayer.ENVIRONMENT,
    CompositionLayer.AFFINITY,
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "layer",
        "tenant_id",
        "project_id",
        "principal_digest",
        "authorization_digest",
        "compatibility_digest",
        "work_digest",
        "binding_digest",
        "material_digest",
        "size_bytes",
        "validation_level",
    }
)


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field_name} must be a bounded identifier")
    return value


def _production_layer(layer: CompositionLayer) -> CompositionLayer:
    if not isinstance(layer, CompositionLayer) or layer not in _PRODUCTION_LAYERS:
        raise ContractViolation(
            "durable parity material may only represent a non-Action serving layer"
        )
    return layer


def _binding_document(
    *,
    layer: CompositionLayer,
    tenant_id: str,
    project_id: str,
    principal_digest: str,
    authorization_digest: str,
    compatibility_digest: str,
    work_digest: str,
) -> dict[str, str]:
    return {
        "layer": _production_layer(layer).value,
        "tenant_id": _identifier(tenant_id, "tenant_id"),
        "project_id": _identifier(project_id, "project_id"),
        "principal_digest": require_digest(principal_digest),
        "authorization_digest": require_digest(authorization_digest),
        "compatibility_digest": require_digest(compatibility_digest),
        "work_digest": require_digest(work_digest),
    }


def _binding_source_id(layer: CompositionLayer, binding_digest: str) -> str:
    return f"{layer.value.lower()}:{require_digest(binding_digest).removeprefix('sha256:')}"


@dataclass(frozen=True, slots=True)
class RegisteredLayerMaterial:
    """One durable exact-scope binding to verified immutable material."""

    layer: CompositionLayer
    binding_digest: str
    manifest_digest: str
    material_digest: str
    size_bytes: int
    validation_level: ValidationLevel

    def __post_init__(self) -> None:
        _production_layer(self.layer)
        require_digest(self.binding_digest)
        require_digest(self.manifest_digest)
        require_digest(self.material_digest)
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 1:
            raise ContractViolation("registered parity material must be non-empty")
        if not isinstance(self.validation_level, ValidationLevel):
            raise ContractViolation("registered parity material validation level is invalid")


class PersistentLayerMaterialRegistry:
    """CAS-backed exact binding registry used by the production composition.

    Registration is a trusted host operation, not an HTTP request field.  One
    binding is immutable and idempotent: an exact replay converges while a
    different byte sequence for the same binding fails closed.
    """

    def __init__(
        self,
        store: MetadataStore,
        cas: ContentAddressableStore,
        *,
        minimum_validation: ValidationLevel = ValidationLevel.TEST_VERIFIED,
    ) -> None:
        if not isinstance(store, MetadataStore):
            raise ContractViolation("parity layer registry requires MetadataStore")
        if not isinstance(cas, ContentAddressableStore):
            raise ContractViolation("parity layer registry requires ContentAddressableStore")
        if (
            not isinstance(minimum_validation, ValidationLevel)
            or minimum_validation is ValidationLevel.QUARANTINED
        ):
            raise ContractViolation("parity layer minimum validation is invalid")
        self.store = store
        self.cas = cas
        self.minimum_validation = minimum_validation

    def register(
        self,
        *,
        layer: CompositionLayer,
        tenant_id: str,
        project_id: str,
        principal_digest: str,
        authorization_digest: str,
        compatibility_digest: str,
        work_digest: str,
        material: bytes,
        validation_level: ValidationLevel = ValidationLevel.TEST_VERIFIED,
    ) -> RegisteredLayerMaterial:
        """Seal and bind one server-produced layer artifact."""

        binding = _binding_document(
            layer=layer,
            tenant_id=tenant_id,
            project_id=project_id,
            principal_digest=principal_digest,
            authorization_digest=authorization_digest,
            compatibility_digest=compatibility_digest,
            work_digest=work_digest,
        )
        self._ensure_project_scope(tenant_id, project_id)
        if not isinstance(material, bytes) or not material:
            raise ContractViolation("parity layer material must be non-empty immutable bytes")
        if (
            not isinstance(validation_level, ValidationLevel)
            or not validation_level.satisfies(self.minimum_validation)
        ):
            raise ContractViolation(
                "parity layer material does not meet the configured validation floor"
            )

        binding_digest = digest_of(binding)
        material_digest = self.cas.put_bytes(
            material,
            artifact_kind=f"cache-parity-{layer.value.lower()}-material",
        )
        manifest: dict[str, object] = {
            "schema_version": PARITY_LAYER_MANIFEST_SCHEMA_VERSION,
            "kind": PARITY_LAYER_MANIFEST_KIND,
            **binding,
            "binding_digest": binding_digest,
            "material_digest": material_digest,
            "size_bytes": len(material),
            "validation_level": str(validation_level),
        }
        manifest_bytes = canonical_json_bytes(manifest)
        manifest_digest = self.cas.put_bytes(
            manifest_bytes,
            artifact_kind="cache-parity-layer-manifest",
        )
        source_id = _binding_source_id(layer, binding_digest)

        with self.store.transaction():
            targets = self.store.artifact_targets(
                tenant_id,
                PARITY_LAYER_BINDING_SOURCE_KIND,
                source_id,
            )
            if targets and targets != [manifest_digest]:
                raise IdempotencyConflict(
                    "cache-parity layer binding already names different material",
                    layer=layer.value,
                    binding_digest=binding_digest,
                )
            material_record = self.store.register_artifact(
                tenant_id,
                material_digest,
                len(material),
                "application/octet-stream",
                f"cache-parity-{layer.value.lower()}-material",
                validation_level=validation_level,
                metadata={
                    "project_id": project_id,
                    "binding_digest": binding_digest,
                    "layer": layer.value,
                },
            )
            if not self._artifact_matches(
                material_record,
                artifact_kind=f"cache-parity-{layer.value.lower()}-material",
                media_type="application/octet-stream",
                size_bytes=len(material),
                project_id=project_id,
                binding_digest=binding_digest,
                layer=layer,
            ):
                raise IdempotencyConflict(
                    "cache-parity material metadata conflicts with its binding",
                    layer=layer.value,
                    material_digest=material_digest,
                )
            manifest_record = self.store.register_artifact(
                tenant_id,
                manifest_digest,
                len(manifest_bytes),
                "application/json",
                "cache-parity-layer-manifest",
                validation_level=validation_level,
                metadata={
                    "project_id": project_id,
                    "binding_digest": binding_digest,
                    "layer": layer.value,
                },
            )
            if not self._artifact_matches(
                manifest_record,
                artifact_kind="cache-parity-layer-manifest",
                media_type="application/json",
                size_bytes=len(manifest_bytes),
                project_id=project_id,
                binding_digest=binding_digest,
                layer=layer,
            ):
                raise IdempotencyConflict(
                    "cache-parity manifest metadata conflicts with its binding",
                    layer=layer.value,
                    manifest_digest=manifest_digest,
                )
            self.store.add_artifact_ref(
                tenant_id,
                PARITY_LAYER_BINDING_SOURCE_KIND,
                source_id,
                manifest_digest,
                "binding-manifest",
            )
            self.store.add_artifact_ref(
                tenant_id,
                PARITY_LAYER_MANIFEST_SOURCE_KIND,
                manifest_digest,
                material_digest,
                "verified-material",
            )

        return RegisteredLayerMaterial(
            layer=layer,
            binding_digest=binding_digest,
            manifest_digest=manifest_digest,
            material_digest=material_digest,
            size_bytes=len(material),
            validation_level=validation_level,
        )

    def probe(self, request: CompositionRequest, layer: CompositionLayer) -> LayerProbe:
        """Resolve and independently reverify one exact request binding."""

        _production_layer(layer)
        if not isinstance(request, CompositionRequest):
            raise ContractViolation("parity layer probe requires CompositionRequest")
        try:
            self._ensure_project_scope(request.tenant_id, request.project_id)
            expected_binding = _binding_document(
                layer=layer,
                tenant_id=request.tenant_id,
                project_id=request.project_id,
                principal_digest=request.principal_digest,
                authorization_digest=request.authorization_digest,
                compatibility_digest=request.compatibility_digest,
                work_digest=request.work_digest,
            )
            binding_digest = digest_of(expected_binding)
            source_id = _binding_source_id(layer, binding_digest)
            targets = self.store.artifact_targets(
                request.tenant_id,
                PARITY_LAYER_BINDING_SOURCE_KIND,
                source_id,
            )
            if not targets:
                return LayerProbe.miss("LAYER_MATERIAL_NOT_REGISTERED")
            if len(targets) != 1:
                return LayerProbe.error("LAYER_BINDING_CONFLICT")
            manifest_digest = require_digest(targets[0])
            manifest_artifact = self.store.get_artifact(request.tenant_id, manifest_digest)
            if not self._eligible(manifest_artifact):
                return LayerProbe.error("LAYER_MANIFEST_NOT_ELIGIBLE")
            manifest = self._read_manifest(manifest_digest)
            if not self._artifact_matches(
                manifest_artifact,
                artifact_kind="cache-parity-layer-manifest",
                media_type="application/json",
                size_bytes=len(canonical_json_bytes(manifest)),
                project_id=request.project_id,
                binding_digest=binding_digest,
                layer=layer,
            ):
                return LayerProbe.error("LAYER_MANIFEST_METADATA_DRIFT")
            if set(manifest) != _MANIFEST_FIELDS:
                return LayerProbe.error("LAYER_MANIFEST_SHAPE_INVALID")
            if (
                manifest.get("schema_version") != PARITY_LAYER_MANIFEST_SCHEMA_VERSION
                or manifest.get("kind") != PARITY_LAYER_MANIFEST_KIND
                or any(manifest.get(name) != value for name, value in expected_binding.items())
                or manifest.get("binding_digest") != binding_digest
                or digest_of(expected_binding) != binding_digest
            ):
                return LayerProbe.error("LAYER_MANIFEST_SCOPE_DRIFT")
            material_digest = require_digest(str(manifest.get("material_digest")))
            size_bytes = manifest.get("size_bytes")
            if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 1:
                return LayerProbe.error("LAYER_MANIFEST_SIZE_INVALID")
            try:
                declared_validation = ValidationLevel(str(manifest.get("validation_level")))
            except ValueError:
                return LayerProbe.error("LAYER_MANIFEST_VALIDATION_INVALID")
            if not declared_validation.satisfies(self.minimum_validation):
                return LayerProbe.error("LAYER_MANIFEST_VALIDATION_INSUFFICIENT")
            material_artifact = self.store.get_artifact(request.tenant_id, material_digest)
            if not self._eligible(material_artifact):
                return LayerProbe.error("LAYER_MATERIAL_NOT_ELIGIBLE")
            if material_artifact is None:
                return LayerProbe.error("LAYER_MATERIAL_NOT_ELIGIBLE")
            if not self._artifact_matches(
                material_artifact,
                artifact_kind=f"cache-parity-{layer.value.lower()}-material",
                media_type="application/octet-stream",
                size_bytes=size_bytes,
                project_id=request.project_id,
                binding_digest=binding_digest,
                layer=layer,
            ):
                return LayerProbe.error("LAYER_MATERIAL_METADATA_DRIFT")
            if not material_artifact.validation_level.satisfies(declared_validation):
                return LayerProbe.error("LAYER_MATERIAL_VALIDATION_DRIFT")
            linked = self.store.artifact_targets(
                request.tenant_id,
                PARITY_LAYER_MANIFEST_SOURCE_KIND,
                manifest_digest,
            )
            if linked != [material_digest]:
                return LayerProbe.error("LAYER_MATERIAL_REFERENCE_DRIFT")
            material = self.cas.get_bytes(material_digest, verify=True)
            if len(material) != size_bytes or sha256_bytes(material) != material_digest:
                return LayerProbe.error("LAYER_MATERIAL_DIGEST_MISMATCH")
            return LayerProbe.hit(
                material_digest,
                reason_code="LAYER_MATERIAL_VERIFIED",
            )
        except (ElmosCacheError, KeyError, TypeError, ValueError, UnicodeDecodeError):
            return LayerProbe.error("LAYER_MATERIAL_VERIFICATION_FAILED")

    def probe_for(self, layer: CompositionLayer) -> LayerProbeFn:
        resolved = _production_layer(layer)

        def probe(request: CompositionRequest) -> LayerProbe:
            return self.probe(request, resolved)

        return probe

    def _read_manifest(self, manifest_digest: str) -> dict[str, Any]:
        raw = self.cas.get_bytes(manifest_digest, verify=True)
        decoded = json.loads(raw.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ContractViolation("cache-parity layer manifest must be an object")
        if canonical_json_bytes(decoded) != raw:
            raise ContractViolation("cache-parity layer manifest is not canonical")
        return decoded

    def _eligible(self, artifact: Any) -> bool:
        return bool(
            artifact is not None
            and artifact.storage_state not in {
                ArtifactStorageState.DELETED,
                ArtifactStorageState.DELETING,
                ArtifactStorageState.QUARANTINED,
            }
            and artifact.validation_level.satisfies(self.minimum_validation)
        )

    @staticmethod
    def _artifact_matches(
        artifact: Any,
        *,
        artifact_kind: str,
        media_type: str,
        size_bytes: int,
        project_id: str,
        binding_digest: str,
        layer: CompositionLayer,
    ) -> bool:
        if artifact is None:
            return False
        metadata = artifact.metadata
        return (
            artifact.artifact_kind == artifact_kind
            and artifact.media_type == media_type
            and artifact.size_bytes == size_bytes
            and isinstance(metadata, dict)
            and metadata.get("project_id") == project_id
            and metadata.get("binding_digest") == binding_digest
            and metadata.get("layer") == layer.value
        )

    def _ensure_project_scope(self, tenant_id: str, project_id: str) -> None:
        _identifier(tenant_id, "tenant_id")
        _identifier(project_id, "project_id")
        row = self.store.query_one(
            "SELECT tenant_id FROM projects WHERE project_id=?",
            (project_id,),
        )
        if row is None:
            raise NotFound("cache-parity composition project does not exist")
        if str(row[0]) != tenant_id:
            raise TenantMismatch("cache-parity composition project belongs to another tenant")


@dataclass(frozen=True, slots=True)
class FiveLayerProductionCompositionRoot:
    """Construct complete read-side wiring from trusted durable services."""

    serving_boundary: SignedServingBoundary
    layer_registry: PersistentLayerMaterialRegistry
    cache_deadline_seconds: float = 5.0
    monotonic: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        if not isinstance(self.serving_boundary, SignedServingBoundary):
            raise ContractViolation("production composition root requires a signed boundary")
        if not isinstance(self.layer_registry, PersistentLayerMaterialRegistry):
            raise ContractViolation("production composition root requires a durable layer registry")
        if self.cache_deadline_seconds <= 0:
            raise ContractViolation("production composition deadline must be positive")

    def build(self) -> ServingCompositionWiring:
        probes: Mapping[CompositionLayer, LayerProbeFn] = {
            layer: self.layer_registry.probe_for(layer) for layer in _PRODUCTION_LAYERS
        }
        return ServingCompositionWiring(
            serving_boundary=self.serving_boundary,
            layer_probes=probes,
            cache_deadline_seconds=self.cache_deadline_seconds,
            monotonic=self.monotonic,
        )


def build_production_serving_composition(
    *,
    serving_boundary: SignedServingBoundary,
    layer_registry: PersistentLayerMaterialRegistry,
    cache_deadline_seconds: float = 5.0,
    monotonic: Callable[[], float] = time.monotonic,
) -> ServingCompositionWiring:
    """Functional composition-root entry point for host applications."""

    return FiveLayerProductionCompositionRoot(
        serving_boundary=serving_boundary,
        layer_registry=layer_registry,
        cache_deadline_seconds=cache_deadline_seconds,
        monotonic=monotonic,
    ).build()


__all__ = [
    "FiveLayerProductionCompositionRoot",
    "PARITY_LAYER_BINDING_SOURCE_KIND",
    "PARITY_LAYER_MANIFEST_KIND",
    "PARITY_LAYER_MANIFEST_SCHEMA_VERSION",
    "PARITY_LAYER_MANIFEST_SOURCE_KIND",
    "PersistentLayerMaterialRegistry",
    "RegisteredLayerMaterial",
    "build_production_serving_composition",
]
