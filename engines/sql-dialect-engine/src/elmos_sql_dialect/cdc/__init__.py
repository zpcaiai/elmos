"""CDC Reconciliation and Heterogeneous Data Comparison Package.

Includes:
- SchemaComparator: Heterogeneous database schema and type mapping verification
- DataComparator: Chunk-based full snapshot hash validation and row-level diffing
- EventComparator: Incremental transaction event stream ordering and replay verification
- CdcReconciliationReport: Machine-readable evidence reporting
"""

from .data_comparator import (
    ChunkDiffResult,
    DataComparator,
    RowDiff,
    SnapshotCompareReport,
    hash_normalized_string,
    hash_rows,
    normalize_cell_value,
    normalize_row_dict,
)
from .event_comparator import (
    CdcEvent,
    CdcOpType,
    EventComparator,
    EventReconciliationReport,
    EventStreamAnomaly,
)
from .reporter import CdcReconciliationReport, CdcReporter
from .schema_comparator import (
    ColumnDiff,
    ColumnSchema,
    DiffStatus,
    ForeignKeySpec,
    SchemaComparator,
    SchemaDiffReport,
    SchemaDiffResult,
    TableSchema,
)

__all__ = [
    "CdcEvent",
    "CdcOpType",
    "CdcReconciliationReport",
    "CdcReporter",
    "ChunkDiffResult",
    "ColumnDiff",
    "ColumnSchema",
    "DataComparator",
    "DiffStatus",
    "EventComparator",
    "EventReconciliationReport",
    "EventStreamAnomaly",
    "ForeignKeySpec",
    "RowDiff",
    "SchemaComparator",
    "SchemaDiffReport",
    "SchemaDiffResult",
    "SnapshotCompareReport",
    "TableSchema",
    "hash_normalized_string",
    "hash_rows",
    "normalize_cell_value",
    "normalize_row_dict",
]
