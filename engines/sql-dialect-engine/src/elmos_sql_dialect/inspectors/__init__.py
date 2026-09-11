"""Database catalog inspectors for live introspection."""

from .postgres_inspector import LiveCatalogInspector, PostgresCatalogInspector

PostgresInspector = PostgresCatalogInspector

__all__ = ["LiveCatalogInspector", "PostgresCatalogInspector", "PostgresInspector"]

