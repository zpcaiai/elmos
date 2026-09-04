"""certified-alter-v1: ALTER TABLE translation.

Scope was chosen by measurement. A scan of this monorepo's 64 real
migration files found 635 ALTER TABLE actions: 603 ADD COLUMN, 29 ADD
CONSTRAINT, 2 RENAME COLUMN, 1 DROP CONSTRAINT. Those five are the
profile.

The most important tests here are the two per-dialect rules the syntax
validator CANNOT catch. `sqlglot` happily parses `ALTER TABLE t ADD COLUMN
c NUMBER` as Oracle and `ALTER TABLE t RENAME COLUMN a TO b` as T-SQL, but
both real databases reject them. A permissive parser means the validation
leg proves nothing there, so the rules are encoded in the emitter and
pinned here instead -- the same posture already taken for sqlglot's
AUTO_INCREMENT/IDENTITY generation defect.
"""

from __future__ import annotations

import pytest

from elmos_sql_dialect.emitter import emit_alter_table
from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect, DialectError, RouteError
from elmos_sql_dialect.parser import parse_alter_table

ADD_COLUMN = "ALTER TABLE sessions ADD COLUMN account_ref VARCHAR(96) NOT NULL"
TARGETS = ["mysql", "oracle", "tsql"]


# --------------------------------------------------------------------------
# The two rules a permissive parser cannot enforce
# --------------------------------------------------------------------------


def test_oracle_never_emits_the_add_column_keyword() -> None:
    # Oracle has no ADD COLUMN: it spells this `ALTER TABLE t ADD (c ...)`.
    # sqlglot parses the wrong form without complaint, so this assertion --
    # not the validation leg -- is what protects the output.
    emitted = emit_alter_table(parse_alter_table(ADD_COLUMN, Dialect.POSTGRES), Dialect.ORACLE)
    assert "ADD COLUMN" not in emitted
    assert emitted.startswith("ALTER TABLE sessions ADD (")
    assert emitted.endswith(")")


def test_sql_server_renames_a_column_with_sp_rename() -> None:
    # T-SQL has no ALTER TABLE ... RENAME COLUMN at all; it requires the
    # sp_rename stored procedure, which is a different statement kind.
    alter = parse_alter_table("ALTER TABLE snapshots RENAME COLUMN branch TO requested_ref", Dialect.POSTGRES)
    emitted = emit_alter_table(alter, Dialect.TSQL)
    assert emitted == "EXEC sp_rename 'snapshots.branch', 'requested_ref', 'COLUMN'"
    assert "RENAME COLUMN" not in emitted


@pytest.mark.parametrize("dialect", [Dialect.POSTGRES, Dialect.MYSQL, Dialect.ORACLE])
def test_the_other_dialects_do_use_rename_column(dialect: Dialect) -> None:
    alter = parse_alter_table("ALTER TABLE snapshots RENAME COLUMN branch TO requested_ref", Dialect.POSTGRES)
    assert "RENAME COLUMN branch TO requested_ref" in emit_alter_table(alter, dialect)


def test_sql_server_add_column_omits_the_column_keyword() -> None:
    # T-SQL is `ALTER TABLE t ADD c INT`, not `ADD COLUMN c INT`.
    emitted = emit_alter_table(parse_alter_table(ADD_COLUMN, Dialect.POSTGRES), Dialect.TSQL)
    assert "ADD COLUMN" not in emitted
    assert "ADD account_ref" in emitted


# --------------------------------------------------------------------------
# Every certified action reaches every dialect and re-parses there
# --------------------------------------------------------------------------


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize(
    "sql",
    [
        ADD_COLUMN,
        "ALTER TABLE sessions ADD COLUMN account_ref VARCHAR(96) REFERENCES accounts (account_id)",
        "ALTER TABLE sessions ADD COLUMN retries INTEGER DEFAULT 0",
        "ALTER TABLE sessions DROP COLUMN legacy_flag",
        "ALTER TABLE sessions RENAME COLUMN branch TO requested_ref",
        "ALTER TABLE sessions ADD CONSTRAINT sessions_uq UNIQUE (account_ref, branch)",
        "ALTER TABLE sessions ADD CONSTRAINT sessions_fk FOREIGN KEY (account_ref) "
        "REFERENCES accounts (account_id) ON DELETE CASCADE",
        "ALTER TABLE sessions ADD CONSTRAINT sessions_ck CHECK (retries >= 0)",
        "ALTER TABLE sessions DROP CONSTRAINT sessions_uq",
    ],
)
def test_every_certified_action_translates_and_revalidates(sql: str, target: str) -> None:
    report = translate_ddl(sql, "postgres", target, statement_kind="ALTER")
    assert report["status"] == "PASSED", report["reason"]
    assert report["profile"] == "certified-alter-v1"


