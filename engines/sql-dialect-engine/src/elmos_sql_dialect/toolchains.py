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
    # sqlglot declares no __all__, so a type checker will not accept
    # `sqlglot.__version__` as an exported attribute even though it is a stable
    # part of the package's public surface. The narrow ignore keeps this module
    # strict-clean without weakening the comparison -- the pin is still exact
    # and still fails closed.
    installed: str = sqlglot.__version__  # type: ignore[attr-defined]
    if installed != PINNED_SQLGLOT_VERSION:
        raise RouteError(
            "TOOLCHAIN_MISMATCH: certified-ddl-v1 was verified against sqlglot "
            f"{PINNED_SQLGLOT_VERSION}, found {installed}. Install the exact pinned "
            "version (see pyproject.toml) before trusting certified-ddl-v1 results."
        )
