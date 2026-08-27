"""Content-addressed route profiles shared by the SQL translation surfaces.

Namespace mappings are part of the meaning of a translated object name.  A
plain ``dict`` is therefore not enough for an auditable route: two callers can
use different mappings while reporting the same target profile.  This module
keeps the mapping immutable, deterministic and digest-bound while retaining a
``Mapping`` interface for the existing parser APIs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from .models import DialectError


def _canonical_mapping(mapping: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    raw_items = tuple(mapping.items())
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in raw_items):
        raise DialectError("INVALID_NAMESPACE_PROFILE", "namespace keys must be strings")
    # The empty key is meaningful: it maps the source default namespace.
    items = tuple(sorted(raw_items))
    if any(not value for _, value in items):
        raise DialectError("INVALID_NAMESPACE_PROFILE", "namespace target values must not be empty")
    return items


def _digest(items: tuple[tuple[str, str], ...]) -> str:
    payload = json.dumps({"mapping": items}, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NamespaceProfile(Mapping[str, str]):
    """An immutable source-to-target namespace map with a stable digest."""

    name: str
    entries: tuple[tuple[str, str], ...]
    digest: str

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, str], name: str = "explicit-namespace") -> NamespaceProfile:
        entries = _canonical_mapping(mapping)
        return cls(name=name, entries=entries, digest=_digest(entries))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> NamespaceProfile:
        name = payload.get("name", "explicit-namespace")
        raw_mapping = payload.get("mapping")
        supplied_digest = payload.get("digest")
        if not isinstance(name, str) or not isinstance(raw_mapping, Mapping):
            raise DialectError(
                "INVALID_NAMESPACE_PROFILE",
                "namespace profile requires string name and object mapping",
            )
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in raw_mapping.items()):
            raise DialectError(
                "INVALID_NAMESPACE_PROFILE",
                "namespace profile mapping must contain only string keys and values",
            )
        profile = cls.from_mapping(raw_mapping, name=name)
        if supplied_digest is not None:
            if not isinstance(supplied_digest, str) or supplied_digest != profile.digest:
                raise DialectError(
                    "INVALID_NAMESPACE_PROFILE_DIGEST",
                    "namespace profile digest does not match its canonical mapping",
                )
        return profile

    def __getitem__(self, key: str) -> str:
        for source, target in self.entries:
            if source == key:
                return target
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (source for source, _ in self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "mapping": {source: target for source, target in self.entries},
            "digest": self.digest,
        }


def resolve_namespace_profile(
    namespace_map: Mapping[str, str] | None,
    namespace_profile: NamespaceProfile | None,
) -> NamespaceProfile | None:
    """Resolve legacy map and new profile arguments without implicit mapping."""

    if namespace_map is not None and namespace_profile is not None:
        legacy = NamespaceProfile.from_mapping(namespace_map, name=namespace_profile.name)
        if legacy.digest != namespace_profile.digest:
            raise DialectError(
                "NAMESPACE_PROFILE_CONFLICT",
                "namespace_map and namespace_profile describe different mappings",
            )
        return namespace_profile
    if namespace_profile is not None:
        return namespace_profile
    if namespace_map is not None:
        return NamespaceProfile.from_mapping(namespace_map)
    return None
