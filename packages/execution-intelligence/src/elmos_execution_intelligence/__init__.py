"""Elmos execution intelligence: token, cost, runtime, and human-baseline forecasting.

The package is deliberately dependency-free (standard library only) so it can run
inside the same pinned, symlink-free toolchain the rest of elmos uses.
"""

__version__ = "1.0.0"
SCHEMA_VERSION = "1.0.0"

__all__ = ["__version__", "SCHEMA_VERSION"]
