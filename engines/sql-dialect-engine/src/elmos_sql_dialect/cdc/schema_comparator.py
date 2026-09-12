"""Schema Comparator for CDC Migration Verification across Heterogeneous Databases.

Compares source vs target table schemas, column types (using canonical type mapping),
primary keys, nullable constraints, and unique constraints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from elmos_sql_dialect.models import CanonicalType, Column, Table


class DiffStatus(StrEnum):
    MATCH = "MATCH"
    TYPE_COMPATIBLE = "TYPE_COMPATIBLE"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    NULLABLE_MISMATCH = "NULLABLE_MISMATCH"
    MISSING_IN_TARGET = "MISSING_IN_TARGET"
    EXTRA_IN_TARGET = "EXTRA_IN_TARGET"
    CONSTRAINT_MISMATCH = "CONSTRAINT_MISMATCH"


@dataclass(frozen=True)
class ColumnSchema:
    name: str
    canonical_type: CanonicalType
    raw_type: str = ""
    precision: int | None = None
    scale: int | None = None
    length: int | None = None
    nullable: bool = True
    default_value: str | None = None
    is_primary_key: bool = False
    auto_increment: bool = False


@dataclass(frozen=True)
class ForeignKeySpec:
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]


@dataclass
class TableSchema:
    table_name: str
    columns: dict[str, ColumnSchema] = field(default_factory=dict)
    primary_key: tuple[str, ...] = ()
    unique_constraints: tuple[tuple[str, ...], ...] = ()
    foreign_keys: tuple[ForeignKeySpec, ...] = ()
    schema_name: str | None = None

    def add_column(self, col: ColumnSchema) -> None:
        self.columns[col.name.lower()] = col


@dataclass
class ColumnDiff:
    column_name: str
    status: DiffStatus
    source_type: str | None = None
    target_type: str | None = None
    source_nullable: bool | None = None
    target_nullable: bool | None = None
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "columnName": self.column_name,
            "status": self.status.value,
            "sourceType": self.source_type,
            "targetType": self.target_type,
            "sourceNullable": self.source_nullable,
            "targetNullable": self.target_nullable,
            "details": self.details,
        }


@dataclass
class ConstraintDiff:
    constraint_type: str
    status: DiffStatus
    source_spec: Any
    target_spec: Any
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraintType": self.constraint_type,
            "status": self.status.value,
            "sourceSpec": self.source_spec,
            "targetSpec": self.target_spec,
            "details": self.details,
        }


@dataclass
class SchemaDiffResult:
    table_name: str
    is_compatible: bool
    is_identical: bool
    column_diffs: list[ColumnDiff] = field(default_factory=list)
    constraint_diffs: list[ConstraintDiff] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tableName": self.table_name,
            "isCompatible": self.is_compatible,
            "isIdentical": self.is_identical,
            "columnDiffs": [c.to_dict() for c in self.column_diffs],
            "constraintDiffs": [cd.to_dict() for cd in self.constraint_diffs],
            "summary": self.summary,
        }

    @property
    def divergence_count(self) -> int:
        col_div = len([c for c in self.column_diffs if c.status != DiffStatus.MATCH])
        con_div = len([cd for cd in self.constraint_diffs if cd.status != DiffStatus.MATCH])
        return col_div + con_div


type SchemaDiffReport = SchemaDiffResult


# Type normalization regexes
_PARAM_RE = re.compile(r"^([A-Z0-9_\s]+)(?:\(\s*(\d+)(?:\s*,\s*(\d+))?\s*(?:CHAR|BYTE)?\s*\))?", re.IGNORECASE)


class SchemaComparator:
    """Evaluates schema equivalence and compatibility between source and target."""

    @staticmethod
    def normalize_type_str(type_str: str) -> tuple[CanonicalType, int | None, int | None, int | None]:
        """Normalize raw SQL type string into (CanonicalType, precision, scale, length)."""
        clean = type_str.strip().upper()
        # Handle array types
        if clean.endswith("[]"):
            return CanonicalType.ARRAY, None, None, None

        match = _PARAM_RE.match(clean)
        base = match.group(1).strip() if match else clean
        p1 = int(match.group(2)) if match and match.group(2) else None
        p2 = int(match.group(3)) if match and match.group(3) else None

        # Type mapping rules
        if base in ("BIGINT", "BIGSERIAL", "INT8", "NUMBER") and (p1 == 19 or p1 is None and "BIG" in base):
            return CanonicalType.INT64, 19, 0, None
        if base in ("INTEGER", "INT", "INT4", "SERIAL", "MEDIUMINT") or (base == "NUMBER" and p1 == 10):
            return CanonicalType.INT32, 10, 0, None
        if base in ("SMALLINT", "INT2", "SMALLSERIAL") or (base == "NUMBER" and p1 == 5):
            return CanonicalType.INT16, 5, 0, None
        if base in ("BOOLEAN", "BOOL", "BIT") or (base in ("NUMBER", "TINYINT") and p1 == 1):
            return CanonicalType.BOOLEAN, None, None, None
        if base in ("DOUBLE", "DOUBLE PRECISION", "FLOAT8", "FLOAT", "REAL", "BINARY_DOUBLE", "FLOAT64"):
            return CanonicalType.FLOAT64, None, None, None
        if base in ("DECIMAL", "NUMERIC", "NUMBER"):
            prec = p1 if p1 is not None else 18
            scale = p2 if p2 is not None else 0
            # Special case for Oracle NUMBER(p) without scale -> if p <= 5 int16, p <= 10 int32, p <= 19 int64
            if p2 is None or p2 == 0:
                if p1 == 1:
                    return CanonicalType.BOOLEAN, None, None, None
                if p1 is not None and p1 <= 5:
                    return CanonicalType.INT16, p1, 0, None
                if p1 is not None and p1 <= 10:
                    return CanonicalType.INT32, p1, 0, None
                if p1 is not None and p1 <= 19:
                    return CanonicalType.INT64, p1, 0, None
            return CanonicalType.DECIMAL, prec, scale, None
        if base in ("VARCHAR", "VARCHAR2", "NVARCHAR", "CHARACTER VARYING"):
            length = p1 if p1 is not None else 255
            return CanonicalType.VARCHAR, None, None, length
        if base in ("CHAR", "NCHAR", "CHARACTER"):
            length = p1 if p1 is not None else 1
            return CanonicalType.CHAR, None, None, length
        is_text_base = base in ("TEXT", "CLOB", "LONGTEXT", "TINYTEXT", "MEDIUMTEXT")
        if is_text_base or (base in ("VARCHAR", "NVARCHAR") and "MAX" in clean):
            return CanonicalType.TEXT, None, None, None
        if base in ("DATE",):
            return CanonicalType.DATE, None, None, None
        is_ts_base = base in (
            "TIMESTAMP",
            "TIMESTAMPTZ",
            "TIMESTAMP WITH TIME ZONE",
            "TIMESTAMP WITHOUT TIME ZONE",
            "DATETIME",
        )
        if is_ts_base:
            return CanonicalType.TIMESTAMP, None, None, None
        if base in ("JSON", "JSONB"):
            return CanonicalType.JSON, None, None, None
        if base in ("BYTEA", "BLOB", "BINARY", "VARBINARY"):
            return CanonicalType.BINARY, None, None, p1
        if base in ("UUID",):
            return CanonicalType.UUID, None, None, None

        # Fallback to VARCHAR or TEXT
        return CanonicalType.VARCHAR, None, None, 255

    @classmethod
    def from_column_model(cls, col: Column, is_pk: bool = False) -> ColumnSchema:
        """Construct ColumnSchema from certified elmos_sql_dialect Column."""
        return ColumnSchema(
            name=col.name,
            canonical_type=col.type_ref.canonical_type,
            raw_type=col.type_ref.canonical_type.value,
            precision=col.type_ref.precision,
            scale=col.type_ref.scale,
            length=col.type_ref.length,
            nullable=col.nullable,
            default_value=col.default.literal if col.default else None,
            is_primary_key=is_pk,
            auto_increment=col.auto_increment,
        )

    @classmethod
    def from_table_model(cls, table: Table) -> TableSchema:
        """Construct TableSchema from certified Table AST model."""
        pk_set = set(col.lower() for col in table.primary_key)
        schema = TableSchema(
            table_name=table.name,
            schema_name=table.schema,
            primary_key=tuple(col.lower() for col in table.primary_key),
            unique_constraints=tuple(tuple(col.lower() for col in uc) for uc in table.unique_constraints),
            foreign_keys=tuple(
                ForeignKeySpec(
                    columns=tuple(c.lower() for c in fk.columns),
                    ref_table=fk.ref_table,
                    ref_columns=tuple(rc.lower() for rc in fk.ref_columns),
                )
                for fk in table.foreign_keys
            ),
        )
        for col in table.columns:
            schema.add_column(cls.from_column_model(col, is_pk=(col.name.lower() in pk_set)))
        return schema

    def compare_tables(self, source: TableSchema, target: TableSchema) -> SchemaDiffResult:
        """Compare source and target table schemas."""
        column_diffs: list[ColumnDiff] = []
        constraint_diffs: list[ConstraintDiff] = []
        is_compatible = True
        is_identical = True

        src_cols = source.columns
        tgt_cols = target.columns

        # Check all source columns in target
        for col_name, src_col in src_cols.items():
            if col_name not in tgt_cols:
                column_diffs.append(
                    ColumnDiff(
                        column_name=col_name,
                        status=DiffStatus.MISSING_IN_TARGET,
                        source_type=src_col.canonical_type.value,
                        source_nullable=src_col.nullable,
                        details="Column exists in source but is missing in target table.",
                    )
                )
                is_compatible = False
                is_identical = False
                continue

            tgt_col = tgt_cols[col_name]
            col_diff = self._compare_column(src_col, tgt_col)
            column_diffs.append(col_diff)
            if col_diff.status == DiffStatus.TYPE_MISMATCH:
                is_compatible = False
                is_identical = False
            elif col_diff.status in (DiffStatus.TYPE_COMPATIBLE, DiffStatus.NULLABLE_MISMATCH):
                is_identical = False
                # If target is NOT NULL while source is nullable, target is stricter -> potential write failure
                if src_col.nullable and not tgt_col.nullable:
                    is_compatible = False

        # Check for extra columns in target
        for col_name, tgt_col in tgt_cols.items():
            if col_name not in src_cols:
                # If target extra column is NOT NULL with no default, it's incompatible
                extra_compatible = tgt_col.nullable or (tgt_col.default_value is not None)
                if not extra_compatible:
                    is_compatible = False
                is_identical = False
                column_diffs.append(
                    ColumnDiff(
                        column_name=col_name,
                        status=DiffStatus.EXTRA_IN_TARGET,
                        target_type=tgt_col.canonical_type.value,
                        target_nullable=tgt_col.nullable,
                        details=(
                            f"Extra column in target table (nullable={tgt_col.nullable}, "
                            f"default={tgt_col.default_value})."
                        ),
                    )
                )

        # Primary Key comparison
        src_pk = tuple(c.lower() for c in source.primary_key)
        tgt_pk = tuple(c.lower() for c in target.primary_key)
        if src_pk == tgt_pk:
            if src_pk:
                constraint_diffs.append(
                    ConstraintDiff(
                        constraint_type="PRIMARY_KEY",
                        status=DiffStatus.MATCH,
                        source_spec=src_pk,
                        target_spec=tgt_pk,
                        details="Primary key definitions match exactly.",
                    )
                )
        else:
            is_compatible = False
            is_identical = False
            constraint_diffs.append(
                ConstraintDiff(
                    constraint_type="PRIMARY_KEY",
                    status=DiffStatus.CONSTRAINT_MISMATCH,
                    source_spec=src_pk,
                    target_spec=tgt_pk,
                    details=f"Primary key mismatch: source={src_pk} vs target={tgt_pk}",
                )
            )

        # Unique Constraints comparison
        src_uq = {tuple(sorted(c.lower() for c in u)) for u in source.unique_constraints}
        tgt_uq = {tuple(sorted(c.lower() for c in u)) for u in target.unique_constraints}
        if src_uq == tgt_uq:
            if src_uq:
                constraint_diffs.append(
                    ConstraintDiff(
                        constraint_type="UNIQUE",
                        status=DiffStatus.MATCH,
                        source_spec=list(src_uq),
                        target_spec=list(tgt_uq),
                        details="Unique constraints match.",
                    )
                )
        else:
            is_identical = False
            missing_uq = src_uq - tgt_uq
            extra_uq = tgt_uq - src_uq
            constraint_diffs.append(
                ConstraintDiff(
                    constraint_type="UNIQUE",
                    status=DiffStatus.CONSTRAINT_MISMATCH,
                    source_spec=list(src_uq),
                    target_spec=list(tgt_uq),
                    details=(
                        f"Unique constraint divergence: missing_in_target={list(missing_uq)}, "
                        f"extra_in_target={list(extra_uq)}"
                    ),
                )
            )

        summary = {
            "totalSourceColumns": len(src_cols),
            "totalTargetColumns": len(tgt_cols),
            "matchingColumns": sum(1 for c in column_diffs if c.status == DiffStatus.MATCH),
            "compatibleColumns": sum(1 for c in column_diffs if c.status == DiffStatus.TYPE_COMPATIBLE),
            "mismatchColumns": sum(1 for c in column_diffs if c.status == DiffStatus.TYPE_MISMATCH),
            "missingTargetColumns": sum(1 for c in column_diffs if c.status == DiffStatus.MISSING_IN_TARGET),
            "extraTargetColumns": sum(1 for c in column_diffs if c.status == DiffStatus.EXTRA_IN_TARGET),
            "constraintMismatches": sum(1 for cd in constraint_diffs if cd.status == DiffStatus.CONSTRAINT_MISMATCH),
        }

        return SchemaDiffResult(
            table_name=source.table_name,
            is_compatible=is_compatible,
            is_identical=is_identical,
            column_diffs=column_diffs,
            constraint_diffs=constraint_diffs,
            summary=summary,
        )

    def _compare_column(self, src: ColumnSchema, tgt: ColumnSchema) -> ColumnDiff:
        """Check column type and nullability match/compatibility."""
        src_type = src.canonical_type
        tgt_type = tgt.canonical_type

        # Exact type match
        if src_type == tgt_type:
            # Check length/precision capacity
            if src_type in (CanonicalType.VARCHAR, CanonicalType.CHAR):
                if src.length is not None and tgt.length is not None and tgt.length < src.length:
                    return ColumnDiff(
                        column_name=src.name,
                        status=DiffStatus.TYPE_MISMATCH,
                        source_type=f"{src_type.value}({src.length})",
                        target_type=f"{tgt_type.value}({tgt.length})",
                        source_nullable=src.nullable,
                        target_nullable=tgt.nullable,
                        details=f"Target length {tgt.length} is smaller than source length {src.length}.",
                    )
            elif src_type == CanonicalType.DECIMAL:
                if (
                    src.precision is not None
                    and tgt.precision is not None
                    and (tgt.precision < src.precision or (src.scale or 0) > (tgt.scale or 0))
                ):
                    return ColumnDiff(
                        column_name=src.name,
                        status=DiffStatus.TYPE_MISMATCH,
                        source_type=f"DECIMAL({src.precision},{src.scale})",
                        target_type=f"DECIMAL({tgt.precision},{tgt.scale})",
                        source_nullable=src.nullable,
                        target_nullable=tgt.nullable,
                        details="Target decimal precision or scale is insufficient.",
                    )

            if src.nullable != tgt.nullable:
                return ColumnDiff(
                    column_name=src.name,
                    status=DiffStatus.NULLABLE_MISMATCH,
                    source_type=src_type.value,
                    target_type=tgt_type.value,
                    source_nullable=src.nullable,
                    target_nullable=tgt.nullable,
                    details=f"Nullable divergence: source={src.nullable} vs target={tgt.nullable}",
                )

            return ColumnDiff(
                column_name=src.name,
                status=DiffStatus.MATCH,
                source_type=src_type.value,
                target_type=tgt_type.value,
                source_nullable=src.nullable,
                target_nullable=tgt.nullable,
                details="Column type and constraints match.",
            )

        # Compatible promotions (e.g. INT32 -> INT64, VARCHAR -> TEXT)
        compatible = False
        if src_type == CanonicalType.INT32 and tgt_type == CanonicalType.INT64:
            compatible = True
        elif src_type == CanonicalType.INT16 and tgt_type in (CanonicalType.INT32, CanonicalType.INT64):
            compatible = True
        elif src_type in (CanonicalType.CHAR, CanonicalType.VARCHAR) and tgt_type == CanonicalType.TEXT:
            compatible = True
        elif src_type == CanonicalType.CHAR and tgt_type == CanonicalType.VARCHAR:
            compatible = True

        if compatible:
            return ColumnDiff(
                column_name=src.name,
                status=DiffStatus.TYPE_COMPATIBLE,
                source_type=src_type.value,
                target_type=tgt_type.value,
                source_nullable=src.nullable,
                target_nullable=tgt.nullable,
                details=f"Target type {tgt_type.value} safely accommodates source type {src_type.value}.",
            )

        return ColumnDiff(
            column_name=src.name,
            status=DiffStatus.TYPE_MISMATCH,
            source_type=src_type.value,
            target_type=tgt_type.value,
            source_nullable=src.nullable,
            target_nullable=tgt.nullable,
            details=f"Incompatible types: source is {src_type.value}, target is {tgt_type.value}.",
        )


