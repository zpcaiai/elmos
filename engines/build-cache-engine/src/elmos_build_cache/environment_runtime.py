"""Side-effect-bounded materialisation of verified environment snapshot layers.

The environment snapshot service deliberately stops at verified immutable
bytes.  This module is the next, still-local boundary: it may place those
bytes in a caller-owned disposable workspace, but it may not install, mount,
start, execute, or fetch anything.  Every destination is a portable logical
path below the workspace and every published file appears atomically.
"""

from __future__ import annotations

import os
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .canonical import (
    detect_path_collisions,
    digest_of,
    fsync_directory,
    normalize_logical_path,
    require_digest,
    resolve_within,
    sha256_file,
)
from .environment_cache import RestoreAction
from .environment_service import (
    EnvironmentLayerType,
    EnvironmentRestoreResult,
    VerifiedEnvironmentLayer,
)
from .errors import ContractViolation, UnsafePath

ENVIRONMENT_MATERIALIZATION_SCHEMA_VERSION = "1.0.0"
ENVIRONMENT_MATERIALIZATION_RECEIPT_KIND = "elmos.environment-layer-materialization-receipt/v1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}$")
_LAYER_DOCUMENT_FIELDS = frozenset(
    {
        "layer_type",
        "layer_digest",
        "size_bytes",
        "logical_path",
        "destination_binding_digest",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "tenant_id",
        "project_id",
        "snapshot_key",
        "manifest_digest",
        "workspace_digest",
        "operation",
        "activation_performed",
        "mount_performed",
        "network_access_performed",
        "layer_count",
        "layers",
        "receipt_digest",
    }
)


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field_name} must be a bounded identifier")
    return value


def _string_value(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field_name} must be a string")
    return value


def _digest_value(value: object, field_name: str) -> str:
    return require_digest(_string_value(value, field_name))


@dataclass(frozen=True, slots=True)
class EnvironmentLayerDestination:
    """One caller-selected, non-executable logical destination."""

    layer_type: EnvironmentLayerType
    logical_path: str
    executable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.layer_type, EnvironmentLayerType):
            raise ContractViolation("environment destination has an unknown layer type")
        object.__setattr__(self, "logical_path", normalize_logical_path(self.logical_path))
        if not isinstance(self.executable, bool):
            raise ContractViolation("environment destination executable flag must be boolean")
        if self.executable:
            raise ContractViolation("environment layer executable activation is forbidden")


@dataclass(frozen=True, slots=True)
class MaterializedEnvironmentLayer:
    """Content-free receipt entry for one atomically published layer."""

    layer_type: EnvironmentLayerType
    layer_digest: str
    size_bytes: int
    logical_path: str
    destination_binding_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.layer_type, EnvironmentLayerType):
            raise ContractViolation("materialized layer has an unknown layer type")
        require_digest(self.layer_digest)
        require_digest(self.destination_binding_digest)
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ContractViolation("materialized layer size must be non-negative")
        object.__setattr__(self, "logical_path", normalize_logical_path(self.logical_path))

    def to_dict(self) -> dict[str, object]:
        return {
            "layer_type": self.layer_type.value,
            "layer_digest": self.layer_digest,
            "size_bytes": self.size_bytes,
            "logical_path": self.logical_path,
            "destination_binding_digest": self.destination_binding_digest,
        }


@dataclass(frozen=True, slots=True)
class EnvironmentMaterializationReceipt:
    """Digest-bound evidence for a no-execution local materialisation."""

    tenant_id: str
    project_id: str
    snapshot_key: str
    manifest_digest: str
    workspace_digest: str
    layers: tuple[MaterializedEnvironmentLayer, ...]

    def __post_init__(self) -> None:
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")
        require_digest(self.snapshot_key)
        require_digest(self.manifest_digest)
        require_digest(self.workspace_digest)
        if not self.layers:
            raise ContractViolation("environment materialization receipt requires layers")
        if len({item.layer_type for item in self.layers}) != len(self.layers):
            raise ContractViolation("environment materialization receipt repeats a layer type")

    def unsigned_document(self) -> dict[str, object]:
        return {
            "schema_version": ENVIRONMENT_MATERIALIZATION_SCHEMA_VERSION,
            "kind": ENVIRONMENT_MATERIALIZATION_RECEIPT_KIND,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "snapshot_key": self.snapshot_key,
            "manifest_digest": self.manifest_digest,
            "workspace_digest": self.workspace_digest,
            "operation": "MATERIALIZE_VERIFIED_BYTES",
            "activation_performed": False,
            "mount_performed": False,
            "network_access_performed": False,
            "layer_count": len(self.layers),
            "layers": [item.to_dict() for item in self.layers],
        }

    @property
    def receipt_digest(self) -> str:
        return digest_of(self.unsigned_document())

    def to_dict(self) -> dict[str, object]:
        document = self.unsigned_document()
        document["receipt_digest"] = self.receipt_digest
        return document


