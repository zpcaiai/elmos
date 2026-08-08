from __future__ import annotations

import pytest

from elmos_polyglot_route import toolchains
from elmos_polyglot_route.models import RouteError


@pytest.mark.parametrize(
    "observed",
    [
        "go version go1.25.0 darwin/arm64",
        "go version go1.25.0 linux/amd64",
    ],
)
def test_go_accepts_only_declared_exact_ci_platform_tuples(
    monkeypatch: pytest.MonkeyPatch, observed: str
) -> None:
    monkeypatch.setattr(toolchains.shutil, "which", lambda name: "/usr/local/bin/go")
    monkeypatch.setattr(toolchains, "_output", lambda command: observed)

    selected = toolchains._go()

    assert selected.version == "1.25.0"
    assert selected.executable == "/usr/local/bin/go"


@pytest.mark.parametrize(
    "observed",
    [
        "go version go1.24.13 linux/amd64",
        "go version go1.25.0 windows/amd64",
        "go1.25.0",
    ],
)
def test_go_rejects_version_platform_and_output_drift(
    monkeypatch: pytest.MonkeyPatch, observed: str
) -> None:
    monkeypatch.setattr(toolchains.shutil, "which", lambda name: "/usr/local/bin/go")
    monkeypatch.setattr(toolchains, "_output", lambda command: observed)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_MISMATCH:go"):
        toolchains._go()
