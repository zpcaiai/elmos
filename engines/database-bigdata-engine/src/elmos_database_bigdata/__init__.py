"""Database and Big Data plan-skeleton package.

The package initializer is intentionally inert. The console entry point uses the
small bootstrap trust surface before importing the runtime catalog or handlers.
"""

import sys

sys.dont_write_bytecode = True

from .bootstrap import initialize_repository_runtime

initialize_repository_runtime()

__all__: list[str] = []
