"""Exact-toolchain enforcement, matching `engines/polyglot-route-engine`'s
pattern: certified-ddl-v1's parse/emit/round-trip-validate proof was captured
against one exact sqlglot release. A different release could parse or
generate differently; this module fails closed rather than silently trusting
whatever version happens to be installed."""
from __future__ import annotations

import sqlglot

from .models import RouteError

PINNED_SQLGLOT_VERSION = "30.14.0"


def verify_toolchain() -> None:
    if sqlglot.__version__ != PINNED_SQLGLOT_VERSION:
        raise RouteError(
            "TOOLCHAIN_MISMATCH: certified-ddl-v1 was verified against sqlglot "
            f"{PINNED_SQLGLOT_VERSION}, found {sqlglot.__version__}. Install the exact pinned "
            "version (see pyproject.toml) before trusting certified-ddl-v1 results."
        )
