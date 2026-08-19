"""Mutable orchestration state: SQLite locally, PostgreSQL in production.

Immutable bytes never enter these tables. Everything here is a row that can
legally change: run and node state, staged-file lifecycle, Action Cache
mappings, checkpoints, pins, receipts, and the transactional outbox.
"""

from __future__ import annotations

from .records import (
    ActionCacheRecord,
    ArtifactRecord,
    CheckpointRecord,
    NodeRecord,
    RunRecord,
    StagedFileRecord,
)
from .store import MetadataStore, PostgresMetadataStore, SqliteMetadataStore, open_store

__all__ = [
    "ActionCacheRecord",
    "ArtifactRecord",
    "CheckpointRecord",
    "MetadataStore",
    "NodeRecord",
    "PostgresMetadataStore",
    "RunRecord",
    "SqliteMetadataStore",
    "StagedFileRecord",
    "open_store",
]
