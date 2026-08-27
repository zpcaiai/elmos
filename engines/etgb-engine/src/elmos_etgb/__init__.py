"""Repository-owned ETGB runtime.

The source package under ``skills/subskills`` is treated as immutable input.
This package contains the executable implementation used by Elmos.
"""

__version__ = "1.0.0+elmos"

from .canonical import canonical_json, digest_json, sha256_bytes, sha256_file

__all__ = ["canonical_json", "digest_json", "sha256_bytes", "sha256_file"]
