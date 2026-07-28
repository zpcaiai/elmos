"""elmos-sql-dialect: certified-ddl-v1 SQL DDL dialect translation.

See README.md for the certified subset boundary and why an unbounded "100%
success on any SQL" target is not offered.
"""
from __future__ import annotations

__all__ = ["engine", "models", "parser", "emitter", "validator", "dialects", "toolchains"]
