"""Deterministic prompt-prefix compilation and provider cache adapters.

This module deliberately keeps provider prefix reuse separate from the Action
Cache.  A provider may avoid processing input tokens; that does not make the
model output deterministic, validated, or publishable.

The public objects have two different representations:

* request objects contain the prompt bytes needed by the provider adapter;
* telemetry objects contain only bounded identifiers, digests, and counters.

There is intentionally no helper that serialises a raw provider request as
telemetry.  That separation makes leaking source or a credential an API misuse
instead of a redaction convention.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .canonical import digest_of, require_digest, sha256_bytes
from .errors import ContractViolation, IdempotencyConflict, Unsupported

PROMPT_SCHEMA_VERSION = "elmos.prompt/v1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}$")


class _ValueEnum(StrEnum):
    pass


class PromptProvider(_ValueEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    SELF_HOSTED = "self-hosted"


class SegmentStability(_ValueEnum):
    STABLE = "stable"
    APPEND_ONLY = "append-only"
    VOLATILE = "volatile"

    @property
    def rank(self) -> int:
        return {
            SegmentStability.STABLE: 0,
            SegmentStability.APPEND_ONLY: 1,
            SegmentStability.VOLATILE: 2,
        }[self]


class CapabilityState(_ValueEnum):
    SUPPORTED = "SUPPORTED"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"


class UsageAccounting(_ValueEnum):
    """How a provider reports its input-token counter.

    ``INCLUSIVE`` means ``input_tokens`` already includes cached tokens.
    ``ADDITIVE`` means cache-read/write counters are outside the base input
    counter and must be added to reconcile the total prompt tokens.
    """

    INCLUSIVE = "INCLUSIVE"
    ADDITIVE = "ADDITIVE"


class ProviderCacheMode(_ValueEnum):
    OBSERVE = "OBSERVE"
    AUTOMATIC = "AUTOMATIC"
    EXPLICIT = "EXPLICIT"
    DISABLED = "DISABLED"


class ProviderCacheReason(_ValueEnum):
    HIT = "HIT"
    COLD_PREFIX = "COLD_PREFIX"
    MODEL_CHANGED = "MODEL_CHANGED"
    EFFORT_CHANGED = "EFFORT_CHANGED"
    TOOL_SCHEMA_CHANGED = "TOOL_SCHEMA_CHANGED"
    PREFIX_CHANGED = "PREFIX_CHANGED"
    TTL_EXPIRED = "TTL_EXPIRED"
    WRONG_REPLICA = "WRONG_REPLICA"
    PROVIDER_UNSUPPORTED = "PROVIDER_UNSUPPORTED"
    PROVIDER_OUTAGE = "PROVIDER_OUTAGE"
    UNKNOWN = "UNKNOWN"


class PromptRequestClass(_ValueEnum):
    CONVERSATIONAL = "CONVERSATIONAL"
    DETERMINISTIC_CONVERSION = "DETERMINISTIC_CONVERSION"
    REPAIR = "REPAIR"
    TEST_GENERATION = "TEST_GENERATION"
    SUMMARIZATION = "SUMMARIZATION"
    ONE_SHOT = "ONE_SHOT"


def _require_identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field} must be a bounded identifier", field=field)
    return value


def _normalise_content(value: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation("prompt segment content must be text")
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


@dataclass(frozen=True)
class PromptIdentity:
    """Every compatibility boundary that can change prefix-cache semantics.

    Tenant and provider account/project identities are supplied as opaque
    digests.  This preserves exact isolation without putting customer names or
    provider account identifiers into logs or routing metadata.
    """

    tenant_scope_digest: str
    provider: PromptProvider
    provider_namespace_digest: str
    model: str
    effort_profile: str
    tool_schema_digest: str
    compatibility_digest: str

    def __post_init__(self) -> None:
        require_digest(self.tenant_scope_digest)
        if not isinstance(self.provider, PromptProvider):
            raise ContractViolation("provider must be a PromptProvider")
        require_digest(self.provider_namespace_digest)
        _require_identifier(self.model, "model")
        _require_identifier(self.effort_profile, "effort_profile")
        require_digest(self.tool_schema_digest)
        require_digest(self.compatibility_digest)

    def document(self) -> dict[str, str]:
        return {
            "tenant_scope_digest": self.tenant_scope_digest,
            "provider": self.provider.value,
            "provider_namespace_digest": self.provider_namespace_digest,
            "model": self.model,
            "effort_profile": self.effort_profile,
            "tool_schema_digest": self.tool_schema_digest,
            "compatibility_digest": self.compatibility_digest,
        }


@dataclass(frozen=True)
class PromptSegment:
    segment_id: str
    stability: SegmentStability
    ordinal: int
    content: str

    def __post_init__(self) -> None:
        _require_identifier(self.segment_id, "segment_id")
        if not isinstance(self.stability, SegmentStability):
            raise ContractViolation("segment stability must use the closed vocabulary")
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise ContractViolation("segment ordinal must be a non-negative integer")
        object.__setattr__(self, "content", _normalise_content(self.content))

    @property
    def content_digest(self) -> str:
        return sha256_bytes(self.content.encode("utf-8"))

    def manifest_entry(self) -> dict[str, Any]:
        raw = self.content.encode("utf-8")
        return {
            "segment_id": self.segment_id,
            "stability": self.stability.value,
            "ordinal": self.ordinal,
            "content_digest": sha256_bytes(raw),
            "content_bytes": len(raw),
        }


def _render(segments: Sequence[PromptSegment]) -> str:
    # The separator is fixed and content line endings are canonical.  Keeping
    # segment IDs out of the wire prompt prevents implementation metadata from
    # changing model behaviour; the manifest still binds every boundary.
    return "\n\n".join(segment.content for segment in segments)


@dataclass(frozen=True)
class CompiledPrompt:
    identity: PromptIdentity
    segments: tuple[PromptSegment, ...]
    stable_count: int
    append_count: int
    stable_prefix_digest: str
    append_prefix_digest: str
    full_prompt_digest: str
    cache_key: str

    @property
    def stable_segments(self) -> tuple[PromptSegment, ...]:
        return self.segments[: self.stable_count]

    @property
    def append_segments(self) -> tuple[PromptSegment, ...]:
        start = self.stable_count
        return self.segments[start : start + self.append_count]

    @property
    def volatile_segments(self) -> tuple[PromptSegment, ...]:
        return self.segments[self.stable_count + self.append_count :]

    @property
    def stable_text(self) -> str:
        return _render(self.stable_segments)

    @property
    def append_text(self) -> str:
        return _render(self.append_segments)

    @property
    def volatile_text(self) -> str:
        return _render(self.volatile_segments)

    @property
    def rendered_text(self) -> str:
        return _render(self.segments)

    def manifest(self) -> dict[str, Any]:
        """Return a content-free, replayable prefix manifest."""

        return {
            "schema_version": PROMPT_SCHEMA_VERSION,
            "identity": self.identity.document(),
            "segments": [segment.manifest_entry() for segment in self.segments],
            "stable_prefix_digest": self.stable_prefix_digest,
            "append_prefix_digest": self.append_prefix_digest,
            "full_prompt_digest": self.full_prompt_digest,
            "cache_key": self.cache_key,
        }

    def telemetry(self) -> dict[str, Any]:
        """Safe prompt metadata: never segment IDs, content, or tenant names."""

        return {
            "schema_version": PROMPT_SCHEMA_VERSION,
            "provider": self.identity.provider.value,
            "model": self.identity.model,
            "effort_profile": self.identity.effort_profile,
            "stable_segments": self.stable_count,
            "append_segments": self.append_count,
            "volatile_segments": len(self.volatile_segments),
            "stable_prefix_digest": self.stable_prefix_digest,
            "full_prompt_digest": self.full_prompt_digest,
            "cache_key": self.cache_key,
        }


class PromptCompiler:
    """Compile named segments into a deterministic stable/append/volatile layout."""

    def compile(
        self,
        identity: PromptIdentity,
        segments: Iterable[PromptSegment],
    ) -> CompiledPrompt:
        supplied = tuple(segments)
        if not supplied:
            raise ContractViolation("a prompt must contain at least one segment")

        ids: set[str] = set()
        positions: set[tuple[SegmentStability, int]] = set()
        for segment in supplied:
            if segment.segment_id in ids:
                raise ContractViolation("duplicate prompt segment ID", segment_id=segment.segment_id)
            position = (segment.stability, segment.ordinal)
            if position in positions:
                raise ContractViolation(
                    "ambiguous prompt segment ordinal",
                    stability=segment.stability.value,
                    ordinal=segment.ordinal,
                )
            ids.add(segment.segment_id)
            positions.add(position)

        ordered = tuple(
            sorted(supplied, key=lambda item: (item.stability.rank, item.ordinal, item.segment_id))
        )
        stable = tuple(item for item in ordered if item.stability is SegmentStability.STABLE)
        append = tuple(item for item in ordered if item.stability is SegmentStability.APPEND_ONLY)
        if not stable:
            raise ContractViolation("a cacheable prompt requires at least one stable segment")

        stable_text = _render(stable)
        append_prefix = _render((*stable, *append))
        full_text = _render(ordered)
        identity_document = identity.document()
        stable_digest = digest_of(
            {
                "schema_version": PROMPT_SCHEMA_VERSION,
                "identity": identity_document,
                "wire_digest": sha256_bytes(stable_text.encode("utf-8")),
                "segments": [item.manifest_entry() for item in stable],
            }
        )
        append_digest = digest_of(
            {
                "stable_prefix_digest": stable_digest,
                "wire_digest": sha256_bytes(append_prefix.encode("utf-8")),
                "segments": [item.manifest_entry() for item in append],
            }
        )
        full_digest = sha256_bytes(full_text.encode("utf-8"))
        cache_key = digest_of(
            {
                "schema_version": PROMPT_SCHEMA_VERSION,
                "identity": identity_document,
                "stable_prefix_digest": stable_digest,
            }
        )
        return CompiledPrompt(
            identity=identity,
            segments=ordered,
            stable_count=len(stable),
            append_count=len(append),
            stable_prefix_digest=stable_digest,
            append_prefix_digest=append_digest,
            full_prompt_digest=full_digest,
            cache_key=cache_key,
        )

    @staticmethod
    def assert_append_only_successor(previous: CompiledPrompt, current: CompiledPrompt) -> None:
        """Prove that a follow-up only appended ledger-like context.

        Volatile task data may change freely.  Stable segments must be exactly
        identical, and every prior append-only segment must remain an exact
        prefix of the new append-only sequence.
        """

        if previous.identity != current.identity:
            raise ContractViolation("prompt identity changed across append-only continuation")
        if previous.stable_segments != current.stable_segments:
            raise ContractViolation("stable prompt segments changed across continuation")
        prefix_length = len(previous.append_segments)
        if current.append_segments[:prefix_length] != previous.append_segments:
            raise ContractViolation("append-only prompt history was rewritten")


@dataclass(frozen=True)
class ProviderCapabilityProfile:
    provider: PromptProvider
    profile_version: str
    state: CapabilityState
    accounting: UsageAccounting
    input_tokens_path: tuple[str, ...]
    output_tokens_path: tuple[str, ...]
    cache_read_tokens_path: tuple[str, ...]
    cache_write_tokens_path: tuple[str, ...] | None
    explicit_breakpoints: bool
    routing_key: bool
    ttl_classes: tuple[str, ...]
    api_contract_version: str = "unpinned"

    def __post_init__(self) -> None:
        if not isinstance(self.provider, PromptProvider):
            raise ContractViolation("capability provider must use the closed vocabulary")
        _require_identifier(self.profile_version, "profile_version")
        if not isinstance(self.state, CapabilityState):
            raise ContractViolation("capability state must use the closed vocabulary")
        if not isinstance(self.accounting, UsageAccounting):
            raise ContractViolation("usage accounting must use the closed vocabulary")
        for name, path in (
            ("input_tokens_path", self.input_tokens_path),
            ("output_tokens_path", self.output_tokens_path),
            ("cache_read_tokens_path", self.cache_read_tokens_path),
        ):
            if not path or any(not _IDENTIFIER.fullmatch(part) for part in path):
                raise ContractViolation(f"{name} must be a non-empty safe field path")
        if self.cache_write_tokens_path is not None and (
            not self.cache_write_tokens_path
            or any(not _IDENTIFIER.fullmatch(part) for part in self.cache_write_tokens_path)
        ):
            raise ContractViolation("cache_write_tokens_path must be a safe field path")
        for ttl_class in self.ttl_classes:
            _require_identifier(ttl_class, "ttl_class")
        _require_identifier(self.api_contract_version, "api_contract_version")

    @property
    def profile_digest(self) -> str:
        return digest_of(self.public_document())

    def public_document(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "profile_version": self.profile_version,
            "state": self.state.value,
            "accounting": self.accounting.value,
            "explicit_breakpoints": self.explicit_breakpoints,
            "routing_key": self.routing_key,
            "ttl_classes": list(self.ttl_classes),
            "api_contract_version": self.api_contract_version,
        }


@dataclass(frozen=True)
class ProviderCachePolicy:
    """Exact, content-free cache kill switches.

    A disabled scope still permits the underlying model request; it merely
    forces ``OBSERVE`` so no provider cache hint, routing key, breakpoint, or
    extended TTL is emitted.  Tenant scopes are represented by their existing
    opaque digest, never a customer identifier.
    """

    enabled: bool = False
    enabled_providers: tuple[PromptProvider, ...] = ()
    disabled_tenant_scope_digests: tuple[str, ...] = ()
    disabled_provider_models: tuple[str, ...] = ()
    disabled_request_classes: tuple[PromptRequestClass, ...] = ()

    def __post_init__(self) -> None:
        if len(set(self.enabled_providers)) != len(self.enabled_providers):
            raise ContractViolation("provider cache policy contains duplicate providers")
        if len(set(self.disabled_request_classes)) != len(self.disabled_request_classes):
            raise ContractViolation("provider cache policy contains duplicate request classes")
        for digest in self.disabled_tenant_scope_digests:
            require_digest(digest)
        for item in self.disabled_provider_models:
            parts = item.split(":", 1)
            if len(parts) != 2:
                raise ContractViolation(
                    "disabled provider/model must use provider:model",
                    value=item,
                )
            try:
                PromptProvider(parts[0])
            except ValueError as exc:
                raise ContractViolation("unknown provider in model kill switch", value=item) from exc
            _require_identifier(parts[1], "disabled_model")

    def cache_allowed(
        self,
        identity: PromptIdentity,
        request_class: PromptRequestClass,
    ) -> tuple[bool, ProviderCacheReason]:
        if not self.enabled:
            return False, ProviderCacheReason.PROVIDER_UNSUPPORTED
        if self.enabled_providers and identity.provider not in self.enabled_providers:
            return False, ProviderCacheReason.PROVIDER_UNSUPPORTED
        if identity.tenant_scope_digest in self.disabled_tenant_scope_digests:
            return False, ProviderCacheReason.PROVIDER_UNSUPPORTED
        if f"{identity.provider.value}:{identity.model}" in self.disabled_provider_models:
            return False, ProviderCacheReason.PROVIDER_UNSUPPORTED
        if request_class in self.disabled_request_classes:
            return False, ProviderCacheReason.PROVIDER_UNSUPPORTED
        return True, ProviderCacheReason.UNKNOWN


class ProviderCircuitBreaker:
    """Deterministic event-count breaker for cache controls only.

    Opening this breaker never blocks the model provider itself.  It disables
    only cache-specific fields until enough independent request opportunities
    have passed, which is safe under clock skew and straightforward to replay.
    """

    def __init__(self, failure_threshold: int = 3, recovery_after_events: int = 10) -> None:
        if failure_threshold < 1 or recovery_after_events < 1:
            raise ContractViolation("provider circuit-breaker bounds must be positive")
        self.failure_threshold = failure_threshold
        self.recovery_after_events = recovery_after_events
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, int] = {}
        self._event = 0

    def allow_cache(self, profile_digest: str) -> bool:
        require_digest(profile_digest)
        self._event += 1
        opened = self._opened_at.get(profile_digest)
        if opened is None:
            return True
        if self._event - opened < self.recovery_after_events:
            return False
        # One half-open cache-hint attempt is allowed.  A later failure opens
        # the breaker again; success clears it.
        del self._opened_at[profile_digest]
        self._failures[profile_digest] = 0
        return True

    def record_success(self, profile_digest: str) -> None:
        require_digest(profile_digest)
        self._failures[profile_digest] = 0
        self._opened_at.pop(profile_digest, None)

    def record_failure(self, profile_digest: str) -> None:
        require_digest(profile_digest)
        failures = self._failures.get(profile_digest, 0) + 1
        self._failures[profile_digest] = failures
        if failures >= self.failure_threshold:
            self._opened_at[profile_digest] = self._event

    def state(self, profile_digest: str) -> str:
        require_digest(profile_digest)
        return "OPEN" if profile_digest in self._opened_at else "CLOSED"


def _counter(payload: Mapping[str, Any], path: tuple[str, ...], label: str) -> int:
    value: Any = payload
    for part in path:
        if not isinstance(value, Mapping) or part not in value:
            raise ContractViolation("provider usage counter is missing", counter=label, path=".".join(path))
        value = value[part]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractViolation("provider usage counter must be a non-negative integer", counter=label)
    return int(value)


@dataclass(frozen=True)
class NormalizedTokenUsage:
    provider: PromptProvider
    total_input_tokens: int
    processed_input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int | None
    accounting: UsageAccounting
    observed_fields: tuple[str, ...]

    @property
    def cache_read_fraction(self) -> float:
        if self.total_input_tokens == 0:
            return 0.0
        return self.cache_read_tokens / self.total_input_tokens

    def telemetry(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "total_input_tokens": self.total_input_tokens,
            "processed_input_tokens": self.processed_input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "accounting": self.accounting.value,
        }


@dataclass(frozen=True)
class ProviderPromptRequest:
    provider: PromptProvider
    model: str
    cache_key: str
    capability_profile: str
    payload: Mapping[str, Any]
    cache_mode: ProviderCacheMode = ProviderCacheMode.AUTOMATIC
    ttl_class: str = "provider-default"

    def telemetry(self) -> dict[str, str]:
        """A deliberately content-free view of the provider request."""

        return {
            "provider": self.provider.value,
            "model": self.model,
            "cache_key": self.cache_key,
            "capability_profile": self.capability_profile,
            "cache_mode": self.cache_mode.value,
            "ttl_class": self.ttl_class,
        }


@dataclass(frozen=True)
class PromptCacheObservation:
    """Content-free attribution for one provider request/response pair."""

    observation_id: str
    request_id: str
    provider_namespace_digest: str
    stable_prefix_digest: str
    cache_key: str
    provider: PromptProvider
    model: str
    effort_profile: str
    capability_profile_digest: str
    cache_mode: ProviderCacheMode
    ttl_class: str
    reason: ProviderCacheReason
    usage: NormalizedTokenUsage

    def __post_init__(self) -> None:
        for value in (
            self.observation_id,
            self.request_id,
            self.provider_namespace_digest,
            self.stable_prefix_digest,
            self.cache_key,
            self.capability_profile_digest,
        ):
            require_digest(value)
        if self.usage.provider is not self.provider:
            raise ContractViolation("provider cache observation usage/provider mismatch")
        _require_identifier(self.model, "model")
        _require_identifier(self.effort_profile, "effort_profile")
        _require_identifier(self.ttl_class, "ttl_class")
        if self.reason is ProviderCacheReason.HIT and self.usage.cache_read_tokens <= 0:
            raise ContractViolation("a provider cache hit requires positive cache-read tokens")
        if self.reason is not ProviderCacheReason.HIT and self.usage.cache_read_tokens > 0:
            raise ContractViolation("positive cache-read tokens must be attributed as a hit")

    def telemetry(self) -> dict[str, Any]:
        return {
            "schema_version": "1.2.0",
            "observation_id": self.observation_id,
            "request_id": self.request_id,
            "provider_namespace_digest": self.provider_namespace_digest,
            "stable_prefix_digest": self.stable_prefix_digest,
            "cache_key": self.cache_key,
            "provider": self.provider.value,
            "model": self.model,
            "effort_profile": self.effort_profile,
            "capability_profile_digest": self.capability_profile_digest,
            "cache_mode": self.cache_mode.value,
            "ttl_class": self.ttl_class,
            "reason": self.reason.value,
            "usage": self.usage.telemetry(),
        }


class RetryAccountingLedger:
    """Deduplicate provider usage by the caller's stable request identity."""

    def __init__(self) -> None:
        self._observations: dict[str, PromptCacheObservation] = {}

    def record(self, observation: PromptCacheObservation) -> bool:
        existing = self._observations.get(observation.request_id)
        if existing is None:
            self._observations[observation.request_id] = observation
            return True
        if existing.telemetry() != observation.telemetry():
            raise IdempotencyConflict(
                "provider retry changed the cache observation",
                request_id=observation.request_id,
            )
        return False

    def totals(self) -> dict[str, int]:
        observations = tuple(self._observations.values())
        return {
            "requests": len(observations),
            "total_input_tokens": sum(item.usage.total_input_tokens for item in observations),
            "processed_input_tokens": sum(
                item.usage.processed_input_tokens for item in observations
            ),
            "output_tokens": sum(item.usage.output_tokens for item in observations),
            "cache_read_tokens": sum(item.usage.cache_read_tokens for item in observations),
            "cache_write_tokens": sum(
                item.usage.cache_write_tokens or 0 for item in observations
            ),
        }


