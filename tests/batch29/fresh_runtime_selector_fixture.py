from __future__ import annotations

import os
import sys


def main() -> int:
    if sys.argv[1:] != ["--selector-smoke"]:
        raise SystemExit("focused fresh-child fixture received unexpected arguments")
    from elmos_polyglot_route import toolchains
    from elmos_polyglot_route.models import DEPRECATED_LANGUAGES, ROUTED_LANGUAGES
    from elmos_polyglot_route.toolchains import ExactToolchain

    selectors = {
        "java": "_java",
        "python": "_python",
        "csharp": "_csharp",
        "typescript": "_typescript",
        "go": "_go",
        "rust": "_rust",
        "cpp": "_cpp",
        "objc": "_objc",
        "swift": "_swift",
        "php": "_php",
        "kotlin": "_kotlin",
        "react": "_react",
        "flutter": "_flutter",
    }
    assert tuple(selectors) == tuple(ROUTED_LANGUAGES)
    assert tuple(DEPRECATED_LANGUAGES) == ("javascript",)
    assert callable(toolchains._javascript)
    for language, selector in selectors.items():
        setattr(
            toolchains,
            selector,
            lambda language=language: ExactToolchain(
                language, "fixture", "/fixed/tool"
            ),
        )
    selected = [toolchains.exact_toolchain(language) for language in selectors]  # type: ignore[arg-type]
    assert [item.language for item in selected] == list(selectors)
    path = os.environ["PATH"].split(os.pathsep)
    assert "/opt/homebrew/Cellar/uv/0.11.16/bin" in path
    assert path[0].endswith("/.venv/bin")
    assert "/Users/stephen/.local/bin" not in path
    assert "/opt/homebrew/bin" not in path
    assert os.environ["UV_OFFLINE"] == "1"
    assert os.environ["UV_PYTHON_DOWNLOADS"] == "never"
    return 0
