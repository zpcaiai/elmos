"""Layered cache fabric: complete keys, verified hits, explained admissions.

A cache in an autonomous repository agent is not a performance feature, it is a
correctness surface.  A *false hit* — returning a value computed under some
other snapshot, policy, prompt prefix or model — is indistinguishable at the
call site from a correct answer, so it does not fail loudly, it fails silently
and forever.  Everything in this module is arranged around making that outcome
structurally impossible rather than statistically unlikely.

Three rules carry the weight.  First, a key is complete or it does not exist:
:class:`CacheKeyParts` requires all nine parts and :func:`build_key` raises
``CACHE_KEY_INCOMPLETE`` rather than hashing whatever it was given, because a
key that omits ``policy_hash`` is a key that survives a policy change.  Second,
a hit is *verified*: the layer stores the key parts alongside the value, and a
lookup re-compares them before returning, so a corrupted entry or a fingerprint
collision surfaces as ``CACHE_ENTRY_INVALID`` or ``STALE_CACHE_USED`` and never
as a hit.  Third, admission is a decision with a stated reason: a result that is
too cheap to be worth caching, too large to store, or not reproducible is
refused at the door, and a retryable failure is never negatively cached at all —
caching "this failed" when the failure was transient converts a blip into a
permanent outage.

Tenancy is part of the key and is re-checked on every read.  Nothing here is
allowed to serve one tenant's bytes to another, and a mismatch is an
``ISOLATION_VIOLATION``, not a miss.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from .contracts import (
    canonical_json,
    digest,
    format_timestamp,
    parse_timestamp,
    reject_unknown_fields,
    require_bool,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .ports import ArtifactStore, Clock, EventStore, KeyValueStore
from .registry import register

__all__ = [
    "AdmissionDecision",
    "AdmissionPolicy",
    "AdmissionReason",
    "ArtifactLayer",
    "CacheClass",
    "CacheEntry",
    "CacheFabric",
    "CacheKey",
    "CacheKeyParts",
    "CacheLayer",
    "CacheMetrics",
    "Candidate",
    "DependencyGraph",
    "InProcessLayer",
    "InvalidationSet",
    "KeyValueLayer",
    "Layer",
    "LayerCounters",
    "LookupOutcome",
    "LookupReason",
    "LookupResult",
    "Operation",
    "REQUIRED_KEY_PARTS",
    "bind_fabric",
    "bound_fabric",
    "build_key",
    "handle",
    "record_admission",
]

register_codes(
    Category.INPUT,
    "CACHE_KEY_INCOMPLETE",
)
register_codes(
    Category.INTEGRITY,
    "CACHE_POISONED",
    "CACHE_ENTRY_INVALID",
    "STALE_CACHE_USED",
)
register_codes(
    Category.POLICY,
    "ISOLATION_VIOLATION",
    "CACHE_ADMISSION_REJECTED",
)
register_codes(
    Category.SEMANTIC,
    "CACHE_LAYER_UNKNOWN",
    "CACHE_UNCONFIGURED",
)

#: The nine parts that together identify "the same computation".  Dropping any
#: one of them makes a class of changes invisible to the key, and the resulting
#: hit is wrong rather than slow.  ``prompt_prefix_digest`` and
#: ``environment_fingerprint`` are the two that implementations forget: the
#: first makes a reordered system prompt reuse the old answer, the second makes
#: a toolchain upgrade reuse the old build.
REQUIRED_KEY_PARTS: tuple[str, ...] = (
    "repo_snapshot_sha",
    "task_spec_hash",
    "workflow_version",
    "skill_versions",
    "policy_hash",
    "tool_schema_versions",
    "model_profile",
    "prompt_prefix_digest",
    "environment_fingerprint",
)

_PART_FIELD_NAMES: Mapping[str, str] = {
    "repo_snapshot_sha": "repoSnapshotSha",
    "task_spec_hash": "taskSpecHash",
    "workflow_version": "workflowVersion",
    "skill_versions": "skillVersions",
    "policy_hash": "policyHash",
    "tool_schema_versions": "toolSchemaVersions",
    "model_profile": "modelProfile",
    "prompt_prefix_digest": "promptPrefixDigest",
    "environment_fingerprint": "environmentFingerprint",
}

_ENTRY_SCHEMA = "elmos.cache.entry/1"


class CacheClass(StrEnum):
    """What kind of reuse an entry claims to be safe for.

    The class is part of the key, so an entry can never be read back under a
    different set of reuse rules than it was written under.  ``SECRET_BOUND``
    exists only so that it can be refused: a value whose correctness depends on
    a short-lived secret binding is never served from a cache, because the
    binding it depended on is gone by the time the cache is read.
    """

    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"
    TIME_BOUND = "time-bound"
    ENVIRONMENT_BOUND = "environment-bound"
    SECRET_BOUND = "secret-bound"  # noqa: S105 - a control/verdict name, not a credential


class Layer(StrEnum):
    """Storage tiers, fastest first.

    ``L1`` is process-local and dies with the process, ``L2`` is the shared
    key/value store, ``L3`` is content-addressed artifact storage.  A lookup
    walks them in this order and promotes a hit upwards; a write goes to every
    writable layer so that a process restart does not silently halve the hit
    rate.
    """

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class LookupOutcome(StrEnum):
    """Every lookup ends in exactly one of these, and says why.

    ``BYPASS`` is deliberately not a ``MISS``: a miss means "we looked and it
    was not there" (so admitting the computed value is useful), a bypass means
    "we were not allowed to look" (so admitting it would be wrong).  Collapsing
    them makes the hit rate look bad and the safety story look fine, which is
    exactly backwards.
    """

    HIT = "HIT"
    MISS = "MISS"
    BYPASS = "BYPASS"


class LookupReason(StrEnum):
    """The single reason attached to a lookup outcome."""

    FRESH_HIT = "FRESH_HIT"
    NEGATIVE_HIT = "NEGATIVE_HIT"
    ABSENT = "ABSENT"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    SECRET_BOUND_CLASS = "SECRET_BOUND_CLASS"  # noqa: S105 - a control/verdict name, not a credential
    SIDE_EFFECTING_OPERATION = "SIDE_EFFECTING_OPERATION"
    CLASS_NOT_CACHEABLE = "CLASS_NOT_CACHEABLE"
    NO_LAYERS_CONFIGURED = "NO_LAYERS_CONFIGURED"


class AdmissionReason(StrEnum):
    """Why a candidate was or was not written.

    Refusals are enumerated rather than free text so that "why is my hit rate
    zero" is answerable from metrics alone.
    """

    ADMITTED = "ADMITTED"
    BELOW_MIN_COMPUTE_COST = "BELOW_MIN_COMPUTE_COST"
    ABOVE_MAX_SIZE = "ABOVE_MAX_SIZE"
    NONDETERMINISTIC_RESULT = "NONDETERMINISTIC_RESULT"
    COMPUTE_COST_UNMEASURED = "COMPUTE_COST_UNMEASURED"
    RETRYABLE_FAILURE_NOT_CACHEABLE = "RETRYABLE_FAILURE_NOT_CACHEABLE"
    NEGATIVE_TTL_REQUIRED = "NEGATIVE_TTL_REQUIRED"
    CLASS_NOT_CACHEABLE = "CLASS_NOT_CACHEABLE"
    SECRET_BOUND_CLASS = "SECRET_BOUND_CLASS"  # noqa: S105 - a control/verdict name, not a credential
    SIDE_EFFECTING_OPERATION = "SIDE_EFFECTING_OPERATION"


# --- keys --------------------------------------------------------------------


def _normalise_version_map(value: Any, field_name: str) -> tuple[tuple[str, str], ...]:
    """Decode a name -> version mapping into a sorted, hashable tuple.

    Mapping iteration order is not a stable identity, so the pairs are sorted
    once here.  An empty map is refused: "no skills" and "we forgot to pass the
    skill versions" are the same bytes otherwise.
    """

    mapping = require_mapping(value, field_name)
    if not mapping:
        raise KernelError(
            code="CACHE_KEY_INCOMPLETE",
            message=f"{field_name} is empty; an empty version map cannot identify a computation",
            recommended_action=f"send every component and version in {field_name}",
            details={"part": field_name},
        )
    pairs = tuple(
        (require_str(name, f"{field_name}.name", max_length=256),
         require_str(mapping[name], f"{field_name}[{name}]", max_length=256))
        for name in sorted(mapping)
    )
    return pairs


@dataclass(frozen=True, slots=True)
class CacheKeyParts:
    """The nine-part identity of a computation.

    Every field is mandatory and every field is non-empty.  There is no
    ``Optional`` here on purpose: an optional key part is a key part that a
    caller will eventually omit, and the resulting collision is invisible.
    """

    repo_snapshot_sha: str
    task_spec_hash: str
    workflow_version: str
    skill_versions: tuple[tuple[str, str], ...]
    policy_hash: str
    tool_schema_versions: tuple[tuple[str, str], ...]
    model_profile: str
    prompt_prefix_digest: str
    environment_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("repo_snapshot_sha", "task_spec_hash", "workflow_version",
                     "policy_hash", "model_profile", "prompt_prefix_digest",
                     "environment_fingerprint"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise KernelError(
                    code="CACHE_KEY_INCOMPLETE",
                    message=f"cache key part {name!r} is empty",
                    recommended_action="supply every part in cache.REQUIRED_KEY_PARTS",
                    details={"part": name, "required": list(REQUIRED_KEY_PARTS)},
                )
        for name in ("skill_versions", "tool_schema_versions"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or not value:
                raise KernelError(
                    code="CACHE_KEY_INCOMPLETE",
                    message=f"cache key part {name!r} is empty",
                    recommended_action="supply every part in cache.REQUIRED_KEY_PARTS",
                    details={"part": name, "required": list(REQUIRED_KEY_PARTS)},
                )

    def to_payload(self) -> dict[str, Any]:
        return {
            "repoSnapshotSha": self.repo_snapshot_sha,
            "taskSpecHash": self.task_spec_hash,
            "workflowVersion": self.workflow_version,
            "skillVersions": [[name, version] for name, version in self.skill_versions],
            "policyHash": self.policy_hash,
            "toolSchemaVersions": [[name, version]
                                   for name, version in self.tool_schema_versions],
            "modelProfile": self.model_profile,
            "promptPrefixDigest": self.prompt_prefix_digest,
            "environmentFingerprint": self.environment_fingerprint,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> CacheKeyParts:
        """Rebuild parts from a stored envelope, refusing anything unfamiliar."""

        reject_unknown_fields(payload, set(_PART_FIELD_NAMES.values()),
                              field_name="cache key parts")
        missing = [wire for wire in _PART_FIELD_NAMES.values() if payload.get(wire) is None]
        if missing:
            raise KernelError(
                code="CACHE_ENTRY_INVALID",
                message=f"stored cache key is missing parts: {sorted(missing)}",
                recommended_action="evict the entry; a partial key cannot be verified",
                details={"missing": sorted(missing)},
            )
        return cls(
            repo_snapshot_sha=require_str(payload["repoSnapshotSha"], "repoSnapshotSha"),
            task_spec_hash=require_str(payload["taskSpecHash"], "taskSpecHash"),
            workflow_version=require_str(payload["workflowVersion"], "workflowVersion"),
            skill_versions=tuple(
                (require_str(pair[0], "skillVersions.name"),
                 require_str(pair[1], "skillVersions.version"))
                for pair in payload["skillVersions"]
            ),
            policy_hash=require_str(payload["policyHash"], "policyHash"),
            tool_schema_versions=tuple(
                (require_str(pair[0], "toolSchemaVersions.name"),
                 require_str(pair[1], "toolSchemaVersions.version"))
                for pair in payload["toolSchemaVersions"]
            ),
            model_profile=require_str(payload["modelProfile"], "modelProfile"),
            prompt_prefix_digest=require_str(payload["promptPrefixDigest"], "promptPrefixDigest"),
            environment_fingerprint=require_str(payload["environmentFingerprint"],
                                                "environmentFingerprint"),
        )


@dataclass(frozen=True, slots=True)
class CacheKey:
    """A tenant-scoped, class-scoped, complete cache key."""

    tenant_id: str
    namespace: str
    cache_class: CacheClass
    parts: CacheKeyParts

    def __post_init__(self) -> None:
        require_identifier(self.tenant_id, "cache_key.tenant_id")
        require_identifier(self.namespace, "cache_key.namespace")
        if not isinstance(self.cache_class, CacheClass):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown cache class {self.cache_class!r}",
                recommended_action=f"use one of {sorted(item.value for item in CacheClass)}",
            )

    @property
    def fingerprint(self) -> str:
        """Content address of the whole key, tenant and class included."""

        return digest(self.to_payload())

    def to_payload(self) -> dict[str, Any]:
        return {
            "tenantId": self.tenant_id,
            "namespace": self.namespace,
            "cacheClass": str(self.cache_class),
            "parts": self.parts.to_payload(),
        }


def build_key(parts: Mapping[str, Any], *, tenant_id: str, namespace: str,
              cache_class: CacheClass) -> CacheKey:
    """Build a complete cache key or refuse to build one at all.

    ``CACHE_KEY_INCOMPLETE`` names every missing part.  The alternative —
    hashing the subset that happened to arrive — produces a key that is stable,
    plausible and wrong, and there is no downstream check that can detect it.
    """

    supplied = require_mapping(parts, "cache_key_inputs")
    missing = [name for name in REQUIRED_KEY_PARTS
               if supplied.get(name) is None and supplied.get(_PART_FIELD_NAMES[name]) is None]
    if missing:
        raise KernelError(
            code="CACHE_KEY_INCOMPLETE",
            message=f"cache key is missing required parts: {sorted(missing)}",
            retryable=False,
            recommended_action="supply every part in cache.REQUIRED_KEY_PARTS before hashing",
            details={"missing": sorted(missing), "required": list(REQUIRED_KEY_PARTS)},
        )
    unknown = sorted(
        set(supplied) - set(REQUIRED_KEY_PARTS) - set(_PART_FIELD_NAMES.values())
    )
    if unknown:
        raise KernelError(
            code="UNKNOWN_FIELD",
            message=f"cache_key_inputs contains unsupported parts: {unknown}",
            recommended_action="remove the fields; an unrecognised part is never hashed",
            details={"unknown": unknown, "supported": list(REQUIRED_KEY_PARTS)},
        )

    def pick(name: str) -> Any:
        value = supplied.get(name)
        return supplied.get(_PART_FIELD_NAMES[name]) if value is None else value

    return CacheKey(
        tenant_id=tenant_id,
        namespace=namespace,
        cache_class=cache_class,
        parts=CacheKeyParts(
            repo_snapshot_sha=require_str(pick("repo_snapshot_sha"), "repo_snapshot_sha",
                                          max_length=256),
            task_spec_hash=require_str(pick("task_spec_hash"), "task_spec_hash", max_length=256),
            workflow_version=require_str(pick("workflow_version"), "workflow_version",
                                         max_length=256),
            skill_versions=_normalise_version_map(pick("skill_versions"), "skill_versions"),
            policy_hash=require_str(pick("policy_hash"), "policy_hash", max_length=256),
            tool_schema_versions=_normalise_version_map(pick("tool_schema_versions"),
                                                        "tool_schema_versions"),
            model_profile=require_str(pick("model_profile"), "model_profile", max_length=256),
            prompt_prefix_digest=require_str(pick("prompt_prefix_digest"), "prompt_prefix_digest",
                                             max_length=256),
            environment_fingerprint=require_str(pick("environment_fingerprint"),
                                                "environment_fingerprint", max_length=256),
        ),
    )


# --- entries -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """A stored value together with the key it was stored under.

    Storing the key parts *inside* the entry is the whole trick.  A fingerprint
    is a lossy summary; a hit that only checks the fingerprint trusts the hash,
    the index and every byte in between.  Re-comparing the parts turns a
    collision or a corrupted index from a wrong answer into a raised error.
    """

    key_fingerprint: str
    tenant_id: str
    namespace: str
    cache_class: CacheClass
    parts: CacheKeyParts
    negative: bool
    value: Any
    value_digest: str | None
    failure_code: str | None
    stored_at: datetime
    expires_at: datetime | None
    byte_count: int
    compute_cost_ms: int
    depends_on: tuple[str, ...]
    producer_id: str

    def __post_init__(self) -> None:
        require_int(self.byte_count, "cache_entry.byte_count", minimum=0)
        require_int(self.compute_cost_ms, "cache_entry.compute_cost_ms", minimum=0)
        if self.negative:
            if self.expires_at is None:
                raise KernelError(
                    code="CACHE_ENTRY_INVALID",
                    message="a negative cache entry without an expiry is a permanent outage",
                    recommended_action="give every negative entry a bounded ttl",
                )
            if not self.failure_code:
                raise KernelError(
                    code="CACHE_ENTRY_INVALID",
                    message="a negative cache entry must name the failure code it caches",
                    recommended_action="record the stable failure code with the entry",
                )
        elif self.value_digest is None:
            raise KernelError(
                code="CACHE_ENTRY_INVALID",
                message="a positive cache entry must carry the digest of its value",
                recommended_action="store digest(value) alongside the value",
            )

    def is_expired(self, now: datetime) -> bool:
        """Expiry is inclusive: an entry expiring exactly now is already gone."""

        return self.expires_at is not None and self.expires_at <= now

    def to_envelope(self) -> dict[str, Any]:
        return {
            "schema": _ENTRY_SCHEMA,
            "keyFingerprint": self.key_fingerprint,
            "tenantId": self.tenant_id,
            "namespace": self.namespace,
            "cacheClass": str(self.cache_class),
            "keyParts": self.parts.to_payload(),
            "negative": self.negative,
            "value": self.value,
            "valueDigest": self.value_digest,
            "failureCode": self.failure_code,
            "storedAt": format_timestamp(self.stored_at),
            "expiresAt": None if self.expires_at is None else format_timestamp(self.expires_at),
            "byteCount": self.byte_count,
            "computeCostMs": self.compute_cost_ms,
            "dependsOn": list(self.depends_on),
            "producerId": self.producer_id,
        }

    @classmethod
    def from_envelope(cls, envelope: Any) -> CacheEntry:
        """Decode a stored envelope, treating anything unexpected as corruption."""

        if not isinstance(envelope, Mapping):
            raise KernelError(
                code="CACHE_ENTRY_INVALID",
                message=f"stored cache entry is a {type(envelope).__name__}, not an object",
                recommended_action="evict the entry",
            )
        if envelope.get("schema") != _ENTRY_SCHEMA:
            raise KernelError(
                code="CACHE_ENTRY_INVALID",
                message=f"stored cache entry has schema {envelope.get('schema')!r}",
                recommended_action=f"evict the entry; this build reads {_ENTRY_SCHEMA}",
            )
        known = {"schema", "keyFingerprint", "tenantId", "namespace", "cacheClass", "keyParts",
                 "negative", "value", "valueDigest", "failureCode", "storedAt", "expiresAt",
                 "byteCount", "computeCostMs", "dependsOn", "producerId"}
        unknown = sorted(set(envelope) - known)
        if unknown:
            raise KernelError(
                code="CACHE_ENTRY_INVALID",
                message=f"stored cache entry carries unknown fields: {unknown}",
                recommended_action="evict the entry",
                details={"unknown": unknown},
            )
        cache_class = require_str(envelope.get("cacheClass"), "cacheClass", max_length=64)
        if cache_class not in {item.value for item in CacheClass}:
            raise KernelError(
                code="CACHE_ENTRY_INVALID",
                message=f"stored cache entry has unknown class {cache_class!r}",
                recommended_action="evict the entry",
            )
        expires_raw = envelope.get("expiresAt")
        return cls(
            key_fingerprint=require_str(envelope.get("keyFingerprint"), "keyFingerprint",
                                        max_length=256),
            tenant_id=require_str(envelope.get("tenantId"), "tenantId", max_length=128),
            namespace=require_str(envelope.get("namespace"), "namespace", max_length=128),
            cache_class=CacheClass(cache_class),
            parts=CacheKeyParts.from_payload(require_mapping(envelope.get("keyParts"),
                                                             "keyParts")),
            negative=require_bool(envelope.get("negative"), "negative"),
            value=envelope.get("value"),
            value_digest=(None if envelope.get("valueDigest") is None
                          else require_str(envelope["valueDigest"], "valueDigest",
                                           max_length=256)),
            failure_code=(None if envelope.get("failureCode") is None
                          else require_str(envelope["failureCode"], "failureCode",
                                           max_length=128)),
            stored_at=parse_timestamp(envelope.get("storedAt"), "storedAt"),
            expires_at=None if expires_raw is None else parse_timestamp(expires_raw, "expiresAt"),
            byte_count=require_int(envelope.get("byteCount"), "byteCount", minimum=0),
            compute_cost_ms=require_int(envelope.get("computeCostMs"), "computeCostMs",
                                        minimum=0),
            depends_on=require_str_seq(envelope.get("dependsOn", ()), "dependsOn"),
            producer_id=require_str(envelope.get("producerId"), "producerId", max_length=128),
        )

    def to_payload(self) -> dict[str, Any]:
        """Outward shape.  The value itself is summarised, never echoed blind."""

        return {
            "keyFingerprint": self.key_fingerprint,
            "tenantId": self.tenant_id,
            "namespace": self.namespace,
            "cacheClass": str(self.cache_class),
            "negative": self.negative,
            "valueDigest": self.value_digest,
            "failureCode": self.failure_code,
            "storedAt": format_timestamp(self.stored_at),
            "expiresAt": None if self.expires_at is None else format_timestamp(self.expires_at),
            "byteCount": self.byte_count,
            "computeCostMs": self.compute_cost_ms,
            "dependsOn": list(self.depends_on),
            "producerId": self.producer_id,
        }


# --- layers ------------------------------------------------------------------


class CacheLayer(Protocol):
    """One storage tier.

    Layers deal in envelopes, never in :class:`CacheEntry`.  Decoding and
    verification happen once, in the fabric, so a new layer cannot accidentally
    skip the checks by returning something already-typed.
    """

    @property
    def layer(self) -> Layer: ...

    def get(self, fingerprint: str) -> Any | None: ...

    def put(self, fingerprint: str, envelope: Mapping[str, Any]) -> None: ...

    def evict(self, fingerprint: str) -> bool: ...

    def fingerprints(self) -> tuple[str, ...]: ...


class InProcessLayer:
    """L1: bounded, process-local, FIFO.

    Eviction is first-in-first-out rather than least-recently-used on purpose:
    LRU makes the layer's contents depend on read order, and read order depends
    on scheduling, which would make the fabric's behaviour irreproducible
    between two runs of the same workload.
    """

    __slots__ = ("_capacity", "_entries")

    def __init__(self, *, capacity: int = 256) -> None:
        if capacity <= 0:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="L1 capacity must be positive",
                recommended_action="configure a capacity of at least one entry",
            )
        self._capacity = capacity
        self._entries: dict[str, Mapping[str, Any]] = {}

    @property
    def layer(self) -> Layer:
        return Layer.L1

    def get(self, fingerprint: str) -> Any | None:
        return self._entries.get(fingerprint)

    def put(self, fingerprint: str, envelope: Mapping[str, Any]) -> None:
        self._entries[fingerprint] = dict(envelope)
        while len(self._entries) > self._capacity:
            oldest = next(iter(self._entries))
            del self._entries[oldest]

    def evict(self, fingerprint: str) -> bool:
        return self._entries.pop(fingerprint, None) is not None

    def fingerprints(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))


class KeyValueLayer:
    """L2: the shared key/value store, namespaced by prefix."""

    __slots__ = ("_kv", "_prefix")

    def __init__(self, kv: KeyValueStore, *, prefix: str = "cache:l2:") -> None:
        self._kv = kv
        self._prefix = prefix

    @property
    def layer(self) -> Layer:
        return Layer.L2

    def _key(self, fingerprint: str) -> str:
        return f"{self._prefix}{fingerprint}"

    def get(self, fingerprint: str) -> Any | None:
        found = self._kv.get(self._key(fingerprint))
        return None if found is None else found[0]

    def put(self, fingerprint: str, envelope: Mapping[str, Any]) -> None:
        self._kv.put(self._key(fingerprint), dict(envelope))

    def evict(self, fingerprint: str) -> bool:
        key = self._key(fingerprint)
        if self._kv.get(key) is None:
            return False
        self._kv.delete(key)
        return True

    def fingerprints(self) -> tuple[str, ...]:
        return tuple(sorted(key[len(self._prefix):] for key, _, _ in self._kv.scan(self._prefix)))


class ArtifactLayer:
    """L3: content-addressed artifact storage plus a key index.

    An artifact store is addressed by the digest of its *content*, which is
    exactly what a cache does not know before it looks something up.  The index
    that closes that gap is part of this layer rather than a hidden global, and
    it is deliberately not trusted: the artifact it points at carries the full
    key parts, so an index that has drifted produces ``CACHE_ENTRY_INVALID``
    instead of another entry's value.
    """

    __slots__ = ("_artifacts", "_index", "_prefix")

    def __init__(self, artifacts: ArtifactStore, index: KeyValueStore, *,
                 prefix: str = "cache:l3-index:") -> None:
        self._artifacts = artifacts
        self._index = index
        self._prefix = prefix

    @property
    def layer(self) -> Layer:
        return Layer.L3

    def _key(self, fingerprint: str) -> str:
        return f"{self._prefix}{fingerprint}"

    def get(self, fingerprint: str) -> Any | None:
        found = self._index.get(self._key(fingerprint))
        if found is None:
            return None
        artifact_digest = found[0]
        if not isinstance(artifact_digest, str) or not self._artifacts.exists(artifact_digest):
            raise KernelError(
                code="CACHE_ENTRY_INVALID",
                message=f"L3 index for {fingerprint} points at a missing artifact",
                recommended_action="evict the index entry and recompute",
            )
        raw = self._artifacts.get(artifact_digest)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise KernelError(
                code="CACHE_ENTRY_INVALID",
                message=f"L3 artifact for {fingerprint} is not a decodable envelope",
                recommended_action="evict the entry and recompute",
            ) from exc

    def put(self, fingerprint: str, envelope: Mapping[str, Any]) -> None:
        data = canonical_json(dict(envelope)).encode("utf-8")
        artifact_digest = self._artifacts.put(data, media_type="application/json")
        self._index.put(self._key(fingerprint), artifact_digest)

    def evict(self, fingerprint: str) -> bool:
        key = self._key(fingerprint)
        if self._index.get(key) is None:
            return False
        # The artifact itself is content-addressed and may be shared; only the
        # index entry is removed, so eviction can never orphan another key.
        self._index.delete(key)
        return True

    def fingerprints(self) -> tuple[str, ...]:
        return tuple(sorted(key[len(self._prefix):]
                            for key, _, _ in self._index.scan(self._prefix)))


# --- counters & metrics ------------------------------------------------------


@dataclass(slots=True)
class LayerCounters:
    """Per-layer tallies.  Every one of them is an integer count of events."""

    probes: int = 0
    hits: int = 0
    misses: int = 0
    writes: int = 0
    promotions: int = 0
    evictions: int = 0
    expired: int = 0
    invalid: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "probes": self.probes,
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "promotions": self.promotions,
            "evictions": self.evictions,
            "expired": self.expired,
            "invalid": self.invalid,
        }


@dataclass(frozen=True, slots=True)
class CacheMetrics:
    """Fabric-wide counters.

    ``hit_rate_per_mille`` is an integer per-mille rather than a float ratio —
    floats are not canonically representable and this number is compared across
    machines.  When nothing has been looked up it is ``None`` with
    ``measured: false``, because a hit rate of zero and no measurement at all
    are different facts and only one of them is a problem.
    """

    lookups: int
    hits: int
    misses: int
    bypasses: int
    negative_hits: int
    admissions: int
    admission_rejections: int
    invalidations: int
    stale_reuse_prevented: int
    per_layer: tuple[tuple[Layer, LayerCounters], ...]

    @property
    def hit_rate_per_mille(self) -> int | None:
        countable = self.hits + self.misses
        if countable == 0:
            return None
        return (self.hits * 1000) // countable

    def to_payload(self) -> dict[str, Any]:
        rate = self.hit_rate_per_mille
        return {
            "lookups": self.lookups,
            "hits": self.hits,
            "misses": self.misses,
            "bypasses": self.bypasses,
            "negativeHits": self.negative_hits,
            "admissions": self.admissions,
            "admissionRejections": self.admission_rejections,
            "invalidations": self.invalidations,
            "staleReusePrevented": self.stale_reuse_prevented,
            "hitRatePerMille": rate,
            "hitRateMeasured": rate is not None,
            "perLayer": [
                {"layer": str(layer)} | counters.to_payload()
                for layer, counters in self.per_layer
            ],
        }


# --- results -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LookupResult:
    """What a lookup found, where, and why it counts as that."""

    outcome: LookupOutcome
    reason: LookupReason
    key_fingerprint: str
    layers_probed: tuple[Layer, ...] = ()
    layer: Layer | None = None
    entry: CacheEntry | None = None
    promoted_to: tuple[Layer, ...] = ()
    detail: str = ""

    @property
    def is_hit(self) -> bool:
        """A bypass is never a hit and a negative hit is still a hit."""

        return self.outcome is LookupOutcome.HIT

    def to_payload(self) -> dict[str, Any]:
        return {
            "outcome": str(self.outcome),
            "reason": str(self.reason),
            "keyFingerprint": self.key_fingerprint,
            "layersProbed": [str(item) for item in self.layers_probed],
            "layer": None if self.layer is None else str(self.layer),
            "entry": None if self.entry is None else self.entry.to_payload(),
            "promotedTo": [str(item) for item in self.promoted_to],
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """Whether a computed result was written, and why."""

    admitted: bool
    reason: AdmissionReason
    key_fingerprint: str
    byte_count: int
    compute_cost_ms: int | None
    expires_at: datetime | None = None
    layers_written: tuple[Layer, ...] = ()
    detail: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "reason": str(self.reason),
            "keyFingerprint": self.key_fingerprint,
            "byteCount": self.byte_count,
            "computeCostMs": self.compute_cost_ms,
            "computeCostMeasured": self.compute_cost_ms is not None,
            "expiresAt": (None if self.expires_at is None
                          else format_timestamp(self.expires_at)),
            "layersWritten": [str(item) for item in self.layers_written],
            "detail": self.detail,
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class InvalidationSet:
    """Everything a change invalidated, and the closure that produced it."""

    changed_nodes: tuple[str, ...]
    closure: tuple[str, ...]
    fingerprints: tuple[str, ...]
    evicted: tuple[tuple[Layer, str], ...]
    undeclared_dependencies: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "changedNodes": list(self.changed_nodes),
            "closure": list(self.closure),
            "fingerprints": list(self.fingerprints),
            "evicted": [[str(layer), fingerprint] for layer, fingerprint in self.evicted],
            "undeclaredDependencies": list(self.undeclared_dependencies),
            "digest": digest({
                "changedNodes": list(self.changed_nodes),
                "fingerprints": list(self.fingerprints),
            }),
        }


# --- policy & candidates -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class AdmissionPolicy:
    """What is worth caching.

    ``cacheable_classes`` defaults to nothing.  An empty set denies every
    admission, which is the fail-closed reading: a fabric that was never told
    what it may cache must not decide for itself.
    """

    min_compute_cost_ms: int = 0
    max_value_bytes: int = 1 << 20
    positive_ttl_seconds: int | None = None
    negative_ttl_seconds: int = 60
    cacheable_classes: frozenset[CacheClass] = frozenset()

    def __post_init__(self) -> None:
        require_int(self.min_compute_cost_ms, "policy.min_compute_cost_ms", minimum=0)
        require_int(self.max_value_bytes, "policy.max_value_bytes", minimum=1)
        require_int(self.negative_ttl_seconds, "policy.negative_ttl_seconds", minimum=1)
        if self.positive_ttl_seconds is not None:
            require_int(self.positive_ttl_seconds, "policy.positive_ttl_seconds", minimum=1)
        if CacheClass.SECRET_BOUND in self.cacheable_classes:
            raise KernelError(
                code="CACHE_ADMISSION_REJECTED",
                message="secret-bound results are never cacheable",
                recommended_action="remove secret-bound from the cacheable classes",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "minComputeCostMs": self.min_compute_cost_ms,
            "maxValueBytes": self.max_value_bytes,
            "positiveTtlSeconds": self.positive_ttl_seconds,
            "negativeTtlSeconds": self.negative_ttl_seconds,
            "cacheableClasses": sorted(str(item) for item in self.cacheable_classes),
        }


@dataclass(frozen=True, slots=True)
class Candidate:
    """A freshly computed result offered to the cache.

    ``compute_cost_ms`` is ``None`` when nobody measured it.  That is refused
    rather than treated as zero: "free" and "unmeasured" are different, and
    only one of them should keep a result out of the cache.
    """

    value: Any = None
    deterministic: bool = True
    compute_cost_ms: int | None = None
    negative: bool = False
    failure_code: str | None = None
    retryable: bool = False
    depends_on: tuple[str, ...] = ()
    producer_id: str = "unknown"
    ttl_seconds: int | None = None

    def __post_init__(self) -> None:
        require_bool(self.deterministic, "candidate.deterministic")
        require_bool(self.negative, "candidate.negative")
        require_bool(self.retryable, "candidate.retryable")
        if self.compute_cost_ms is not None:
            require_int(self.compute_cost_ms, "candidate.compute_cost_ms", minimum=0)
        if self.ttl_seconds is not None:
            require_int(self.ttl_seconds, "candidate.ttl_seconds", minimum=1)
        if self.negative and not self.failure_code:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="a negative candidate must name the failure code it records",
                recommended_action="pass the stable failure code with the candidate",
            )


@dataclass(frozen=True, slots=True)
class Operation:
    """The operation the lookup is standing in for.

    A tool with declared side effects is never served from cache: a cache hit
    would return the *result* of an action without performing the action, which
    is the single most damaging thing a cache in this system can do.
    """

    operation_id: str = "unknown"
    side_effecting: bool = False

    def __post_init__(self) -> None:
        require_bool(self.side_effecting, "operation.side_effecting")


@dataclass(frozen=True, slots=True)
class DependencyGraph:
    """Which artifacts depend on which, for invalidation recall.

    ``edges`` maps a node to the nodes that depend on it, so invalidating a
    changed file walks forwards to everything derived from it.  Recall is what
    matters here, not precision: over-invalidating costs compute, and
    under-invalidating costs correctness.
    """

    edges: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def closure(self, changed: Iterable[str]) -> tuple[str, ...]:
        """Every node reachable from ``changed``, including ``changed`` itself."""

        seen: set[str] = set()
        stack = list(changed)
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(self.edges.get(node, ()))
        return tuple(sorted(seen))


# --- the fabric --------------------------------------------------------------


class CacheFabric:
    """Layered lookup, verified hits, explained admission, recallable invalidation.

    The fabric is pinned to one tenant, one repository snapshot and one policy
    snapshot.  A key that disagrees with any of those is an error rather than a
    silent refresh, because a fabric that quietly serves the newest thing it has
    is a fabric whose answers cannot be reproduced.
    """

    __slots__ = ("_tenant_id", "_snapshot_sha", "_policy_hash", "_layers", "_policy",
                 "_clock", "_dependencies", "_counters", "_tombstones", "_lookups",
                 "_hits", "_misses", "_bypasses", "_negative_hits", "_admissions",
                 "_rejections", "_invalidations", "_stale_prevented")

    def __init__(self, *, tenant_id: str, snapshot_sha: str, policy_hash: str,
                 layers: Sequence[CacheLayer], policy: AdmissionPolicy, clock: Clock,
                 dependencies: DependencyGraph | None = None) -> None:
        require_identifier(tenant_id, "fabric.tenant_id")
        require_str(snapshot_sha, "fabric.snapshot_sha", max_length=256)
        require_str(policy_hash, "fabric.policy_hash", max_length=256)
        seen: set[Layer] = set()
        for item in layers:
            if item.layer in seen:
                raise KernelError(
                    code="CACHE_LAYER_UNKNOWN",
                    message=f"layer {item.layer} is configured twice",
                    recommended_action="configure at most one implementation per layer",
                )
            seen.add(item.layer)
        self._tenant_id = tenant_id
        self._snapshot_sha = snapshot_sha
        self._policy_hash = policy_hash
        self._layers = tuple(sorted(layers, key=lambda item: item.layer.value))
        self._policy = policy
        self._clock = clock
        self._dependencies = dependencies or DependencyGraph()
        self._counters: dict[Layer, LayerCounters] = {
            item.layer: LayerCounters() for item in self._layers
        }
        self._tombstones: set[str] = set()
        self._lookups = 0
        self._hits = 0
        self._misses = 0
        self._bypasses = 0
        self._negative_hits = 0
        self._admissions = 0
        self._rejections = 0
        self._invalidations = 0
        self._stale_prevented = 0

    # -- guards ---------------------------------------------------------------

    def _guard_key(self, key: CacheKey) -> None:
        """Refuse a key that belongs to another tenant or another snapshot."""

        if key.tenant_id != self._tenant_id:
            raise KernelError(
                code="ISOLATION_VIOLATION",
                message=(
                    f"cache key belongs to tenant {key.tenant_id!r}; "
                    f"this fabric serves {self._tenant_id!r}"
                ),
                retryable=False,
                recommended_action="never share a cache fabric across tenants",
                details={"expectedTenantId": self._tenant_id},
            )
        if key.parts.repo_snapshot_sha != self._snapshot_sha:
            raise KernelError(
                code="STALE_SNAPSHOT",
                message=(
                    f"cache key is bound to snapshot {key.parts.repo_snapshot_sha}, "
                    f"the fabric is pinned to {self._snapshot_sha}"
                ),
                retryable=False,
                recommended_action="rebuild the key against the live snapshot",
            )
        if key.parts.policy_hash != self._policy_hash:
            raise KernelError(
                code="STALE_POLICY_SNAPSHOT",
                message=(
                    f"cache key is bound to policy {key.parts.policy_hash}, "
                    f"the fabric is pinned to {self._policy_hash}"
                ),
                retryable=False,
                recommended_action="re-evaluate under the current policy snapshot",
            )

    def _verify(self, entry: CacheEntry, key: CacheKey, layer: Layer) -> None:
        """Prove a candidate hit is the same computation, or raise.

        Order matters.  Tenancy first, because a cross-tenant read is a security
        event and not a cache event.  Snapshot and policy next, because those
        are the two parts whose reuse is both most likely and most damaging, and
        they deserve their own code.  Everything else is generic corruption.
        """

        if entry.tenant_id != key.tenant_id:
            raise KernelError(
                code="ISOLATION_VIOLATION",
                message=f"{layer} entry for {key.fingerprint} belongs to another tenant",
                recommended_action="evict the entry and audit the layer's namespacing",
            )
        if entry.parts.repo_snapshot_sha != key.parts.repo_snapshot_sha or \
                entry.parts.policy_hash != key.parts.policy_hash:
            raise KernelError(
                code="STALE_CACHE_USED",
                message=(
                    f"{layer} entry for {key.fingerprint} was produced under snapshot "
                    f"{entry.parts.repo_snapshot_sha} / policy {entry.parts.policy_hash}"
                ),
                recommended_action="evict the entry; the fingerprint index has drifted",
            )
        if entry.parts != key.parts or entry.namespace != key.namespace or \
                entry.cache_class is not key.cache_class:
            raise KernelError(
                code="CACHE_ENTRY_INVALID",
                message=(
                    f"{layer} entry for {key.fingerprint} does not carry the requested key; "
                    "this is a collision or a corrupted index, not a hit"
                ),
                recommended_action="evict the entry and recompute",
            )
        if not entry.negative and digest(entry.value) != entry.value_digest:
            raise KernelError(
                code="CACHE_POISONED",
                message=f"{layer} entry for {key.fingerprint} does not hash to its stored digest",
                recommended_action="evict the entry and treat the layer as suspect",
            )

    # -- lookup ---------------------------------------------------------------

    def lookup(self, key: CacheKey, *, operation: Operation | None = None) -> LookupResult:
        """Walk the layers and return a hit only when it is provably the same input."""

        self._guard_key(key)
        fingerprint = key.fingerprint
        self._lookups += 1

        bypass = self._bypass_reason(key, operation)
        if bypass is not None:
            self._bypasses += 1
            return LookupResult(
                outcome=LookupOutcome.BYPASS,
                reason=bypass,
                key_fingerprint=fingerprint,
                detail=f"lookup bypassed: {bypass}",
            )
        if not self._layers:
            self._bypasses += 1
            return LookupResult(
                outcome=LookupOutcome.BYPASS,
                reason=LookupReason.NO_LAYERS_CONFIGURED,
                key_fingerprint=fingerprint,
                detail="no cache layer is configured; nothing was consulted",
            )

        probed: list[Layer] = []
        now = self._clock.now()
        miss_reason = LookupReason.ABSENT
        for layer in self._layers:
            probed.append(layer.layer)
            counters = self._counters[layer.layer]
            counters.probes += 1
            envelope = layer.get(fingerprint)
            if envelope is None:
                counters.misses += 1
                continue
            if fingerprint in self._tombstones:
                counters.evictions += 1
                layer.evict(fingerprint)
                self._stale_prevented += 1
                miss_reason = LookupReason.INVALIDATED
                continue
            try:
                entry = CacheEntry.from_envelope(envelope)
                self._verify(entry, key, layer.layer)
            except KernelError:
                counters.invalid += 1
                layer.evict(fingerprint)
                self._stale_prevented += 1
                raise
            if entry.is_expired(now):
                counters.expired += 1
                counters.evictions += 1
                layer.evict(fingerprint)
                miss_reason = LookupReason.EXPIRED
                continue
            counters.hits += 1
            self._hits += 1
            promoted = self._promote(fingerprint, envelope, layer.layer)
            if entry.negative:
                self._negative_hits += 1
            return LookupResult(
                outcome=LookupOutcome.HIT,
                reason=(LookupReason.NEGATIVE_HIT if entry.negative
                        else LookupReason.FRESH_HIT),
                key_fingerprint=fingerprint,
                layers_probed=tuple(probed),
                layer=layer.layer,
                entry=entry,
                promoted_to=promoted,
                detail=f"verified hit in {layer.layer}",
            )

        self._misses += 1
        return LookupResult(
            outcome=LookupOutcome.MISS,
            reason=miss_reason,
            key_fingerprint=fingerprint,
            layers_probed=tuple(probed),
            detail=f"no usable entry in {[str(item) for item in probed]}",
        )

    def _bypass_reason(self, key: CacheKey, operation: Operation | None) -> LookupReason | None:
        if operation is not None and operation.side_effecting:
            return LookupReason.SIDE_EFFECTING_OPERATION
        if key.cache_class is CacheClass.SECRET_BOUND:
            return LookupReason.SECRET_BOUND_CLASS
        if key.cache_class not in self._policy.cacheable_classes:
            return LookupReason.CLASS_NOT_CACHEABLE
        return None

    def _promote(self, fingerprint: str, envelope: Mapping[str, Any],
                 found_in: Layer) -> tuple[Layer, ...]:
        promoted: list[Layer] = []
        for layer in self._layers:
            if layer.layer.value >= found_in.value:
                break
            if layer.get(fingerprint) is None:
                layer.put(fingerprint, envelope)
                self._counters[layer.layer].promotions += 1
                promoted.append(layer.layer)
        return tuple(promoted)

    # -- admission ------------------------------------------------------------

    def admit(self, key: CacheKey, candidate: Candidate, *,
              operation: Operation | None = None) -> AdmissionDecision:
        """Decide whether to store ``candidate`` and, if so, store it everywhere."""

        self._guard_key(key)
        fingerprint = key.fingerprint
        payload = None if candidate.negative else candidate.value
        byte_count = len(canonical_json(payload).encode("utf-8"))

        refusal = self._refusal(key, candidate, operation, byte_count)
        if refusal is not None:
            self._rejections += 1
            return AdmissionDecision(
                admitted=False,
                reason=refusal,
                key_fingerprint=fingerprint,
                byte_count=byte_count,
                compute_cost_ms=candidate.compute_cost_ms,
                detail=f"admission refused: {refusal}",
            )

        now = self._clock.now()
        ttl = self._ttl_for(candidate)
        expires_at = None if ttl is None else now + timedelta(seconds=ttl)
        entry = CacheEntry(
            key_fingerprint=fingerprint,
            tenant_id=key.tenant_id,
            namespace=key.namespace,
            cache_class=key.cache_class,
            parts=key.parts,
            negative=candidate.negative,
            value=payload,
            value_digest=None if candidate.negative else digest(payload),
            failure_code=candidate.failure_code,
            stored_at=now,
            expires_at=expires_at,
            byte_count=byte_count,
            compute_cost_ms=int(candidate.compute_cost_ms or 0),
            depends_on=tuple(sorted(set(candidate.depends_on))),
            producer_id=candidate.producer_id,
        )
        envelope = entry.to_envelope()
        written: list[Layer] = []
        for layer in self._layers:
            layer.put(fingerprint, envelope)
            self._counters[layer.layer].writes += 1
            written.append(layer.layer)
        self._tombstones.discard(fingerprint)
        self._admissions += 1
        return AdmissionDecision(
            admitted=True,
            reason=AdmissionReason.ADMITTED,
            key_fingerprint=fingerprint,
            byte_count=byte_count,
            compute_cost_ms=candidate.compute_cost_ms,
            expires_at=expires_at,
            layers_written=tuple(written),
            detail=f"stored in {[str(item) for item in written]}",
        )

    def _refusal(self, key: CacheKey, candidate: Candidate, operation: Operation | None,
                 byte_count: int) -> AdmissionReason | None:
        if operation is not None and operation.side_effecting:
            return AdmissionReason.SIDE_EFFECTING_OPERATION
        if key.cache_class is CacheClass.SECRET_BOUND:
            return AdmissionReason.SECRET_BOUND_CLASS
        if key.cache_class not in self._policy.cacheable_classes:
            return AdmissionReason.CLASS_NOT_CACHEABLE
        if not candidate.deterministic:
            return AdmissionReason.NONDETERMINISTIC_RESULT
        if candidate.negative:
            if candidate.retryable or candidate.failure_code == "FAILED_RETRYABLE":
                return AdmissionReason.RETRYABLE_FAILURE_NOT_CACHEABLE
            if self._ttl_for(candidate) is None:
                return AdmissionReason.NEGATIVE_TTL_REQUIRED
        if candidate.compute_cost_ms is None:
            return AdmissionReason.COMPUTE_COST_UNMEASURED
        if candidate.compute_cost_ms < self._policy.min_compute_cost_ms:
            return AdmissionReason.BELOW_MIN_COMPUTE_COST
        if byte_count > self._policy.max_value_bytes:
            return AdmissionReason.ABOVE_MAX_SIZE
        return None

    def _ttl_for(self, candidate: Candidate) -> int | None:
        if candidate.ttl_seconds is not None:
            return candidate.ttl_seconds
        if candidate.negative:
            return self._policy.negative_ttl_seconds
        return self._policy.positive_ttl_seconds

    # -- invalidation ---------------------------------------------------------

    def invalidate(self, changed_nodes: Sequence[str]) -> InvalidationSet:
        """Evict every entry that cannot be proven unaffected by ``changed_nodes``.

        An entry that declares no dependencies is invalidated unconditionally.
        That is the fail-closed reading of "we do not know what this depended
        on", and it is the difference between an invalidation set with complete
        recall and one that merely looks tidy.
        """

        nodes = tuple(require_str_seq(changed_nodes, "changed_nodes", allow_empty=False))
        closure = self._dependencies.closure(nodes)
        closure_set = set(closure)
        targets: set[str] = set()
        undeclared: set[str] = set()
        for layer in self._layers:
            for fingerprint in layer.fingerprints():
                envelope = layer.get(fingerprint)
                if envelope is None:
                    continue
                try:
                    entry = CacheEntry.from_envelope(envelope)
                except KernelError:
                    targets.add(fingerprint)
                    continue
                if not entry.depends_on:
                    undeclared.add(fingerprint)
                    targets.add(fingerprint)
                elif closure_set.intersection(entry.depends_on):
                    targets.add(fingerprint)

        evicted: list[tuple[Layer, str]] = []
        for fingerprint in sorted(targets):
            self._tombstones.add(fingerprint)
            for layer in self._layers:
                if layer.evict(fingerprint):
                    self._counters[layer.layer].evictions += 1
                    evicted.append((layer.layer, fingerprint))
        self._invalidations += len(targets)
        return InvalidationSet(
            changed_nodes=nodes,
            closure=closure,
            fingerprints=tuple(sorted(targets)),
            evicted=tuple(evicted),
            undeclared_dependencies=tuple(sorted(undeclared)),
        )

    # -- reporting ------------------------------------------------------------

    def metrics(self) -> CacheMetrics:
        """Snapshot of every counter, layer by layer."""

        return CacheMetrics(
            lookups=self._lookups,
            hits=self._hits,
            misses=self._misses,
            bypasses=self._bypasses,
            negative_hits=self._negative_hits,
            admissions=self._admissions,
            admission_rejections=self._rejections,
            invalidations=self._invalidations,
            stale_reuse_prevented=self._stale_prevented,
            per_layer=tuple(
                (layer.layer, self._counters[layer.layer]) for layer in self._layers
            ),
        )

    def provenance(self) -> dict[str, Any]:
        """What this fabric is pinned to.  Part of every response."""

        return {
            "tenantId": self._tenant_id,
            "repoSnapshotSha": self._snapshot_sha,
            "policyHash": self._policy_hash,
            "layers": [str(layer.layer) for layer in self._layers],
            "admissionPolicy": self._policy.to_payload(),
        }


# --- durable record ----------------------------------------------------------


def record_admission(decision: AdmissionDecision, events: EventStore, *,
                     stream_id: str, fencing_token: int) -> Mapping[str, Any]:
    """Append an admission decision to the run log.

    The idempotency key is the decision's own digest, so a redelivered
    admission returns the original event instead of writing a second one; the
    fencing token means a worker whose lease was taken over cannot append at
    all.  Both matter because "the cache was written twice" and "a superseded
    worker wrote the cache" are indistinguishable from the value alone.
    """

    event = events.append(
        stream_id,
        {"kind": "cache.admission", "admission": decision.to_payload(),
         "admissionDigest": decision.digest},
        idempotency_key=decision.digest,
        fencing_token=fencing_token,
    )
    return {
        "sequence": event.sequence,
        "eventId": event.event_id,
        "hashChain": event.hash_chain,
        "admissionDigest": decision.digest,
    }


# --- registry entry point ----------------------------------------------------

_FABRIC: CacheFabric | None = None


def bind_fabric(fabric: CacheFabric | None) -> None:
    """Bind the process-wide fabric that :func:`handle` serves from."""

    global _FABRIC
    _FABRIC = fabric


def bound_fabric() -> CacheFabric:
    """Return the bound fabric or fail closed.

    An unconfigured cache does not degrade into "always miss": a miss is a
    statement about the cache's contents, and this build has none to make.
    """

    if _FABRIC is None:
        raise KernelError(
            code="CACHE_UNCONFIGURED",
            message="no cache fabric is bound in this process",
            recommended_action="call cache.bind_fabric at startup",
        )
    return _FABRIC


def _decode_class(value: Any) -> CacheClass:
    text = require_str(value, "cacheClass", max_length=64)
    if text not in {item.value for item in CacheClass}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown cache class {text!r}",
            recommended_action=f"use one of {sorted(item.value for item in CacheClass)}",
        )
    return CacheClass(text)


def _decode_candidate(payload: Mapping[str, Any]) -> Candidate:
    reject_unknown_fields(
        payload,
        {"value", "deterministic", "computeCostMs", "negative", "failureCode", "retryable",
         "dependsOn", "producerId", "ttlSeconds"},
        field_name="candidate",
    )
    raw_cost = payload.get("computeCostMs")
    raw_ttl = payload.get("ttlSeconds")
    return Candidate(
        value=payload.get("value"),
        deterministic=require_bool(payload.get("deterministic", True), "candidate.deterministic"),
        compute_cost_ms=(None if raw_cost is None
                         else require_int(raw_cost, "candidate.computeCostMs", minimum=0)),
        negative=require_bool(payload.get("negative", False), "candidate.negative"),
        failure_code=(None if payload.get("failureCode") is None
                      else require_str(payload["failureCode"], "candidate.failureCode",
                                       max_length=128)),
        retryable=require_bool(payload.get("retryable", False), "candidate.retryable"),
        depends_on=require_str_seq(payload.get("dependsOn", ()), "candidate.dependsOn"),
        producer_id=require_str(payload.get("producerId", "unknown"), "candidate.producerId",
                                max_length=128),
        ttl_seconds=(None if raw_ttl is None
                     else require_int(raw_ttl, "candidate.ttlSeconds", minimum=1)),
    )


@register("layered-cache-fabric")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    The response always carries the key, the lookup result and the metrics, so
    a caller can never conclude "it was cached" from the absence of an error.
    An admission refusal is reported, not raised: refusing to cache something is
    a normal outcome, whereas an incomplete key or a poisoned entry is not.
    """

    reject_unknown_fields(
        request,
        {"cache_key_inputs", "layer_config", "operation", "candidate", "invalidate"},
        field_name="layered-cache-fabric request",
    )
    fabric = bound_fabric()

    config = require_mapping(request.get("layer_config"), "layer_config")
    reject_unknown_fields(config, {"tenantId", "namespace", "cacheClass"},
                          field_name="layer_config")
    key = build_key(
        require_mapping(request.get("cache_key_inputs"), "cache_key_inputs"),
        tenant_id=require_identifier(config.get("tenantId"), "layer_config.tenantId"),
        namespace=require_identifier(config.get("namespace"), "layer_config.namespace"),
        cache_class=_decode_class(config.get("cacheClass")),
    )

    operation: Operation | None = None
    if request.get("operation") is not None:
        mapping = require_mapping(request["operation"], "operation")
        reject_unknown_fields(mapping, {"operationId", "sideEffecting"}, field_name="operation")
        operation = Operation(
            operation_id=require_identifier(mapping.get("operationId", "unknown"),
                                            "operation.operationId"),
            side_effecting=require_bool(mapping.get("sideEffecting", False),
                                        "operation.sideEffecting"),
        )

    invalidation: InvalidationSet | None = None
    if request.get("invalidate") is not None:
        invalidation = fabric.invalidate(
            require_str_seq(request["invalidate"], "invalidate", allow_empty=False)
        )

    lookup = fabric.lookup(key, operation=operation)

    admission: AdmissionDecision | None = None
    if request.get("candidate") is not None and not lookup.is_hit:
        admission = fabric.admit(
            key,
            _decode_candidate(require_mapping(request["candidate"], "candidate")),
            operation=operation,
        )

    return {
        "cache_key": key.to_payload() | {"fingerprint": key.fingerprint},
        "cache_entry": None if lookup.entry is None else lookup.entry.to_payload(),
        "hit_miss": lookup.to_payload(),
        "lookup_result": lookup.to_payload(),
        "admission_decision": None if admission is None else admission.to_payload(),
        "invalidation_set": None if invalidation is None else invalidation.to_payload(),
        "provenance": fabric.provenance(),
        "cache_metrics": fabric.metrics().to_payload(),
    }
