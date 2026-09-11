"""Authoritative 15-language industrial matrix (210 directed routes)."""

from __future__ import annotations

from elmos_polyglot_route.models import SUPPORTED_LANGUAGES

INDUSTRIAL_LANGUAGES: tuple[str, ...] = tuple(
    language for language in SUPPORTED_LANGUAGES if language != "javascript"
)

VENDOR_RUNTIME_LANGUAGES: frozenset[str] = frozenset({"vb6", "vcpp6"})
HOSTED_RUNTIME_LANGUAGES: tuple[str, ...] = tuple(
    language for language in INDUSTRIAL_LANGUAGES if language not in VENDOR_RUNTIME_LANGUAGES
)

INDUSTRIAL_ROUTE_KEYS: tuple[tuple[str, str], ...] = tuple(
    (source, target)
    for source in INDUSTRIAL_LANGUAGES
    for target in INDUSTRIAL_LANGUAGES
    if source != target
)

assert len(INDUSTRIAL_LANGUAGES) == 15
assert len(INDUSTRIAL_ROUTE_KEYS) == 210