def test_multiple_actions_become_separate_statements() -> None:
    # Oracle's ADD takes a parenthesised list and cannot be mixed with other
    # action kinds, so a multi-action source is split into separate
    # statements rather than emitted as a comma list only some dialects
    # accept.
    alter = parse_alter_table("ALTER TABLE t ADD COLUMN a INTEGER, ADD COLUMN b INTEGER", Dialect.POSTGRES)
    assert len(alter.actions) == 2
    emitted = emit_alter_table(alter, Dialect.ORACLE)
    assert emitted.count("ALTER TABLE t") == 2
    assert ";\n" in emitted


def test_a_mixed_multi_action_alter_fails_closed() -> None:
    # sqlglot cannot read `ADD COLUMN a INTEGER, DROP COLUMN b` at all and
    # degrades it to an opaque Command. Degrading silently would be the
    # dangerous outcome, so it is reported as outside the profile.
    with pytest.raises(DialectError):
        parse_alter_table("ALTER TABLE t ADD COLUMN a INTEGER, DROP COLUMN b", Dialect.POSTGRES)


def test_opaque_postgres_multi_add_alter_is_recovered_action_by_action() -> None:
    # sqlglot falls back to Command for this PostgreSQL spelling because the
    # final CHECK contains a list. The compatibility path must still parse
    # every action through the normal typed ALTER parser.
    alter = parse_alter_table(
        "ALTER TABLE mainframe_business_rules "
        "ADD COLUMN confidence NUMERIC(5,4), "
        "ADD COLUMN authority VARCHAR(32) NOT NULL DEFAULT 'CANDIDATE', "
        "ADD CONSTRAINT mainframe_rule_authority CHECK "
        "(authority IN ('CANDIDATE','BUSINESS_APPROVED','REJECTED'))",
        Dialect.POSTGRES,
    )
    assert len(alter.actions) == 3
    emitted = emit_alter_table(alter, Dialect.POSTGRES)
    assert "confidence NUMERIC(5, 4)" in emitted
    assert "mainframe_rule_authority" in emitted


def test_an_inline_reference_on_an_added_column_is_preserved() -> None:
    alter = parse_alter_table(
        "ALTER TABLE sessions ADD COLUMN account_ref VARCHAR(96) REFERENCES accounts (account_id) ON DELETE CASCADE",
        Dialect.POSTGRES,
    )
    action = alter.actions[0]
    assert action.foreign_key is not None
    assert action.foreign_key.ref_table == "accounts"
    assert "ON DELETE CASCADE" in emit_alter_table(alter, Dialect.MYSQL)


# --------------------------------------------------------------------------
# Fail-closed boundaries
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        # These need the column's full type restated on MySQL (MODIFY) and
        # SQL Server (ALTER COLUMN), and a single ALTER statement does not
        # carry it. Inventing a type is exactly the silent corruption this
        # profile exists to prevent.
        ("ALTER TABLE t ALTER COLUMN c SET NOT NULL", "CERTIFIED_ALTER_UNSUPPORTED_ACTION"),
        ("ALTER TABLE t ALTER COLUMN c TYPE BIGINT", "CERTIFIED_ALTER_UNSUPPORTED_ACTION"),
        ("ALTER TABLE t ALTER COLUMN c SET DEFAULT 1", "CERTIFIED_ALTER_UNSUPPORTED_ACTION"),
        ("ALTER TABLE t ALTER COLUMN c DROP DEFAULT", "CERTIFIED_ALTER_UNSUPPORTED_ACTION"),
        # Column-shorthand constraints on an added column.
        ("ALTER TABLE t ADD COLUMN c INTEGER PRIMARY KEY", "CERTIFIED_ALTER_UNSUPPORTED_COLUMN_CONSTRAINT"),
        ("ALTER TABLE t ADD COLUMN c INTEGER UNIQUE", "CERTIFIED_ALTER_UNSUPPORTED_COLUMN_CONSTRAINT"),
        # Structural refusals.
        ("ALTER TABLE app.t ADD COLUMN c INTEGER", "CERTIFIED_DDL_NAMESPACE_MAPPING_REQUIRED"),
        ("ALTER TABLE IF EXISTS t ADD COLUMN c INTEGER", "CERTIFIED_ALTER_UNSUPPORTED_STATEMENT_MODIFIER"),
        ("CREATE TABLE t (id INTEGER)", "CERTIFIED_ALTER_UNSUPPORTED_STATEMENT"),
    ],
)
def test_out_of_profile_alters_fail_closed(sql: str, code: str) -> None:
    with pytest.raises(DialectError) as exc:
        parse_alter_table(sql, Dialect.POSTGRES)
    assert exc.value.code == code


def test_a_blocked_alter_is_reported_not_raised() -> None:
    report = translate_ddl("ALTER TABLE t ALTER COLUMN c SET NOT NULL", "postgres", "mysql", statement_kind="ALTER")
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_ALTER_UNSUPPORTED_ACTION"
    assert report["emitted"] is None
    # The reason names the actual obstacle, so a reader can tell this is a
    # deliberate boundary rather than a parser failure.
    assert "full type" in report["reason"]


