"""Typed configuration for the cache/staging subsystem.

Loading is total: an unknown key is an error, not a silent default, because a
mistyped ``undeclared_output_policy`` would otherwise weaken an invariant
without anyone noticing.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, get_args, get_origin

from .canonical import require_digest
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
class PolicyConfig:
    """Cache replacement policy, admission, tracing and prefetch settings.

    Defaults are the conservative ones: a fixed policy per tier, no adaptive
    switching, no learned tuning, no tracing and no prefetch. Every SOTA
    behaviour is opt-in because the safe configuration must be the one you get
    by not thinking about it.
    """

    enabled: bool = True
    l0_policy: str = "W_TINY_LFU"
    l1_policy: str = "SIEVE"
    l2_policy: str = "GDSF"
    fallback: str = "SIEVE"
    objective_profile: str = "BALANCED"
    adaptive_selection: bool = False
    learned_tuning: bool = False
    learned_shadow_only: bool = True
    learned_canary_fraction: float = 0.0
    minimum_dwell_events: int = 5_000
    improvement_margin: float = 0.03
    admission_enabled: bool = False
    trace_capture: bool = False
    trace_sample_rate: float = 0.05
    trace_per_tenant_budget: int = 1_000_000
    prefetch_enabled: bool = False
    prefetch_horizon: int = 4
    prefetch_max_in_flight: int = 4
    prefetch_max_bytes: int = 512 * 1024 * 1024


@dataclass(frozen=True)
class PromptCacheConfig:
    """Provider-prefix reuse starts observation-only and is never task truth."""

    enabled: bool = False
    mode: str = "observe"
    compatibility_group: str = "prompt-v1"
    providers: tuple[str, ...] = ("openai", "anthropic", "self-hosted")
    disabled_tenant_scope_digests: tuple[str, ...] = ()
    disabled_provider_models: tuple[str, ...] = ()
    disabled_request_classes: tuple[str, ...] = ()
    provider_failure_threshold: int = 3
    provider_recovery_events: int = 10
    canonical_layout: bool = True
    stable_turn_cached_token_reuse_min: float = 0.90
    unexpected_full_prefix_miss_max: float = 0.02


@dataclass(frozen=True)
class ContextLedgerConfig:
    enabled: bool = True
    append_only: bool = True
    hash_chain: str = "sha256"
    whole_repository_reinjection: bool = False
    compaction_enabled: bool = True
    compaction_soft_limit_ratio: float = 0.72
    compaction_hard_limit_ratio: float = 0.88
    compaction_warmup_reuse_min: float = 0.80


@dataclass(frozen=True)
class EnvironmentSnapshotConfig:
    enabled: bool = False
    verify_digests_on_restore: bool = True
    embed_secret_values: bool = False
    hit_rate_min: float = 0.95
    warm_start_p95_reduction_min: float = 0.80
    default_ttl_seconds: int = 86_400


@dataclass(frozen=True)
class AffinityConfig:
    enabled: bool = False
    routing: str = "rendezvous"
    bounded_load_escape: bool = True
    fairness_guard: bool = True
    wrong_shard_rate_max: float = 0.01


@dataclass(frozen=True)
class CoordinatorConfig:
    enabled: bool = False
    singleflight: bool = True
    exact_action_before_model_call: bool = True
    restore_vs_recompute: str = "cost-aware"
    unified_attribution: bool = True
    max_parallel_probes: int = 6


@dataclass(frozen=True)
class CacheParityConfig:
    """v1.2 coding-agent cache controls and measured-only release gates."""

    enabled: bool = True
    schema_version: str = "1.2.0"
    claim_mode: str = "measured_only"
    rollout_phase: str = "observe"
    automatic_rollback: bool = True
    false_hit_immediate_rollback: bool = True
    unknown_outcome_rate_max: float = 0.01
    prompt_cache: PromptCacheConfig = field(default_factory=PromptCacheConfig)
    context_ledger: ContextLedgerConfig = field(default_factory=ContextLedgerConfig)
    environment_snapshots: EnvironmentSnapshotConfig = field(
        default_factory=EnvironmentSnapshotConfig
    )
    affinity: AffinityConfig = field(default_factory=AffinityConfig)
    coordinator: CoordinatorConfig = field(default_factory=CoordinatorConfig)


@dataclass(frozen=True)
class CacheConfig:
    enabled: bool = True
    mode: CacheMode = CacheMode.READ_WRITE
    package_version: str = "1.2.0"
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
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    parity: CacheParityConfig = field(default_factory=CacheParityConfig)

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
    if annotation is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ContractViolation(f"{path}: expected a number", got=repr(value))
        return float(value)
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
    "float": float,
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
    "PolicyConfig": PolicyConfig,
    "PromptCacheConfig": PromptCacheConfig,
    "ContextLedgerConfig": ContextLedgerConfig,
    "EnvironmentSnapshotConfig": EnvironmentSnapshotConfig,
    "AffinityConfig": AffinityConfig,
    "CoordinatorConfig": CoordinatorConfig,
    "CacheParityConfig": CacheParityConfig,
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
    _validate_policy(config.policy)
    validate_parity_config(config.parity)


def _validate_policy(policy: PolicyConfig) -> None:
    """Reject a policy section that names a policy or objective we do not have.

    Done by importing the real enums rather than duplicating their members, so
    a policy added to the portfolio is configurable the same day it lands.
    """

    from .cache_policy import PolicyName
    from .cache_simulator import ObjectiveProfile

    names = {member.value for member in PolicyName}
    for attribute in ("l0_policy", "l1_policy", "l2_policy", "fallback"):
        value = getattr(policy, attribute)
        if value not in names:
            raise ContractViolation(
                f"policy.{attribute} is not a known cache policy",
                value=value,
                known=sorted(names),
            )
    objectives = {member.value for member in ObjectiveProfile}
    if policy.objective_profile not in objectives:
        raise ContractViolation(
            "policy.objective_profile is not a known objective",
            value=policy.objective_profile,
            known=sorted(objectives),
        )
    if not 0.0 <= policy.learned_canary_fraction <= 1.0:
        raise ContractViolation(
            "policy.learned_canary_fraction must be a fraction",
            value=policy.learned_canary_fraction,
        )
    if policy.learned_shadow_only and policy.learned_canary_fraction > 0.0:
        raise ContractViolation(
            "policy.learned_canary_fraction requires learned_shadow_only to be false",
            value=policy.learned_canary_fraction,
        )
    if not 0.0 <= policy.trace_sample_rate <= 1.0:
        raise ContractViolation(
            "policy.trace_sample_rate must be a fraction", value=policy.trace_sample_rate
        )
    if policy.minimum_dwell_events < 1:
        raise ContractViolation(
            "policy.minimum_dwell_events must be positive", value=policy.minimum_dwell_events
        )
    if policy.improvement_margin < 0.0:
        raise ContractViolation(
            "policy.improvement_margin cannot be negative", value=policy.improvement_margin
        )
    if policy.prefetch_horizon < 1:
        raise ContractViolation(
            "policy.prefetch_horizon must be positive", value=policy.prefetch_horizon
        )
    if policy.prefetch_max_in_flight < 1:
        raise ContractViolation(
            "policy.prefetch_max_in_flight must be positive", value=policy.prefetch_max_in_flight
        )
    if policy.prefetch_max_bytes < 1:
        raise ContractViolation(
            "policy.prefetch_max_bytes must be positive", value=policy.prefetch_max_bytes
        )
    if policy.trace_per_tenant_budget < 1:
        raise ContractViolation(
            "policy.trace_per_tenant_budget must be positive",
            value=policy.trace_per_tenant_budget,
        )


def validate_parity_config(parity: CacheParityConfig) -> None:
    """Reject v1.2 parity settings that weaken the shipped safety envelope.

    Operators may make an SLO stricter, but repository configuration cannot
    turn rollback off or relax a v1.2 minimum/maximum.  Serving authorization
    is deliberately *not* configuration: the runtime additionally requires a
    trusted, asymmetric gate receipt and an executable layer wiring.
    """

    if parity.schema_version != "1.2.0":
        raise ContractViolation("unsupported cache parity schema", value=parity.schema_version)
    if parity.claim_mode != "measured_only":
        raise ContractViolation("cache parity claims must remain measured_only")
    if not parity.automatic_rollback:
        raise ContractViolation("cache parity automatic rollback cannot be disabled")
    if not parity.false_hit_immediate_rollback:
        raise ContractViolation("cache parity false-hit rollback cannot be disabled")
    phases = {
        "observe",
        "shadow",
        "internal",
        "canary",
        "5_percent",
        "25_percent",
        "50_percent",
        "100_percent",
    }
    if parity.rollout_phase not in phases:
        raise ContractViolation("unknown cache parity rollout phase", value=parity.rollout_phase)
    if not 0.0 <= parity.unknown_outcome_rate_max <= 0.01:
        raise ContractViolation("unknown outcome budget cannot exceed the v1.2 maximum")
    prompt = parity.prompt_cache
    if prompt.mode not in {"observe", "shadow", "serve"}:
        raise ContractViolation("unsupported provider prompt cache mode", value=prompt.mode)
    if not prompt.compatibility_group or not prompt.providers:
        raise ContractViolation("provider cache compatibility and providers are required")
    if len(set(prompt.providers)) != len(prompt.providers) or not set(prompt.providers) <= {
        "openai",
        "anthropic",
        "self-hosted",
    }:
        raise ContractViolation("provider cache list contains duplicates or unknown providers")
    for digest in prompt.disabled_tenant_scope_digests:
        require_digest(digest)
    for item in prompt.disabled_provider_models:
        provider, separator, model = item.partition(":")
        if separator != ":" or provider not in prompt.providers or not model:
            raise ContractViolation(
                "provider/model kill switches must use an enabled provider:model",
                value=item,
            )
    request_classes = {
        "CONVERSATIONAL",
        "DETERMINISTIC_CONVERSION",
        "REPAIR",
        "TEST_GENERATION",
        "SUMMARIZATION",
        "ONE_SHOT",
    }
    if not set(prompt.disabled_request_classes) <= request_classes:
        raise ContractViolation("provider cache request-class kill switch is unknown")
    if not 1 <= prompt.provider_failure_threshold <= 3:
        raise ContractViolation(
            "provider cache failure threshold cannot exceed the v1.2 maximum"
        )
    if prompt.provider_recovery_events < 10:
        raise ContractViolation(
            "provider cache recovery evidence cannot be weaker than the v1.2 minimum"
        )
    if not prompt.canonical_layout:
        raise ContractViolation("provider prompt cache must retain canonical layout")
    if not 0.90 <= prompt.stable_turn_cached_token_reuse_min <= 1.0:
        raise ContractViolation("prompt cached-token SLO cannot be weaker than v1.2")
    if not 0.0 <= prompt.unexpected_full_prefix_miss_max <= 0.02:
        raise ContractViolation("prompt miss budget cannot exceed the v1.2 maximum")
    context = parity.context_ledger
    if not context.append_only or context.hash_chain != "sha256":
        raise ContractViolation("context ledger must remain append-only and SHA-256 linked")
    if context.whole_repository_reinjection:
        raise ContractViolation("whole-repository reinjection is forbidden after initial indexing")
    if not (
        0.0
        < context.compaction_soft_limit_ratio
        < context.compaction_hard_limit_ratio
        < 1.0
    ):
        raise ContractViolation("context compaction limits must be ordered fractions")
    if not 0.80 <= context.compaction_warmup_reuse_min <= 1.0:
        raise ContractViolation("context compaction warmup SLO cannot be weaker than v1.2")
    environment = parity.environment_snapshots
    if environment.embed_secret_values:
        raise ContractViolation("secret values must never be embedded in environment snapshots")
    if not environment.verify_digests_on_restore:
        raise ContractViolation("environment restores must verify digests")
    if not 0.95 <= environment.hit_rate_min <= 1.0:
        raise ContractViolation("environment hit-rate SLO cannot be weaker than v1.2")
    if not 0.80 <= environment.warm_start_p95_reduction_min <= 1.0:
        raise ContractViolation("environment warm-start SLO cannot be weaker than v1.2")
    if not 1 <= environment.default_ttl_seconds <= 86_400:
        raise ContractViolation("environment snapshot TTL cannot exceed the v1.2 maximum")
    affinity = parity.affinity
    if affinity.routing != "rendezvous":
        raise ContractViolation("only deterministic rendezvous affinity is supported")
    if not affinity.bounded_load_escape or not affinity.fairness_guard:
        raise ContractViolation("affinity must retain bounded-load and fairness escape")
    if not 0.0 <= affinity.wrong_shard_rate_max <= 0.01:
        raise ContractViolation("wrong-shard budget cannot exceed the v1.2 maximum")
    coordinator = parity.coordinator
    if not coordinator.singleflight or not coordinator.exact_action_before_model_call:
        raise ContractViolation("coordinator correctness controls cannot be disabled")
    if not coordinator.unified_attribution:
        raise ContractViolation("coordinator savings must use unified attribution")
    if coordinator.restore_vs_recompute != "cost-aware":
        raise ContractViolation("restore decisions must remain cost-aware")
    if not 1 <= coordinator.max_parallel_probes <= 6:
        raise ContractViolation("coordinator probes cannot exceed the v1.2 bound")

    if parity.rollout_phase in {"observe", "shadow"}:
        serving_requested = (
            (prompt.enabled and prompt.mode == "serve")
            or environment.enabled
            or affinity.enabled
            or coordinator.enabled
        )
        if serving_requested:
            raise ContractViolation(
                "observe/shadow cache parity phases cannot enable serving",
                rollout_phase=parity.rollout_phase,
            )
