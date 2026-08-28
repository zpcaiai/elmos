"""Wire `catalog.py` and `reserved_words.py` into the sql-dialect engine.

Both modules were written in a session that ran in parallel with the one that
added `advanced.py` / `routine.py` / `emit_create_schema` / the T-SQL regex
renderer. Overwriting that session's `emitter.py` would have destroyed all of
it, so the two new modules were delivered unwired and this script does the
join -- against whatever `emitter.py` and `engine.py` look like when it runs,
not against a snapshot.

What it buys, measured against a real MySQL 8.0.46 over the 97-file corpus:

    emission defects the server rejected      201  ->  0

Three hooks:

  1. `emit_create_index` / `emit_alter_table` take an optional `catalog`.
     With one, a MySQL key over a TEXT column fails closed (error 1170);
     without one, nothing changes -- absence of evidence must not become
     evidence of absence.
  2. `ALTER ... ADD CONSTRAINT ... FOREIGN KEY` with no referenced column list
     recovers the target's primary key from the catalogue for MySQL, which
     rejects the bare spelling there (error 1239) though it accepts it inside
     CREATE TABLE. No catalogue -> fail closed rather than guess a column name.
  3. `_require_mysql_identifiers` is generalised to every dialect via
     `reserved_words.RESERVED_WORDS`. The in-tree MySQL list holds 5 words;
     the replacement holds 261, is a strict superset, and every one of them was
     probed against a real server. Oracle (110) and SQL Server (185) come along,
     labelled `VENDOR_DOCUMENTED` until `evidence/verify_reserved_words.py`
     is run against a real instance.

Idempotent: re-running is a no-op. Anchors are asserted unique, so a file that
has drifted too far fails loudly instead of being half-patched.

    python apply_catalog_wiring.py --engine engines/sql-dialect-engine [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


class PatchError(RuntimeError):
    pass


def substitute(text: str, old: str, new: str, what: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{what}: anchor found {count} times, expected exactly 1")
    return text.replace(old, new, 1)


OLD_TSQL_PAIR = 'def test_sql_server_fails_closed_rather_than_degrading_to_like() -> None:\n    report = translate_ddl(HASH_CHECK, "postgres", "tsql", statement_kind="TABLE")\n    assert report["status"] == "BLOCKED"\n    assert report["reasonCode"] == "CERTIFIED_DDL_REGEX_CHECK_UNREACHABLE_ON_TARGET"\n    assert report["emitted"] is None\n\n\ndef test_the_sql_server_refusal_says_why_like_is_not_a_substitute() -> None:\n    report = translate_ddl(HASH_CHECK, "postgres", "tsql", statement_kind="TABLE")\n    assert "LIKE" in report["reason"]\n    assert "bounded quantifier" in report["reason"]'

NEW_TSQL_PAIR = 'def test_sql_server_lowers_the_corpus_patterns_with_a_binary_collation() -> None:\n    """SQL Server has no regex predicate, so an in-table pattern is LOWERED.\n\n    Two properties carry the guarantee and both are asserted, because either\n    alone would silently widen the accepted language: a BINARY collation\n    (SQL Server\'s default is case-insensitive -- the same trap MySQL has) and\n    an exact DATALENGTH (its `=` ignores trailing spaces).\n\n    NOTE: this lowering has never been executed. No SQL Server instance is\n    reachable from the container these agents run in, so it rests on the\n    documented grammar alone -- see evidence/README.md for how to close that.\n    """\n    report = translate_ddl(HASH_CHECK, "postgres", "tsql", statement_kind="TABLE")\n    assert report["status"] == "PASSED", report["reasonCode"]\n    assert "BIN2" in report["emitted"]\n    assert "DATALENGTH" in report["emitted"]\n\n\ndef test_a_pattern_outside_the_lowering_table_still_fails_closed_on_sql_server() -> None:\n    """The fail-closed half of the original guarantee, which still holds."""\n    report = translate_ddl(\n        "CREATE TABLE t (h VARCHAR(64), CHECK (h ~ \'^(alpha|beta)$\'))",\n        "postgres",\n        "tsql",\n        statement_kind="TABLE",\n    )\n    assert report["status"] == "BLOCKED"\n    assert report["reasonCode"] == "CERTIFIED_DDL_REGEX_CHECK_UNREACHABLE_ON_TARGET"\n    assert report["emitted"] is None'


def retarget_reference_test(text: str) -> str:
    """Retarget the test asserting a bare `REFERENCES t` emits for MySQL.

    A real server rejects that in ADD CONSTRAINT (error 1239). The oracle and
    tsql halves of the assertion still hold and are kept.
    """
    stale = ('@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])\n'
             "def test_a_reference_without_a_column_list_does_not_emit_empty_parentheses(")
    if stale not in text:
        return text
    return text.replace(
        stale,
        "# MySQL moved out of this list: it rejects the bare spelling in\n"
        "# ADD CONSTRAINT (error 1239). See test_catalog.py for the\n"
        "# catalogue-backed recovery and the fail-closed path.\n"
        '@pytest.mark.parametrize("target", ["oracle", "tsql"])\n'
        "def test_a_reference_without_a_column_list_does_not_emit_empty_parentheses(",
        1,
    )


def retarget_sql_server_tests(text: str) -> str:
    """Retarget the two tests asserting SQL Server ALWAYS fails closed on regex.

    `_render_tsql_regex_check` since lowered a closed table of the corpus's
    patterns to binary-collation predicates. The fail-closed guarantee still
    holds OUTSIDE that table, and that half is kept rather than deleted.
    """
    if OLD_TSQL_PAIR not in text:
        return text
    return text.replace(OLD_TSQL_PAIR, NEW_TSQL_PAIR, 1)


HELPER = '''
def _column_name(column: object) -> str:
    """A column name, whether the model hands over a string or an IndexColumn."""
    if isinstance(column, str):
        return column
    name = getattr(column, "name", None)
    if isinstance(name, str):
        return name
    raise DialectError(
        "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE",
        f"index column {column!r} carries no plain name",
    )


def _catalog_text_columns(
    table: str, columns: tuple[str, ...], catalog: ColumnCatalog | None
) -> tuple[str, ...]:
    """TEXT columns among `columns`, or () when the catalogue cannot say.

    `type_of` returning None means "not in the catalogue" -- the absence of
    evidence, never a pass. Only positively-known TEXT columns are returned.
    """
    if catalog is None:
        return ()
    return catalog.columns_of_type(table, columns, CanonicalType.TEXT)


def _require_mysql_key_columns_are_indexable(
    table: str, columns: tuple[str, ...], catalog: ColumnCatalog | None, what: str
) -> None:
    """MySQL cannot index a TEXT-family column without a prefix length (1170).

    A prefix index compares only the first N characters, so it is a WEAKER
    constraint than the source's -- two different values could satisfy a UNIQUE
    the source rejects. Choosing N is a profile decision, not a translation.
    """
    for column in columns:
        _require_identifier_not_reserved(column, "key column", Dialect.MYSQL)
    offending = _catalog_text_columns(table, columns, catalog)
    if offending:
        raise DialectError(
            "CERTIFIED_DDL_MYSQL_TEXT_KEY_REQUIRES_PREFIX",
            f"{what} covers column(s) {', '.join(sorted(offending))} on {table!r}, which the "
            "catalogue records as TEXT. MySQL stores TEXT as LONGTEXT and cannot index it "
            "without a prefix length, and a prefix index is a weaker constraint than the "
            "source's, so this fails closed.",
        )


def _mysql_reference_columns(
    fk: ForeignKey, catalog: ColumnCatalog | None
) -> tuple[str, ...]:
    """Recover the referenced columns MySQL insists on in ADD CONSTRAINT (1239).

    PostgreSQL, Oracle and SQL Server let `REFERENCES t` default to the target's
    primary key. MySQL accepts that inside CREATE TABLE but rejects it in
    `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY`. The catalogue is the only
    place the key can come from without a database connection.
    """
    if fk.ref_columns:
        return fk.ref_columns
    key = catalog.primary_key_of(fk.ref_table) if catalog is not None else None
    if key:
        return key
    raise DialectError(
        "CERTIFIED_DDL_MYSQL_REFERENCE_COLUMNS_REQUIRED",
        "MySQL requires the referenced column list on ADD FOREIGN KEY, and the source wrote "
        f"`REFERENCES {fk.ref_table}` relying on that table's primary key. No catalogue supplied "
        f"{fk.ref_table!r}, so the key cannot be recovered without guessing a column name. "
        "Spell the referenced columns at the source, or translate with the surrounding schema.",
    )


def _require_identifier_not_reserved(name: str, what: str, dialect: Dialect) -> None:
    """Refuse an identifier the TARGET reserves, naming the list's provenance.

    Quoting is deliberately not the fix: this profile refuses quoted identifiers
    on the way in, so quoting on the way out would emit a shape it will not read
    back -- and the round trip is what the route evidence rests on.
    """
    words = RESERVED_WORDS.get(dialect)
    if words is None or name.casefold() not in words:
        return
    raise DialectError(
        "CERTIFIED_DDL_TARGET_RESERVED_IDENTIFIER",
        f"{what} {name!r} is a reserved word in {dialect.value} "
        f"({PROVENANCE[dialect].value}), so the emitted statement would be a syntax error. "
        "Quoting it is not the certified fix -- it changes the plain-identifier contract. "
        "Rename the source object.",
    )

'''


def patch_emitter(text: str) -> str:
    if "_mysql_reference_columns" in text:
        return text  # already wired

    text = substitute(
        text,
        "from .dialects import (",
        "from .catalog import ColumnCatalog\nfrom .reserved_words import PROVENANCE, RESERVED_WORDS\nfrom .dialects import (",
        "emitter imports",
    )
    text = substitute(
        text, "\ndef emit_create_table(", HELPER + "\ndef emit_create_table(", "emitter helpers"
    )
    # 1. index
    text = substitute(
        text,
        "def emit_create_index(index: Index, dialect: Dialect) -> str:\n",
        "def emit_create_index(\n    index: Index, dialect: Dialect, catalog: ColumnCatalog | None = None\n) -> str:\n"
        "    if dialect is Dialect.MYSQL:\n"
        "        # `Index.columns` holds IndexColumn records (name + direction),\n"
        "        # not bare strings -- the key check wants the names.\n"
        "        _require_mysql_key_columns_are_indexable(\n"
        "            index.table,\n"
        "            tuple(_column_name(column) for column in index.columns),\n"
        "            catalog,\n"
        "            \"the index\",\n"
        "        )\n",
        "emit_create_index signature",
    )
    # 2. alter
    text = substitute(
        text,
        "def emit_alter_table(alter: AlterTable, dialect: Dialect) -> str:\n",
        "def emit_alter_table(\n    alter: AlterTable, dialect: Dialect, catalog: ColumnCatalog | None = None\n) -> str:\n",
        "emit_alter_table signature",
    )
    text = substitute(
        text,
        "        elif isinstance(action, AddConstraint):\n            if action.primary_key:\n",
        "        elif isinstance(action, AddConstraint):\n"
        "            if dialect is Dialect.MYSQL:\n"
        "                _keyed = action.primary_key or action.unique or (\n"
        "                    action.foreign_key.columns if action.foreign_key else ()\n"
        "                )\n"
        "                _require_mysql_key_columns_are_indexable(\n"
        "                    alter.table, _keyed, catalog, \"the constraint\"\n"
        "                )\n"
        "                if action.foreign_key is not None and not action.foreign_key.ref_columns:\n"
        "                    action = replace(\n"
        "                        action,\n"
        "                        foreign_key=replace(\n"
        "                            action.foreign_key,\n"
        "                            ref_columns=_mysql_reference_columns(\n"
        "                                action.foreign_key, catalog\n"
        "                            ),\n"
        "                        ),\n"
        "                    )\n"
        "            if action.primary_key:\n",
        "AddConstraint branch (the emitting one, not the identifier sweep)",
    )
    if "from dataclasses import replace" not in text:
        text = substitute(
            text,
            "from __future__ import annotations\n",
            "from __future__ import annotations\n\nfrom dataclasses import replace\n",
            "dataclasses import",
        )
    # 3. Redefine the constant rather than patch its call sites: there are two
    #    of them (CREATE TABLE and ALTER TABLE) and both are upgraded for free.
    #    The in-tree set holds 5 words; the replacement holds 261, is a strict
    #    superset, and every one was probed against a real MySQL 8.0.46.
    start = text.index("_MYSQL_RESERVED_IDENTIFIERS = frozenset(")
    end = text.index("\n)\n", start) + len("\n)\n")
    text = (
        text[:start]
        + "#: Replaced by the execution-verified list. The five words originally\n"
          "#: hard-coded here are all present in it, so nothing is lost; 256 more\n"
          "#: are gained, and Oracle/SQL Server become gate-able through the same\n"
          "#: table. See `reserved_words.py` for each list's provenance.\n"
          "_MYSQL_RESERVED_IDENTIFIERS = RESERVED_WORDS[Dialect.MYSQL]\n"
        + text[end:]
    )
    return text


def patch_engine(text: str) -> str:
    if "catalog: ColumnCatalog | None" in text:
        return text
    text = substitute(
        text,
        "    namespace_map: Mapping[str, str] | None = None,\n) -> dict[str, Any]:",
        "    namespace_map: Mapping[str, str] | None = None,\n    catalog: ColumnCatalog | None = None,\n) -> dict[str, Any]:",
        "translate_ddl signature",
    )
    text = substitute(
        text,
        "emitter.emit_alter_table(parser.parse_alter_table(sql, source, namespace_map), target)",
        "emitter.emit_alter_table(\n                parser.parse_alter_table(sql, source, namespace_map), target, catalog\n            )",
        "alter call site",
    )
    text = substitute(
        text,
        "emitter.emit_create_index(parser.parse_create_index(sql, source, namespace_map), target)",
        "emitter.emit_create_index(\n                parser.parse_create_index(sql, source, namespace_map), target, catalog\n            )",
        "index call site",
    )
    text = substitute(
        text, "from . import emitter, parser", "from . import emitter, parser\nfrom .catalog import ColumnCatalog", "engine imports"
    )
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", type=Path, required=True)
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    root = args.engine / "src/elmos_sql_dialect"
    for name in ("catalog.py", "reserved_words.py"):
        if not (root / name).is_file():
            print(f"FATAL: {name} is missing from {root}; deliver it before wiring")
            return 2

    # TWO PHASES, and the split is load-bearing. The first version of this
    # script retargeted the test files and THEN discovered the emitter had
    # drifted -- leaving a half-patched tree, which is exactly what its own
    # docstring promises never to do. Everything is computed first; nothing is
    # written unless every piece succeeded.
    planned: list[tuple[Path, str, str]] = []

    for name, patcher in (("emitter.py", patch_emitter), ("engine.py", patch_engine)):
        path = root / name
        before = path.read_text(encoding="utf-8")
        try:
            after = patcher(before)
        except PatchError as error:
            print(f"FATAL {name}: {error}")
            print("  the file has drifted past what this patch understands.")
            print("  NOTHING was written. Re-derive the anchors against the current file,")
            print("  or wire the four hooks by hand -- they are listed in the module docstring.")
            return 3
        if after != before:
            planned.append((path, after, f"{name}: wired"))

    for relative, retarget in (
        ("tests/test_execution_level_defects.py", retarget_reference_test),
        ("tests/test_regex_check_predicates.py", retarget_sql_server_tests),
    ):
        path = args.engine / relative
        if not path.is_file():
            continue
        before = path.read_text(encoding="utf-8")
        after = retarget(before)
        if after != before:
            planned.append((path, after, f"{path.name}: retargeted a superseded case"))

    if not planned:
        print("already wired, nothing to do")
        return 0

    for _path, _text, label in planned:
        print(f"  {'would apply' if args.check else 'applied'} -- {label}")
    if args.check:
        print("check only, nothing written")
        return 0

    for path, text, _label in planned:
        path.write_text(text, encoding="utf-8")

    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--fix", "-q", str(root)],
        capture_output=True,
        text=True,
    )
    print("  ruff --fix:", "clean" if result.returncode == 0 else result.stdout.strip()[:200])
    print(f"wired {len(planned)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
