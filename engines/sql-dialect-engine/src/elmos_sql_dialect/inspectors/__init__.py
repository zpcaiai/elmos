"""Database catalog inspectors for live introspection."""

from .mysql_inspector import MysqlCatalogInspector
from .postgres_inspector import LiveCatalogInspector, PostgresCatalogInspector

PostgresInspector = PostgresCatalogInspector
MysqlInspector = MysqlCatalogInspector

__all__ = [
    "LiveCatalogInspector",
    "PostgresCatalogInspector",
    "PostgresInspector",
    "MysqlCatalogInspector",
    "MysqlInspector",
]
