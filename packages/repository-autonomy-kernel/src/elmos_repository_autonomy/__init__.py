"""Fail-closed implementation of the Elmos Repository Autonomy Kernel v2."""

from .adapters import ADAPTERS, CONFORMANCE_CASES
from .catalog import PACKAGE_ID, PACKAGE_VERSION, SKILL_NAMES, SKILL_SPECS
from .dispatcher import AutonomyRuntime, DispatchContext, dispatch
from .errors import ContractError, KernelError
from .models import DispatchResult, Status
from .routes import GOLDEN_ROUTES, route_definition
from .schema_registry import SCHEMA_NAMES, SchemaRegistry
from .storage import DurableStore

__version__ = PACKAGE_VERSION

__all__ = [
    "ADAPTERS",
    "CONFORMANCE_CASES",
    "GOLDEN_ROUTES",
    "PACKAGE_ID",
    "PACKAGE_VERSION",
    "SCHEMA_NAMES",
    "SKILL_NAMES",
    "SKILL_SPECS",
    "AutonomyRuntime",
    "ContractError",
    "DispatchContext",
    "DispatchResult",
    "DurableStore",
    "KernelError",
    "SchemaRegistry",
    "Status",
    "dispatch",
    "route_definition",
]
