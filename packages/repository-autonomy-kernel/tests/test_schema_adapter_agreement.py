"""The SQL the adapters write must name tables the migrations create.

This exists because of a real near-miss. Renaming the capability core's tables
(to stop `autonomy_event` sitting next to the control plane's `autonomy_events`)
updated the migration and the adapter but missed the TRUNCATE in a test helper
and a DELETE in the evidence script. Every one of the 1,543 in-memory tests
still passed; only a real server said `relation does not exist`.

So the agreement is asserted statically, from the files themselves, and holds
whether or not a PostgreSQL server is reachable.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = PACKAGE_ROOT / "sql" / "migrations"
CONSOLIDATED = PACKAGE_ROOT / "sql" / "001_autonomy_kernel.sql"

#: Files that issue SQL against the capability core's own tables.
CORE_SQL_SOURCES = (
    PACKAGE_ROOT / "src" / "elmos_autonomy_kernel" / "adapters" / "postgres.py",
    PACKAGE_ROOT / "scripts" / "durability_evidence.py",
    PACKAGE_ROOT / "tests" / "test_adapter_conformance.py",
)

_CREATE = re.compile(r"^\s*create table if not exists\s+([a-z0-9_]+)", re.IGNORECASE | re.MULTILINE)
#: Any identifier that looks like one of this package's tables, wherever it is
#: mentioned in a SQL string - FROM, INTO, UPDATE, TRUNCATE, DELETE, ON.
_REFERENCED = re.compile(r"\bautonomy_[a-z0-9_]+\b")

#: Identifiers that share the table prefix but are not tables.
_NOT_TABLES = re.compile(r"^autonomy_(kernel_)?[a-z0-9_]*(_idempotency|_recorded_at|_positive"
                         r"|_unique|_shape|_agrees|_core_streams)$")


def _declared_tables(path: Path) -> set[str]:
    return {match.lower() for match in _CREATE.findall(path.read_text(encoding="utf-8"))}


def _all_declared() -> set[str]:
    declared: set[str] = set()
    for migration in sorted(MIGRATIONS.glob("V*.sql")):
        declared |= _declared_tables(migration)
    return declared


def test_the_consolidated_schema_is_exactly_the_union_of_the_migrations():
    """001 is documented as the whole schema; a drifting copy is worse than none.

    A caller who bootstraps from the single file and a caller who applies the
    migrations must end up with the same database, or one of them is running
    against a schema nobody tested.
    """

    assert _declared_tables(CONSOLIDATED) == _all_declared()


def test_every_table_the_core_adapters_name_actually_exists():
    """The check the rename slipped past."""

    declared = _all_declared()
    missing: dict[str, set[str]] = {}
    for source in CORE_SQL_SOURCES:
        referenced = {
            name for name in _REFERENCED.findall(source.read_text(encoding="utf-8"))
            if not _NOT_TABLES.match(name)
        }
        unknown = referenced - declared
        if unknown:
            missing[source.name] = unknown
    assert not missing, f"SQL names tables no migration creates: {missing}"


def test_the_two_event_logs_keep_distinguishable_names():
    """`autonomy_event` beside `autonomy_events` is a wrong-table bug in waiting.

    The package deliberately carries two logs - the control plane's, keyed by a
    run uuid, and the capability core's, chain-verified over an arbitrary stream
    id. They are allowed to coexist; they are not allowed to be one character
    apart.
    """

    declared = _all_declared()
    control_plane = {name for name in declared if not name.startswith("autonomy_kernel_")}
    core = {name for name in declared if name.startswith("autonomy_kernel_")}
    assert core, "the capability core's tables are missing entirely"

    for core_table in core:
        stem = core_table[len("autonomy_kernel_"):]
        assert f"autonomy_{stem}" not in control_plane, (
            f"{core_table} differs from autonomy_{stem} only by the prefix"
        )
