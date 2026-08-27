"""Versioned target capability facts used by route reporting.

This is a capability matrix, not a permission to lower one feature into a
different feature. ``exact_targets`` lists only native typed routes whose
semantics are preserved; missing provider/version evidence stays blocked.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import Dialect


@dataclass(frozen=True)
class TargetCapability:
    feature: str
    exact_targets: tuple[str, ...]
    blocked_targets: tuple[str, ...]
    rule: str


def target_capability_matrix() -> list[dict[str, object]]:
    features = (
        TargetCapability(
            "namespace_explicit_mapping",
            tuple(d.value for d in Dialect),
            (),
            "schema identity must come from an explicit digest-bound namespace profile",
        ),
        TargetCapability(
            "quoted_identifier",
            tuple(d.value for d in Dialect),
            (),
            "preserve source quote intent and use the target quote character",
        ),
        TargetCapability(
            "json_document",
            (Dialect.POSTGRES.value, Dialect.MYSQL.value),
            (Dialect.ORACLE.value, Dialect.TSQL.value),
            "plain JSON only; PostgreSQL JSONB binary semantics are never downgraded",
        ),
        TargetCapability(
            "jsonb_binary",
            (Dialect.POSTGRES.value,),
            (Dialect.MYSQL.value, Dialect.ORACLE.value, Dialect.TSQL.value),
            "PostgreSQL JSONB is exact only on PostgreSQL; it is never downgraded to JSON or TEXT",
        ),
        TargetCapability(
            "array_exact",
            (Dialect.POSTGRES.value,),
            (Dialect.MYSQL.value, Dialect.ORACLE.value, Dialect.TSQL.value),
            "element type, indexing, comparison and NULL semantics must all match",
        ),
        TargetCapability(
            "filtered_or_partial_index",
            (Dialect.POSTGRES.value, Dialect.TSQL.value),
            (Dialect.MYSQL.value, Dialect.ORACLE.value),
            "predicate and NULL filtering semantics must be native and exact",
        ),
        TargetCapability(
            "typed_expression_index",
            (Dialect.POSTGRES.value,),
            (Dialect.MYSQL.value, Dialect.ORACLE.value, Dialect.TSQL.value),
            "LOWER and one-level JSON text-path keys are retained in typed IR; "
            "target collation/JSON semantics must be proven",
        ),
        TargetCapability(
            "routine_trigger_action",
            (Dialect.POSTGRES.value,),
            (Dialect.MYSQL.value, Dialect.ORACLE.value, Dialect.TSQL.value),
            "timing, event, row/statement scope, OLD/NEW and action ABI are typed",
        ),
        TargetCapability(
            "row_security_control",
            (Dialect.POSTGRES.value,),
            (Dialect.MYSQL.value, Dialect.ORACLE.value, Dialect.TSQL.value),
            "ENABLE/FORCE/DISABLE/NO FORCE state is retained only on PostgreSQL; "
            "RLS is never downgraded to ordinary privileges",
        ),
        TargetCapability(
            "if_not_exists_table_or_schema",
            (Dialect.POSTGRES.value, Dialect.MYSQL.value),
            (Dialect.ORACLE.value, Dialect.TSQL.value),
            "rerun behavior is never emulated by DROP or another destructive statement",
        ),
        TargetCapability(
            "comment_metadata",
            (Dialect.POSTGRES.value, Dialect.MYSQL.value, Dialect.TSQL.value),
            (Dialect.ORACLE.value,),
            "object scope and required source type/catalogue evidence must be retained",
        ),
        TargetCapability(
            "mysql_text_prefix_index",
            (Dialect.MYSQL.value,),
            (Dialect.POSTGRES.value, Dialect.ORACLE.value, Dialect.TSQL.value),
            "requires an explicit source prefix and target length proof; never invent one",
        ),
    )
    return [asdict(item) for item in features]