class ProviderPromptCacheAdapter:
    """Provider-specific request mapping with one strict usage contract."""

    def __init__(self, profile: ProviderCapabilityProfile) -> None:
        self.profile = profile

    def _ensure_available(self, cache_mode: ProviderCacheMode) -> None:
        if cache_mode is ProviderCacheMode.OBSERVE:
            return
        if self.profile.state is CapabilityState.DISABLED:
            raise Unsupported("provider prompt cache profile is disabled", provider=self.profile.provider.value)
        if self.profile.state is CapabilityState.DEGRADED:
            raise Unsupported(
                "degraded provider cache profile permits observe mode only",
                provider=self.profile.provider.value,
            )

    def build_request(
        self,
        prompt: CompiledPrompt,
        *,
        cache_mode: ProviderCacheMode | None = None,
        ttl_class: str | None = None,
    ) -> ProviderPromptRequest:
        if prompt.identity.provider is not self.profile.provider:
            raise ContractViolation(
                "prompt/provider adapter mismatch",
                prompt_provider=prompt.identity.provider.value,
                adapter_provider=self.profile.provider.value,
            )
        mode = cache_mode or (
            ProviderCacheMode.EXPLICIT
            if self.profile.explicit_breakpoints
            else ProviderCacheMode.AUTOMATIC
        )
        self._ensure_available(mode)
        if mode is ProviderCacheMode.DISABLED:
            raise Unsupported("provider prompt cache request is disabled")
        selected_ttl = ttl_class or self.profile.ttl_classes[0]
        if selected_ttl not in self.profile.ttl_classes:
            raise Unsupported(
                "provider prompt cache TTL class is not supported",
                provider=self.profile.provider.value,
                ttl_class=selected_ttl,
            )
        if mode is ProviderCacheMode.EXPLICIT and not self.profile.explicit_breakpoints:
            raise Unsupported(
                "provider profile does not support explicit cache breakpoints",
                provider=self.profile.provider.value,
            )
        payload = self._payload(prompt, mode, selected_ttl)
        return ProviderPromptRequest(
            provider=self.profile.provider,
            model=prompt.identity.model,
            cache_key=prompt.cache_key,
            capability_profile=self.profile.profile_version,
            payload=payload,
            cache_mode=mode,
            ttl_class=selected_ttl,
        )

    def _payload(
        self,
        prompt: CompiledPrompt,
        cache_mode: ProviderCacheMode,
        ttl_class: str,
    ) -> Mapping[str, Any]:
        # The base adapter is a fail-closed SPI, not a partially functional
        # provider.  A profile without an exact request mapper must degrade to
        # no-cache instead of surfacing a Python implementation stub at run
        # time or accidentally emitting a generic provider request.
        raise Unsupported(
            "provider prompt cache request mapping is unavailable",
            provider=self.profile.provider.value,
            capability_profile=self.profile.profile_version,
        )

    def observation(
        self,
        *,
        prompt: CompiledPrompt,
        request: ProviderPromptRequest,
        usage: NormalizedTokenUsage,
        reason: ProviderCacheReason,
        request_id: str,
    ) -> PromptCacheObservation:
        require_digest(request_id)
        if request.provider is not self.profile.provider or request.cache_key != prompt.cache_key:
            raise ContractViolation("provider observation request does not match the compiled prompt")
        body = {
            "request_id": request_id,
            "cache_key": request.cache_key,
            "profile_digest": self.profile.profile_digest,
            "usage": usage.telemetry(),
            "reason": reason.value,
        }
        return PromptCacheObservation(
            observation_id=digest_of(body),
            request_id=request_id,
            provider_namespace_digest=prompt.identity.provider_namespace_digest,
            stable_prefix_digest=prompt.stable_prefix_digest,
            cache_key=prompt.cache_key,
            provider=self.profile.provider,
            model=prompt.identity.model,
            effort_profile=prompt.identity.effort_profile,
            capability_profile_digest=self.profile.profile_digest,
            cache_mode=request.cache_mode,
            ttl_class=request.ttl_class,
            reason=reason,
            usage=usage,
        )

    def normalize_usage(self, payload: Mapping[str, Any]) -> NormalizedTokenUsage:
        # Usage remains useful in observe/degraded mode, but a fully disabled
        # profile is not an asserted response contract.
        if self.profile.state is CapabilityState.DISABLED:
            raise Unsupported(
                "provider usage contract is disabled",
                provider=self.profile.provider.value,
            )
        profile = self.profile
        base_input = _counter(payload, profile.input_tokens_path, "input_tokens")
        output = _counter(payload, profile.output_tokens_path, "output_tokens")
        cache_read = _counter(payload, profile.cache_read_tokens_path, "cache_read_tokens")
        cache_write = (
            None
            if profile.cache_write_tokens_path is None
            else _counter(payload, profile.cache_write_tokens_path, "cache_write_tokens")
        )
        paths = [
            ".".join(profile.input_tokens_path),
            ".".join(profile.output_tokens_path),
            ".".join(profile.cache_read_tokens_path),
        ]
        if profile.cache_write_tokens_path is not None:
            paths.append(".".join(profile.cache_write_tokens_path))

        if profile.accounting is UsageAccounting.INCLUSIVE:
            if cache_read > base_input:
                raise ContractViolation(
                    "cached tokens exceed inclusive input tokens",
                    provider=profile.provider.value,
                )
            total_input = base_input
            processed = base_input - cache_read
        else:
            if cache_write is None:
                raise ContractViolation("additive accounting requires an explicit cache-write counter")
            total_input = base_input + cache_read + cache_write
            processed = base_input + cache_write

        return NormalizedTokenUsage(
            provider=profile.provider,
            total_input_tokens=total_input,
            processed_input_tokens=processed,
            output_tokens=output,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            accounting=profile.accounting,
            observed_fields=tuple(paths),
        )


