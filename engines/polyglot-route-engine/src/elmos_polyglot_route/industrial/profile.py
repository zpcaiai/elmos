"""enterprise-industrial-v1 semantic contract.

This profile is the industrial counterpart of typed-pure-function-v1.
It admits a closed, fail-closed subset of concurrency, ownership, I/O,
exceptions and REST/DI constructs. Anything outside the subset is rejected
rather than silently approximated.
"""

from __future__ import annotations

from typing import Final

from elmos_polyglot_route.models import ENTERPRISE_INDUSTRIAL_PROFILE

INDUSTRIAL_PROFILE: Final[str] = ENTERPRISE_INDUSTRIAL_PROFILE

INDUSTRIAL_DOMAINS: Final[tuple[str, ...]] = (
    "async-concurrency",
    "object-graph-lifecycle",
    "system-io",
    "exception-unwinding",
    "complex-framework-and-ui",
)

SUPPORTED_INDUSTRIAL_CONSTRUCTS: Final[frozenset[str]] = frozenset(
    {
        "spawn",
        "join",
        "channel-make",
        "channel-send",
        "channel-recv",
        "select",
        "lock",
        "move",
        "drop",
        "io-read",
        "io-write",
        "try-catch",
        "throw",
        "rest-get",
        "rest-post",
        "typed-arithmetic",
        "if-return",
    }
)