class EnvironmentLayerMaterializer(Protocol):
    """Trusted boundary after :meth:`EnvironmentSnapshotService.restore`."""

    def materialize(
        self,
        *,
        tenant_id: str,
        project_id: str,
        restored: EnvironmentRestoreResult,
        workspace_root: Path,
        destinations: Sequence[EnvironmentLayerDestination],
    ) -> EnvironmentMaterializationReceipt: ...


@dataclass(frozen=True, slots=True)
class _StagedLayer:
    verified: VerifiedEnvironmentLayer
    logical_path: str
    destination: Path
    temporary: Path


class LocalEnvironmentLayerMaterializer:
    """Materialize verified bytes without activation or external effects.

    The workspace must already exist and must not be a symlink.  Destinations
    must be absent, so this boundary can never overwrite caller data.  Writes
    are staged, fsynced, and then published with an atomic create-if-absent
    hard link; the staging inode is immediately removed after publication.
    """

    def materialize(
        self,
        *,
        tenant_id: str,
        project_id: str,
        restored: EnvironmentRestoreResult,
        workspace_root: Path,
        destinations: Sequence[EnvironmentLayerDestination],
    ) -> EnvironmentMaterializationReceipt:
        _identifier(tenant_id, "tenant_id")
        _identifier(project_id, "project_id")
        if not isinstance(restored, EnvironmentRestoreResult):
            raise ContractViolation("materializer requires an environment restore result")
        if restored.decision.action is not RestoreAction.RESTORE:
            raise ContractViolation("only an eligible verified restore may be materialized")
        if not restored.verified_layers:
            raise ContractViolation("verified restore contains no environment layers")

        root = self._workspace_root(workspace_root)
        workspace_digest = self._workspace_digest(root)
        target_by_type = self._destinations(destinations, restored.verified_layers)
        staged: list[_StagedLayer] = []
        created: list[Path] = []
        created_directories: list[Path] = []
        try:
            for layer in restored.verified_layers:
                target = target_by_type[layer.ref.layer_type]
                destination = self._destination(
                    root,
                    target.logical_path,
                    created_directories=created_directories,
                )
                temporary = self._stage(destination.parent, layer)
                staged.append(_StagedLayer(layer, target.logical_path, destination, temporary))

            for item in staged:
                self._revalidate_parent(root, item.destination)
                try:
                    os.link(item.temporary, item.destination, follow_symlinks=False)
                except FileExistsError as exc:
                    raise UnsafePath(
                        "environment destination appeared during materialization",
                        logical_path=item.logical_path,
                    ) from exc
                created.append(item.destination)
                item.temporary.unlink(missing_ok=True)
                fsync_directory(item.destination.parent)
                self._verify_published(item.destination, item.verified)

            layer_receipts = tuple(
                MaterializedEnvironmentLayer(
                    layer_type=item.verified.ref.layer_type,
                    layer_digest=item.verified.ref.digest,
                    size_bytes=item.verified.ref.size_bytes,
                    logical_path=item.logical_path,
                    destination_binding_digest=_destination_binding_digest(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        snapshot_key=restored.snapshot_key,
                        manifest_digest=restored.manifest_digest,
                        workspace_digest=workspace_digest,
                        layer_type=item.verified.ref.layer_type.value,
                        layer_digest=item.verified.ref.digest,
                        size_bytes=item.verified.ref.size_bytes,
                        logical_path=item.logical_path,
                    ),
                )
                for item in staged
            )
            receipt = EnvironmentMaterializationReceipt(
                tenant_id=tenant_id,
                project_id=project_id,
                snapshot_key=restored.snapshot_key,
                manifest_digest=restored.manifest_digest,
                workspace_digest=workspace_digest,
                layers=layer_receipts,
            )
            verify_environment_materialization_receipt(receipt.to_dict())
            return receipt
        except Exception:
            for path in reversed(created):
                path.unlink(missing_ok=True)
                fsync_directory(path.parent)
            for directory in reversed(created_directories):
                try:
                    directory.rmdir()
                except OSError:
                    # A pre-existing sibling or a successfully promoted file
                    # may keep the directory non-empty; never remove user data.
                    continue
                fsync_directory(directory.parent)
            raise
        finally:
            for item in staged:
                item.temporary.unlink(missing_ok=True)

    @staticmethod
    def _workspace_root(workspace_root: Path) -> Path:
        root = Path(workspace_root)
        if root.is_symlink():
            raise UnsafePath("environment workspace root cannot be a symlink")
        try:
            resolved = root.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise UnsafePath("environment workspace root must already exist") from exc
        if not resolved.is_dir():
            raise UnsafePath("environment workspace root must be a directory")
        return resolved

    @staticmethod
    def _workspace_digest(root: Path) -> str:
        metadata = root.stat(follow_symlinks=False)
        return digest_of(
            {
                "kind": "elmos.environment-disposable-workspace/v1",
                "resolved_path": str(root),
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
            }
        )

    @staticmethod
    def _destinations(
        destinations: Sequence[EnvironmentLayerDestination],
        layers: Sequence[VerifiedEnvironmentLayer],
    ) -> Mapping[EnvironmentLayerType, EnvironmentLayerDestination]:
        supplied = tuple(destinations)
        if any(not isinstance(item, EnvironmentLayerDestination) for item in supplied):
            raise ContractViolation("environment destinations must use the closed type")
        layer_types = tuple(item.ref.layer_type for item in layers)
        target_types = tuple(item.layer_type for item in supplied)
        if len(set(target_types)) != len(target_types):
            raise ContractViolation("environment destinations repeat a layer type")
        if set(target_types) != set(layer_types):
            raise ContractViolation("environment destinations must cover every restored layer")
        paths = [item.logical_path for item in supplied]
        collisions = detect_path_collisions(paths)
        if collisions:
            raise UnsafePath("environment destinations collide", collisions=collisions)
        return {item.layer_type: item for item in supplied}

    @staticmethod
    def _destination(
        root: Path,
        logical_path: str,
        *,
        created_directories: list[Path] | None = None,
    ) -> Path:
        destination = resolve_within(root, logical_path)
        parent = destination.parent
        relative_parent = parent.relative_to(root)
        cursor = root
        for part in relative_parent.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise UnsafePath(
                    "symlink on environment materialization path",
                    logical_path=logical_path,
                )
            if cursor.exists():
                if not cursor.is_dir():
                    raise UnsafePath(
                        "non-directory on environment materialization path",
                        logical_path=logical_path,
                    )
            else:
                cursor.mkdir(mode=0o700)
                if created_directories is not None:
                    created_directories.append(cursor)
            resolved_cursor = cursor.resolve(strict=True)
            if resolved_cursor != root and root not in resolved_cursor.parents:
                raise UnsafePath(
                    "environment materialization parent escaped the workspace",
                    logical_path=logical_path,
                )
        if destination.exists() or destination.is_symlink():
            raise UnsafePath(
                "environment materialization refuses to overwrite a destination",
                logical_path=logical_path,
            )
        return destination

    @staticmethod
    def _stage(parent: Path, layer: VerifiedEnvironmentLayer) -> Path:
        fd, name = tempfile.mkstemp(prefix=".elmos-env-layer-", dir=parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb", closefd=True) as handle:
                handle.write(layer.content)
                handle.flush()
                os.fsync(handle.fileno())
                os.fchmod(handle.fileno(), 0o600)
            observed_digest, observed_size = sha256_file(temporary)
            if observed_digest != layer.ref.digest or observed_size != layer.ref.size_bytes:
                raise ContractViolation("staged environment layer failed digest verification")
            return temporary
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _revalidate_parent(root: Path, destination: Path) -> None:
        parent = destination.parent
        if parent.is_symlink():
            raise UnsafePath("environment destination parent became a symlink")
        resolved = parent.resolve(strict=True)
        if resolved != root and root not in resolved.parents:
            raise UnsafePath("environment destination parent escaped the workspace")
        if destination.exists() or destination.is_symlink():
            raise UnsafePath("environment destination is no longer absent")

    @staticmethod
    def _verify_published(destination: Path, layer: VerifiedEnvironmentLayer) -> None:
        metadata = destination.lstat()
        if not stat.S_ISREG(metadata.st_mode) or destination.is_symlink():
            raise UnsafePath("published environment layer is not a regular file")
        if metadata.st_mode & 0o111:
            raise ContractViolation("published environment layer became executable")
        observed_digest, observed_size = sha256_file(destination)
        if observed_digest != layer.ref.digest or observed_size != layer.ref.size_bytes:
            raise ContractViolation("published environment layer failed digest verification")


def _destination_binding_digest(
    *,
    tenant_id: str,
    project_id: str,
    snapshot_key: str,
    manifest_digest: str,
    workspace_digest: str,
    layer_type: str,
    layer_digest: str,
    size_bytes: int,
    logical_path: str,
) -> str:
    return digest_of(
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "snapshot_key": snapshot_key,
            "manifest_digest": manifest_digest,
            "workspace_digest": workspace_digest,
            "layer_type": layer_type,
            "layer_digest": layer_digest,
            "size_bytes": size_bytes,
            "logical_path": logical_path,
            "mode": "non-executable-0600",
        }
    )