class OpenAIPromptCacheAdapter(ProviderPromptCacheAdapter):
    def _payload(
        self,
        prompt: CompiledPrompt,
        cache_mode: ProviderCacheMode,
        ttl_class: str,
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {
            "model": prompt.identity.model,
            "input": prompt.rendered_text,
            "reasoning": {"effort": prompt.identity.effort_profile},
        }
        if cache_mode is not ProviderCacheMode.OBSERVE:
            payload["prompt_cache_key"] = prompt.cache_key
            if ttl_class == "24h":
                payload["prompt_cache_retention"] = "24h"
        return payload


class AnthropicPromptCacheAdapter(ProviderPromptCacheAdapter):
    def _payload(
        self,
        prompt: CompiledPrompt,
        cache_mode: ProviderCacheMode,
        ttl_class: str,
    ) -> Mapping[str, Any]:
        stable_block: dict[str, Any] = {"type": "text", "text": prompt.stable_text}
        if cache_mode is ProviderCacheMode.EXPLICIT:
            cache_control: dict[str, str] = {"type": "ephemeral"}
            if ttl_class == "1h":
                cache_control["ttl"] = "1h"
            stable_block["cache_control"] = cache_control
        blocks: list[dict[str, Any]] = [stable_block]
        remainder = _render((*prompt.append_segments, *prompt.volatile_segments))
        if remainder:
            blocks.append({"type": "text", "text": remainder})
        return {
            "model": prompt.identity.model,
            "messages": [{"role": "user", "content": blocks}],
        }


@dataclass(frozen=True)
class SelfHostedRuntimeProfile:
    """Exact compatibility and inventory boundary for a prefix-KV replica."""

    replica_id_digest: str
    tokenizer_digest: str
    model_build_digest: str
    block_hash_version: str
    eviction_epoch: int
    resident_prefix_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value in (
            self.replica_id_digest,
            self.tokenizer_digest,
            self.model_build_digest,
            *self.resident_prefix_digests,
        ):
            require_digest(value)
        _require_identifier(self.block_hash_version, "block_hash_version")
        if self.eviction_epoch < 0:
            raise ContractViolation("self-hosted eviction epoch cannot be negative")
        if len(set(self.resident_prefix_digests)) != len(self.resident_prefix_digests):
            raise ContractViolation("self-hosted prefix inventory contains duplicates")

    @property
    def compatibility_digest(self) -> str:
        return digest_of(
            {
                "tokenizer_digest": self.tokenizer_digest,
                "model_build_digest": self.model_build_digest,
                "block_hash_version": self.block_hash_version,
            }
        )

    def contains(self, prefix_digest: str) -> bool:
        require_digest(prefix_digest)
        return prefix_digest in self.resident_prefix_digests


class SelfHostedPromptCacheAdapter(ProviderPromptCacheAdapter):
    def __init__(
        self,
        profile: ProviderCapabilityProfile,
        runtime: SelfHostedRuntimeProfile | None = None,
    ) -> None:
        super().__init__(profile)
        self.runtime = runtime

    def _payload(
        self,
        prompt: CompiledPrompt,
        cache_mode: ProviderCacheMode,
        ttl_class: str,
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {
            "model": prompt.identity.model,
            "prompt": prompt.rendered_text,
            "effort_profile": prompt.identity.effort_profile,
        }
        if cache_mode is not ProviderCacheMode.OBSERVE:
            if self.runtime is None:
                raise Unsupported("self-hosted prefix cache has no pinned runtime profile")
            if prompt.identity.compatibility_digest != self.runtime.compatibility_digest:
                raise ContractViolation(
                    "self-hosted prompt compatibility does not match the runtime profile"
                )
            payload["prefix_digest"] = prompt.stable_prefix_digest
            payload["prefix_cache_key"] = prompt.cache_key
            payload["prefix_cache_ttl_class"] = ttl_class
            payload["prefix_cache_runtime"] = {
                "replica_id_digest": self.runtime.replica_id_digest,
                "tokenizer_digest": self.runtime.tokenizer_digest,
                "model_build_digest": self.runtime.model_build_digest,
                "block_hash_version": self.runtime.block_hash_version,
                "eviction_epoch": self.runtime.eviction_epoch,
                "prefix_resident": self.runtime.contains(prompt.stable_prefix_digest),
            }
        return payload


class ProviderAdapterRegistry:
    """Versioned, explicit provider capability registry.

    Unknown providers do not inherit a permissive default.  Registering the
    same provider twice also fails unless the caller explicitly replaces it.
    """

    def __init__(self, adapters: Iterable[ProviderPromptCacheAdapter] = ()) -> None:
        self._adapters: dict[PromptProvider, ProviderPromptCacheAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ProviderPromptCacheAdapter, *, replace: bool = False) -> None:
        provider = adapter.profile.provider
        if provider in self._adapters and not replace:
            raise ContractViolation("provider adapter is already registered", provider=provider.value)
        self._adapters[provider] = adapter

    def adapter(self, provider: PromptProvider) -> ProviderPromptCacheAdapter:
        try:
            return self._adapters[provider]
        except KeyError as exc:
            raise Unsupported("provider prompt cache is not registered", provider=provider.value) from exc

    def capabilities(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            self._adapters[provider].profile.public_document()
            for provider in sorted(self._adapters, key=lambda item: item.value)
        )

    @classmethod
    def defaults(cls) -> ProviderAdapterRegistry:
        openai = ProviderCapabilityProfile(
            provider=PromptProvider.OPENAI,
            profile_version="openai-prefix-v1",
            state=CapabilityState.SUPPORTED,
            accounting=UsageAccounting.INCLUSIVE,
            input_tokens_path=("usage", "input_tokens"),
            output_tokens_path=("usage", "output_tokens"),
            cache_read_tokens_path=("usage", "input_tokens_details", "cached_tokens"),
            cache_write_tokens_path=None,
            explicit_breakpoints=False,
            routing_key=True,
            ttl_classes=("provider-default", "24h"),
            api_contract_version="openai-responses-2026-08-20",
        )
        anthropic = ProviderCapabilityProfile(
            provider=PromptProvider.ANTHROPIC,
            profile_version="anthropic-prefix-v1",
            state=CapabilityState.SUPPORTED,
            accounting=UsageAccounting.ADDITIVE,
            input_tokens_path=("usage", "input_tokens"),
            output_tokens_path=("usage", "output_tokens"),
            cache_read_tokens_path=("usage", "cache_read_input_tokens"),
            cache_write_tokens_path=("usage", "cache_creation_input_tokens"),
            explicit_breakpoints=True,
            routing_key=False,
            ttl_classes=("5m", "1h"),
            api_contract_version="anthropic-messages-package-v1.2",
        )
        self_hosted = ProviderCapabilityProfile(
            provider=PromptProvider.SELF_HOSTED,
            profile_version="self-hosted-prefix-kv-v1",
            # No replica/tokenizer/model-build identity can be inferred from
            # the repository.  The generic adapter is therefore observe-only
            # until a deployment registers an exact runtime profile.
            state=CapabilityState.DEGRADED,
            accounting=UsageAccounting.INCLUSIVE,
            input_tokens_path=("usage", "input_tokens"),
            output_tokens_path=("usage", "output_tokens"),
            cache_read_tokens_path=("usage", "prefix_cache_hit_tokens"),
            cache_write_tokens_path=("usage", "prefix_cache_write_tokens"),
            explicit_breakpoints=True,
            routing_key=True,
            ttl_classes=("runtime-default",),
            api_contract_version="elmos-prefix-kv-1",
        )
        return cls(
            (
                OpenAIPromptCacheAdapter(openai),
                AnthropicPromptCacheAdapter(anthropic),
                SelfHostedPromptCacheAdapter(self_hosted),
            )
        )


class PromptCacheController:
    """Resolve policy/profile/health into one safe provider request mode."""

    def __init__(
        self,
        registry: ProviderAdapterRegistry,
        policy: ProviderCachePolicy | None = None,
        circuit_breaker: ProviderCircuitBreaker | None = None,
    ) -> None:
        self.registry = registry
        self.policy = policy or ProviderCachePolicy()
        self.circuit_breaker = circuit_breaker or ProviderCircuitBreaker()

    def prepare(
        self,
        prompt: CompiledPrompt,
        request_class: PromptRequestClass,
        *,
        cache_mode: ProviderCacheMode | None = None,
        ttl_class: str | None = None,
    ) -> tuple[ProviderPromptRequest, ProviderCacheReason]:
        adapter = self.registry.adapter(prompt.identity.provider)
        allowed, reason = self.policy.cache_allowed(prompt.identity, request_class)
        profile_digest = adapter.profile.profile_digest
        if adapter.profile.state is not CapabilityState.SUPPORTED:
            allowed = False
            reason = ProviderCacheReason.PROVIDER_UNSUPPORTED
        elif allowed and not self.circuit_breaker.allow_cache(profile_digest):
            allowed = False
            reason = ProviderCacheReason.PROVIDER_OUTAGE

        if not allowed:
            return (
                adapter.build_request(
                    prompt,
                    cache_mode=ProviderCacheMode.OBSERVE,
                    ttl_class=adapter.profile.ttl_classes[0],
                ),
                reason,
            )
        try:
            request = adapter.build_request(
                prompt,
                cache_mode=cache_mode,
                ttl_class=ttl_class,
            )
        except Unsupported:
            # An unavailable optional cache control must never make the model
            # call unavailable.  Ordinary observe-mode request construction is
            # the deterministic clean fallback.
            return (
                adapter.build_request(
                    prompt,
                    cache_mode=ProviderCacheMode.OBSERVE,
                    ttl_class=adapter.profile.ttl_classes[0],
                ),
                ProviderCacheReason.PROVIDER_UNSUPPORTED,
            )
        return request, ProviderCacheReason.UNKNOWN

    def record_provider_success(self, provider: PromptProvider) -> None:
        adapter = self.registry.adapter(provider)
        self.circuit_breaker.record_success(adapter.profile.profile_digest)

    def record_provider_failure(self, provider: PromptProvider) -> None:
        adapter = self.registry.adapter(provider)
        self.circuit_breaker.record_failure(adapter.profile.profile_digest)
