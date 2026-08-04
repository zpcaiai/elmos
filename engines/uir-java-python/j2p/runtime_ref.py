"""Load the generated-code runtime as a module for compile-time queries.

The emitter needs to know which Java exception names the runtime can actually
represent.  Hardcoding a second copy of that list in the emitter would let the
two drift, and the drift would show up as a translation that catches an
exception the runtime never raises.  So the emitter asks the runtime itself.

``runtime/j2p_runtime.py`` is not importable by name from here: it is shipped
*next to generated code*, not installed as a package.  It is therefore loaded by
path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

RUNTIME_PATH = Path(__file__).resolve().parent.parent / "runtime" / "j2p_runtime.py"

_cached: ModuleType | None = None


def runtime_module() -> ModuleType:
    global _cached
    if _cached is not None:
        return _cached
    if not RUNTIME_PATH.is_file():
        raise FileNotFoundError(f"runtime not found at {RUNTIME_PATH}")
    spec = importlib.util.spec_from_file_location("j2p_runtime", RUNTIME_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load runtime from {RUNTIME_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("j2p_runtime", module)
    spec.loader.exec_module(module)
    _cached = module
    return module


def supported_throwables() -> dict[str, str]:
    """Map Java simple name -> runtime class name."""

    runtime = runtime_module()
    return {
        name: cls.__name__
        for name, cls in runtime.EXCEPTION_BY_SIMPLE_NAME.items()
    }