def verify_environment_materialization_receipt(document: Mapping[str, Any]) -> None:
    """Fail closed when a receipt field or destination binding was changed."""

    if not isinstance(document, Mapping) or set(document) != _RECEIPT_FIELDS:
        raise ContractViolation("environment materialization receipt has an invalid shape")
    if (
        document.get("schema_version") != ENVIRONMENT_MATERIALIZATION_SCHEMA_VERSION
        or document.get("kind") != ENVIRONMENT_MATERIALIZATION_RECEIPT_KIND
        or document.get("operation") != "MATERIALIZE_VERIFIED_BYTES"
        or document.get("activation_performed") is not False
        or document.get("mount_performed") is not False
        or document.get("network_access_performed") is not False
    ):
        raise ContractViolation("environment materialization receipt boundary is invalid")

    tenant_id = _identifier(_string_value(document.get("tenant_id"), "tenant_id"), "tenant_id")
    project_id = _identifier(
        _string_value(document.get("project_id"), "project_id"),
        "project_id",
    )
    snapshot_key = _digest_value(document.get("snapshot_key"), "snapshot_key")
    manifest_digest = _digest_value(document.get("manifest_digest"), "manifest_digest")
    workspace_digest = _digest_value(document.get("workspace_digest"), "workspace_digest")
    raw_layers = document.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        raise ContractViolation("environment materialization receipt layers are invalid")
    if document.get("layer_count") != len(raw_layers):
        raise ContractViolation("environment materialization receipt layer count drifted")

    seen_types: set[str] = set()
    seen_paths: set[str] = set()
    for raw_layer in raw_layers:
        if not isinstance(raw_layer, Mapping) or set(raw_layer) != _LAYER_DOCUMENT_FIELDS:
            raise ContractViolation("environment materialization layer receipt is malformed")
        layer_type_raw = _string_value(raw_layer.get("layer_type"), "layer_type")
        try:
            layer_type = EnvironmentLayerType(layer_type_raw)
        except ValueError as exc:
            raise ContractViolation("environment materialization layer type is invalid") from exc
        layer_digest = _digest_value(raw_layer.get("layer_digest"), "layer_digest")
        destination_digest = _digest_value(
            raw_layer.get("destination_binding_digest"),
            "destination_binding_digest",
        )
        size_bytes = raw_layer.get("size_bytes")
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
            raise ContractViolation("environment materialization layer size is invalid")
        logical_path_raw = raw_layer.get("logical_path")
        if not isinstance(logical_path_raw, str):
            raise ContractViolation("environment materialization logical path is invalid")
        logical_path = normalize_logical_path(logical_path_raw)
        if logical_path != logical_path_raw:
            raise ContractViolation("environment materialization logical path is not canonical")
        if layer_type.value in seen_types or logical_path in seen_paths:
            raise ContractViolation("environment materialization receipt repeats a destination")
        seen_types.add(layer_type.value)
        seen_paths.add(logical_path)
        expected = _destination_binding_digest(
            tenant_id=tenant_id,
            project_id=project_id,
            snapshot_key=snapshot_key,
            manifest_digest=manifest_digest,
            workspace_digest=workspace_digest,
            layer_type=layer_type.value,
            layer_digest=layer_digest,
            size_bytes=size_bytes,
            logical_path=logical_path,
        )
        if destination_digest != expected:
            raise ContractViolation("environment destination binding digest is invalid")

    receipt_digest = _digest_value(document.get("receipt_digest"), "receipt_digest")
    unsigned = {key: value for key, value in document.items() if key != "receipt_digest"}
    if receipt_digest != digest_of(unsigned):
        raise ContractViolation("environment materialization receipt digest is invalid")


__all__ = [
    "ENVIRONMENT_MATERIALIZATION_RECEIPT_KIND",
    "ENVIRONMENT_MATERIALIZATION_SCHEMA_VERSION",
    "EnvironmentLayerDestination",
    "EnvironmentLayerMaterializer",
    "EnvironmentMaterializationReceipt",
    "LocalEnvironmentLayerMaterializer",
    "MaterializedEnvironmentLayer",
    "verify_environment_materialization_receipt",
]
