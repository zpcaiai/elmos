"""The package has two persistence schemas and only one of them runs.

This file exists because a recorded piece of consolidation debt turned out to
have the wrong shape. The note said "unify the two event logs: V001-V006 is the
control plane's, V007 is the capability core's". Measuring it says otherwise:
``autonomy_events`` is not a live log competing with the core's. Nothing in this
package ever writes to it, or reads it - and nothing writes ``autonomy_runs``
either, the root table it and twenty others foreign-key to. Twenty-two of the
thirty-seven tables a deployment gets have no writer at all.

What actually exists is a split:

* **SQLite** — ``storage.DurableStore``, 27 tables under bare names (``events``,
  ``runs``, ``leases``). ``AutonomyRuntime.store`` is always one of these, so
  every skill handler's persistence lands here.
* **PostgreSQL** — ``sql/migrations/``, 37 tables under ``autonomy_*``. Only
  sixteen have any Python behind them: ten written by ``PostgresWaveStore``,
  five by the capability core's adapters, plus the migration ledger.

So an operator who runs ``postgres-migrate`` gets 37 tables, 22 of which nothing
will ever write to, while their run history, leases and artifacts go to a SQLite
file under different names. A schema that advertises a control plane which is
not there is worse than a missing one: it is read, believed, backed up, and
audited.

Closing the split is an architecture decision, not a cleanup — either implement
the 21 against PostgreSQL or stop shipping them. These tests do not make that
decision. They stop it from being made silently: the gap is pinned by name, so
adding a table to one side without answering for the other fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
STORAGE = PACKAGE_ROOT / "src" / "elmos_repository_autonomy" / "storage.py"
MIGRATIONS = PACKAGE_ROOT / "sql" / "migrations"
SOURCE_ROOT = PACKAGE_ROOT / "src"

_SQLITE_CREATE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)", re.IGNORECASE)
_PG_CREATE = re.compile(r"^\s*create table if not exists\s+([a-z0-9_]+)",
                        re.IGNORECASE | re.MULTILINE)

#: The capability core's own tables. These are not part of the control-plane
#: split - they have adapters, a conformance suite and real-server durability
#: evidence - so they are excluded from the counterpart rules below.
CORE_TABLES = frozenset({
    "autonomy_kernel_event", "autonomy_kernel_kv", "autonomy_kernel_artifact",
    "autonomy_kernel_lease", "autonomy_kernel_lease_watermark",
})

#: PostgreSQL tables that exist in the migrations and have no writer or reader
#: anywhere in this package. Pinned by name rather than counted, so that
#: implementing one is a deliberate deletion from this list and adding another
#: is a deliberate addition to it.
UNIMPLEMENTED_IN_POSTGRES = frozenset({
    "autonomy_acceptance_decisions",
    "autonomy_adapter_conformance",
    "autonomy_approvals",
    "autonomy_artifacts",
    "autonomy_cache_entries",
    "autonomy_capability_packages",
    "autonomy_change_edges",
    "autonomy_change_nodes",
    "autonomy_checkpoints",
    "autonomy_cost_events",
    "autonomy_elo_ratings",
    "autonomy_eval_runs",
    "autonomy_events",
    "autonomy_evidence",
    "autonomy_findings",
    "autonomy_leases",
    "autonomy_policy_decisions",
    "autonomy_repository_snapshots",
    "autonomy_runs",
    "autonomy_semantic_indices",
    "autonomy_steps",
    "autonomy_tool_calls",
    "autonomy_validations",
})

#: SQLite tables with no ``autonomy_*`` counterpart in the migrations. One
#: entry, and it is the honest kind: process-local counters that were never
#: meant to be durable across hosts.
SQLITE_ONLY = frozenset({"metrics"})


def _sqlite_tables() -> set[str]:
    return set(_SQLITE_CREATE.findall(STORAGE.read_text(encoding="utf-8")))


def _postgres_tables() -> set[str]:
    tables: set[str] = set()
    for path in sorted(MIGRATIONS.glob("V*.sql")):
        tables |= set(_PG_CREATE.findall(path.read_text(encoding="utf-8")))
    return tables


def _python_code_text() -> str:
    """Every Python source line with ``#`` comments removed.

    A table named only in a comment is documented, not implemented - and
    ``adapters/postgres.py`` names ``autonomy_events`` in a comment explaining
    why the capability core does *not* use it. Matching raw file text would read
    that explanation as a writer and hide the very table it is explaining.

    Only comments are stripped. String literals are kept, because that is how
    every SQL statement in this package is written - including the multi-line
    ones in ``PostgresWaveStore``, which an over-clever docstring filter drops
    along with the nine tables they are the sole writers of.
    """

    import io
    import tokenize

    chunks: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        except (tokenize.TokenError, IndentationError):  # pragma: no cover
            chunks.append(source)
            continue
        chunks.extend(
            token.string for token in tokens if token.type != tokenize.COMMENT
        )
    return "\n".join(chunks)


def test_the_unimplemented_postgres_tables_are_exactly_the_pinned_set():
    """22 of 37 tables in the shipped schema have nothing behind them.

    ``autonomy_runs`` is in here, which is the sharpest part: it is the root
    every other control-plane table foreign-keys to. Nothing creates a run row,
    so the twenty-one tables hanging off it could not hold data even if
    something tried to write them.

    If this fails because the set shrank, someone implemented one - delete it
    from the list. If it grew, someone added a table to the migrations without
    a writer, which is how the other 22 got there.
    """

    python = _python_code_text()
    unimplemented = {
        table for table in _postgres_tables()
        if table not in CORE_TABLES
        and table != "autonomy_schema_migrations"
        and not re.search(rf"\b{table}\b", python)
    }
    assert unimplemented == UNIMPLEMENTED_IN_POSTGRES


def test_every_sqlite_table_has_a_named_postgres_counterpart_or_is_declared_local():
    """The naming rule is `autonomy_` + the SQLite name, and it must stay total.

    A SQLite table with no counterpart is data that can never move to
    PostgreSQL, and finding that out during a migration is finding it out too
    late.
    """

    sqlite = _sqlite_tables()
    postgres = _postgres_tables()
    missing = {
        table for table in sqlite
        if table not in SQLITE_ONLY and f"autonomy_{table}" not in postgres
    }
    assert missing == set(), (
        f"SQLite tables with no PostgreSQL counterpart: {sorted(missing)}"
    )
    # And the declared-local list must not rot into a place to hide new ones.
    assert SQLITE_ONLY <= sqlite


def test_the_runtime_store_is_sqlite_and_the_wave_store_is_the_only_postgres_path():
    """Pins the fact the docs now state, so the docs cannot drift from the code.

    ``AutonomyRuntime.store`` is a ``DurableStore``; ``control_store`` is the
    only thing a ``--postgres-control-service`` flag reaches. Every skill
    handler persists through the first.
    """

    from elmos_repository_autonomy.dispatcher import AutonomyRuntime
    from elmos_repository_autonomy.storage import DurableStore

    runtime = AutonomyRuntime()
    assert isinstance(runtime.store, DurableStore)
    # With no control store configured, it falls back to the same SQLite store -
    # so a deployment that forgets the flag silently has no PostgreSQL at all.
    assert runtime.control_store is runtime.store
