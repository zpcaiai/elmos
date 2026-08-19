"""Typed configuration for the cache/staging subsystem.

Loading is total: an unknown key is an error, not a silent default, because a
mistyped ``undeclared_output_policy`` would otherwise weaken an invariant
without anyone noticing.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, get_args, get_origin

from .enums import CacheMode, ValidationLevel
from .errors import ContractViolation
from .yamlmin import safe_load

DEFAULT_CONFIG_NAMES = ("elmos-cache.yaml", "elmos-cache.local.yaml")


@dataclass(frozen=True)
class LocalStorageConfig:
    root: str = ".elmos/cache"
    metadata: str = ".elmos/cache/index.sqlite"
    max_size_gb: int = 100
    canonical_hash: str = "sha256"
    fast_pre_hash: str = "blake2b"
    compression: str = "none"
    materialize: str = "reflink-hardlink-copy"


@dataclass(frozen=True)
class RemoteConfig:
    enabled: bool = False
    backend: str = "filesystem"
    bucket: str = "elmos-cache"
    prefix: str = ""
    root: str = ""
    upload_mode: str = "write-behind"
    checksum: str = "sha256"
    multipart_threshold_mb: int = 64
    chunk_size_mb: int = 8
    max_parallel_transfers: int = 8
    offline_fallback: bool = True
    retry_budget: int = 5


@dataclass(frozen=True)
class RedisConfig:
    enabled: bool = False
    purposes: tuple[str, ...] = ()
    authoritative: bool = False


@dataclass(frozen=True)
class FingerprintConfig:
    normalize_paths: bool = True
    normalize_line_endings: bool = True
    normalize_unicode: str = "NFC"
    public_interface_hash: bool = True
    semantic_ir_hash: bool = True
    declared_environment: tuple[str, ...] = ("LANG", "TZ", "ELMOS_TARGET_PROFILE")


@dataclass(frozen=True)
class WorkspaceConfig:
    root: str = ".elmos/workspaces"
    source_read_only: bool = True
    quota_gb_per_run: int = 30
    max_files_per_run: int = 500_000
    max_single_file_mb: int = 2048
    scratch_checkpointed: bool = False
    undeclared_output_policy: str = "quarantine"
    publish_strategy: str = "versioned-atomic-pointer"
    keep_previous_published_versions: int = 2

    @property
    def quota_bytes(self) -> int:
        return self.quota_gb_per_run * 1024**3

    @property
    def max_single_file_bytes(self) -> int:
        return self.max_single_file_mb * 1024**2


@dataclass(frozen=True)
class CheckpointConfig:
    stage_boundary: bool = True
    interval_seconds: int = 30
    max_chain_length: int = 100
    verify_all_digests_on_resume: bool = True


@dataclass(frozen=True)
class ValidationConfig:
    default_minimum: ValidationLevel = ValidationLevel.TEST_VERIFIED
    production_minimum: ValidationLevel = ValidationLevel.PRODUCTION_CERTIFIED
    quarantine_on_nondeterminism: bool = True
    exact_cache_only_for_direct_reuse: bool = True
    negative_cache_ttl_seconds: int = 900


@dataclass(frozen=True)
class SecurityConfig:
    tenant_isolation: bool = True
    sign_provenance: bool = True
    #: Refuse shared-secret provenance signing. A symmetric verifier holds
    #: forging material, so production deployments require Ed25519.
    require_asymmetric_provenance: bool = True
    scan_secrets_before_remote_upload: bool = True
    scan_secrets_before_publish: bool = True
    reject_symlink_escape: bool = True
    encrypt_sensitive_artifacts: bool = False
    max_archive_expansion_ratio: int = 200
    max_archive_entries: int = 20_000
    allow_executable_output: bool = True


@dataclass(frozen=True)
class RetentionConfig:
    successful_run_days: int = 90
    failed_run_days: int = 14
    quarantine_days: int = 30
    gc_grace_hours: int = 24
    protect_published: bool = True
    protect_checkpoints: bool = True
    protect_certificates: bool = True


@dataclass(frozen=True)
class ObservabilityConfig:
    otel_enabled: bool = False
    metrics_enabled: bool = True
    log_source_content: bool = False
    retain_all_failure_traces: bool = True


@dataclass(frozen=True)
class RolloutConfig:
    """Feature flags and kill switches for the staged rollout."""

    phase: str = "staging-only"
    generated_file_staging: bool = True
    exact_cache_read: bool = True
    exact_cache_write: bool = True
    remote_cache_read: bool = False
    remote_cache_write: bool = False
    semantic_reuse_candidates: bool = False
    shadow_compare: bool = False
    kill_switch: bool = False


@dataclass(frozen=True)
class CacheConfig:
    enabled: bool = True
    mode: CacheMode = CacheMode.READ_WRITE
    package_version: str = "1.0.0"
    local: LocalStorageConfig = field(default_factory=LocalStorageConfig)
    remote: RemoteConfig = field(default_factory=RemoteConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    fingerprint: FingerprintConfig = field(default_factory=FingerprintConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    checkpoint: CheckpointConfig = field(default_factory=CheckpointConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    rollout: RolloutConfig = field(default_factory=RolloutConfig)

    def resolved(self, base: Path) -> ResolvedPaths:
        return ResolvedPaths(
            cache_root=base / self.local.root,
            metadata=base / self.local.metadata,
            workspace_root=base / self.workspace.root,
        )


@dataclass(frozen=True)
class ResolvedPaths:
    cache_root: Path
    metadata: Path
    workspace_root: Path


def _coerce(annotation: Any, value: Any, path: str) -> Any:
    if is_dataclass(annotation) and isinstance(annotation, type):
        if value is None:
            return annotation()
        if not isinstance(value, dict):
            raise ContractViolation(f"{path}: expected a mapping", got=type(value).__name__)
        return _build(annotation, value, path)
    origin = get_origin(annotation)
    if origin is tuple:
        if value is None:
            return ()
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ContractViolation(f"{path}: expected a list", got=type(value).__name__)
        (item_type, _) = get_args(annotation)
        return tuple(_coerce(item_type, item, f"{path}[]") for item in value)
    if isinstance(annotation, type) and issubclass(annotation, CacheMode | ValidationLevel):
        try:
            return annotation(value)
        except ValueError as exc:
            raise ContractViolation(f"{path}: {exc}") from exc
    if annotation is bool:
        if isinstance(value, bool):
            return value
        raise ContractViolation(f"{path}: expected a boolean", got=repr(value))
    if annotation is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContractViolation(f"{path}: expected an integer", got=repr(value))
        return value
    if annotation is str:
        if not isinstance(value, str):
            raise ContractViolation(f"{path}: expected a string", got=repr(value))
        return value
    return value


def _build(cls: Any, data: dict[str, Any], path: str) -> Any:
    known = {f.name: f for f in fields(cls)}
    unknown = sorted(set(data) - set(known))
    if unknown:
        raise ContractViolation(f"{path}: unknown configuration keys", keys=unknown)
    kwargs: dict[str, Any] = {}
    for name, spec in known.items():
        if name not in data:
            continue
        annotation = _resolve(spec.type) if isinstance(spec.type, str) else spec.type
        kwargs[name] = _coerce(annotation, data[name], f"{path}.{name}")
    return cls(**kwargs)


_TYPE_NAMESPACE: dict[str, Any] = {
    "bool": bool,
    "int": int,
    "str": str,
    "CacheMode": CacheMode,
    "ValidationLevel": ValidationLevel,
    "LocalStorageConfig": LocalStorageConfig,
    "RemoteConfig": RemoteConfig,
    "RedisConfig": RedisConfig,
    "FingerprintConfig": FingerprintConfig,
    "WorkspaceConfig": WorkspaceConfig,
    "CheckpointConfig": CheckpointConfig,
    "ValidationConfig": ValidationConfig,
    "SecurityConfig": SecurityConfig,
    "RetentionConfig": RetentionConfig,
    "ObservabilityConfig": ObservabilityConfig,
    "RolloutConfig": RolloutConfig,
    "tuple[str, ...]": tuple[str, ...],
}


def _resolve(name: str) -> Any:
    if name in _TYPE_NAMESPACE:
        return _TYPE_NAMESPACE[name]
    return Any


def load_config_mapping(data: dict[str, Any]) -> CacheConfig:
    root = data.get("elmos", data)
    if isinstance(root, dict) and "cache" in root:
        root = root["cache"]
    if not isinstance(root, dict):
        raise ContractViolation("configuration root must be a mapping")
    result: CacheConfig = _build(CacheConfig, root, "elmos.cache")
    _validate(result)
    return result


def load_config(path: Path) -> CacheConfig:
    return load_config_mapping(safe_load(path.read_text(encoding="utf-8")) or {})


def default_config() -> CacheConfig:
    return CacheConfig()


def _validate(config: CacheConfig) -> None:
    if config.redis.enabled and config.redis.authoritative:
        raise ContractViolation("Redis must never be the authoritative store for cache truth")
    if config.workspace.undeclared_output_policy not in ("quarantine", "reject"):
        raise ContractViolation(
            "undeclared_output_policy must be 'quarantine' or 'reject'",
            value=config.workspace.undeclared_output_policy,
        )
    if config.workspace.publish_strategy not in ("versioned-atomic-pointer", "versioned-atomic-rename"):
        raise ContractViolation("unsupported publish strategy", value=config.workspace.publish_strategy)
    if config.remote.upload_mode not in ("read-through", "write-through", "write-behind"):
        raise ContractViolation("unsupported remote upload mode", value=config.remote.upload_mode)
    if config.validation.default_minimum is ValidationLevel.QUARANTINED:
        raise ContractViolation("default minimum validation level cannot be QUARANTINED")
    if config.workspace.keep_previous_published_versions < 1:
        raise ContractViolation("at least one previous published tree must be retained for rollback")