def test_an_unknown_statement_kind_is_a_caller_mistake() -> None:
    with pytest.raises(RouteError):
        translate_ddl(ADD_COLUMN, "postgres", "mysql", statement_kind="UNKNOWN")


# --------------------------------------------------------------------------
# Round trip
# --------------------------------------------------------------------------


@pytest.mark.parametrize("dialect", [Dialect.MYSQL, Dialect.POSTGRES])
def test_add_column_round_trips_to_the_same_canonical_model(dialect: Dialect) -> None:
    original = parse_alter_table(ADD_COLUMN, Dialect.POSTGRES)
    emitted = emit_alter_table(original, dialect)
    assert parse_alter_table(emitted, dialect) == original


# --------------------------------------------------------------------------
# Referential actions, the third rule the validation leg cannot enforce
#
# sqlglot accepts `ON DELETE NO ACTION ON UPDATE NO ACTION` for every
# dialect, so the syntax leg proved nothing here either. Oracle's documented
# references_clause has NO `ON UPDATE` at all, accepts only CASCADE and
# SET NULL for `ON DELETE`, and has no RESTRICT. SQL Server has no RESTRICT.
# This was a pre-existing defect in the CREATE TABLE path -- every emitted
# Oracle foreign key carried a clause Oracle rejects.
# --------------------------------------------------------------------------

FK_TABLE = "CREATE TABLE a (id INTEGER PRIMARY KEY, b_id INTEGER, FOREIGN KEY (b_id) REFERENCES b (id){actions})"


def test_oracle_omits_the_default_referential_actions() -> None:
    from elmos_sql_dialect.emitter import emit_create_table
    from elmos_sql_dialect.parser import parse_create_table

    emitted = emit_create_table(parse_create_table(FK_TABLE.format(actions=""), Dialect.POSTGRES), Dialect.ORACLE)
    # Oracle expresses NO ACTION by omission; spelling it out is a syntax
    # error there even though sqlglot parses it happily.
    assert "ON UPDATE" not in emitted
    assert "ON DELETE" not in emitted
    assert "REFERENCES b (id)" in emitted


@pytest.mark.parametrize("target", ["postgres", "mysql", "tsql"])
def test_the_other_dialects_still_spell_the_actions_out(target: str) -> None:
    report = translate_ddl(FK_TABLE.format(actions=""), "oracle", target)
    assert report["status"] == "PASSED", report["reason"]
    assert "ON DELETE NO ACTION" in report["emitted"]
    assert "ON UPDATE NO ACTION" in report["emitted"]


def test_oracle_keeps_the_delete_actions_it_does_support() -> None:
    report = translate_ddl(FK_TABLE.format(actions=" ON DELETE CASCADE"), "postgres", "oracle")
    assert report["status"] == "PASSED", report["reason"]
    assert "ON DELETE CASCADE" in report["emitted"]
    assert "ON UPDATE" not in report["emitted"]


@pytest.mark.parametrize(
    ("actions", "target"),
    [
        # Oracle has no ON UPDATE clause whatsoever.
        (" ON UPDATE CASCADE", "oracle"),
        (" ON UPDATE SET NULL", "oracle"),
        # Neither Oracle nor SQL Server has RESTRICT. Downgrading it to NO
        # ACTION would change WHEN the constraint is checked without saying
        # so, which is the silent-corruption case this engine exists for.
        (" ON DELETE RESTRICT", "oracle"),
        (" ON DELETE RESTRICT", "tsql"),
        (" ON UPDATE RESTRICT", "tsql"),
    ],
)
def test_an_unreachable_referential_action_fails_closed(actions: str, target: str) -> None:
    report = translate_ddl(FK_TABLE.format(actions=actions), "postgres", target)
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_UNREACHABLE_REFERENTIAL_ACTION"
    assert report["emitted"] is None
    assert "downgrade it silently" in report["reason"]


def test_the_same_rule_applies_to_alter_add_constraint() -> None:
    # The ALTER path must not be able to smuggle in a clause the CREATE path
    # refuses -- one canonical model, one set of per-dialect rules.
    report = translate_ddl(
        "ALTER TABLE a ADD CONSTRAINT a_fk FOREIGN KEY (b_id) REFERENCES b (id) ON UPDATE CASCADE",
        "postgres",
        "oracle",
        statement_kind="ALTER",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_UNREACHABLE_REFERENTIAL_ACTION"


def test_the_same_rule_applies_to_an_inline_reference_on_an_added_column() -> None:
    report = translate_ddl(
        "ALTER TABLE a ADD COLUMN b_id INTEGER REFERENCES b (id) ON UPDATE CASCADE",
        "postgres",
        "oracle",
        statement_kind="ALTER",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_UNREACHABLE_REFERENTIAL_ACTION"
