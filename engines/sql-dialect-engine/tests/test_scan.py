"""Coverage pre-check tests, plus the inline-constraint gap it uncovered.

The pre-check's only value is that its number is trustworthy, so most of
these are about the ways a coverage report can lie: splitting statements
wrongly, hiding engine crashes inside the blocked count, presenting an
upper bound as a promise, and -- the one this engine actually got wrong --
ranking blockers so that one copy-pasted idiom looks like hundreds of
distinct problems.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_sql_dialect.cli import main
from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect, DialectError
from elmos_sql_dialect.parser import parse_create_table
from elmos_sql_dialect.scan import render_markdown, scan_repository

IN_SUBSET = "CREATE TABLE person (id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL);"
# In certified-alter-v1 since the ALTER profile landed -- kept as the
# in-subset ALTER fixture.
ALTER_ADD = "ALTER TABLE person ADD COLUMN age INTEGER;"
# Still out of profile: MySQL and SQL Server need the column's full type
# restated, which this statement does not carry.
ALTER = "ALTER TABLE person ALTER COLUMN age SET NOT NULL;"
VIEW = "CREATE VIEW adults AS SELECT id FROM person WHERE age > 18;"


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "schema"
    root.mkdir()
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


# --------------------------------------------------------------------------
# The gap the scan uncovered: inline REFERENCES was rejected while the
# table-level spelling of the SAME constraint was accepted.
# --------------------------------------------------------------------------


def test_inline_and_table_level_foreign_keys_produce_the_same_model() -> None:
    inline = parse_create_table(
        "CREATE TABLE a (id INTEGER PRIMARY KEY, b_id INTEGER REFERENCES b(id) ON DELETE CASCADE)",
        Dialect.POSTGRES,
    )
    table_level = parse_create_table(
        "CREATE TABLE a (id INTEGER PRIMARY KEY, b_id INTEGER, "
        "FOREIGN KEY (b_id) REFERENCES b(id) ON DELETE CASCADE)",
        Dialect.POSTGRES,
    )
    # Every one of the four dialects accepts both spellings and treats them
    # identically, so two schemas that are identical to a database must not
    # produce different canonical models.
    assert inline.foreign_keys == table_level.foreign_keys


def test_inline_and_table_level_checks_produce_the_same_model() -> None:
    inline = parse_create_table("CREATE TABLE a (n INTEGER CHECK (n > 0))", Dialect.POSTGRES)
    table_level = parse_create_table("CREATE TABLE a (n INTEGER, CHECK (n > 0))", Dialect.POSTGRES)
    assert inline.check_constraints == table_level.check_constraints


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_an_inline_foreign_key_translates_to_every_dialect(target: str) -> None:
    report = translate_ddl(
        "CREATE TABLE a (id INTEGER PRIMARY KEY, b_id INTEGER REFERENCES b(id) ON DELETE CASCADE)",
        "postgres",
        target,
    )
    assert report["status"] == "PASSED", report["reason"]
    # The emitted form is whatever the target spells it as; what matters is
    # that the target's own strict parser accepted it.
    assert "b" in (report["emitted"] or "")


def test_two_inline_references_on_one_column_still_fail_closed() -> None:
    with pytest.raises(DialectError) as exc:
        parse_create_table(
            "CREATE TABLE a (b_id INTEGER REFERENCES b(id) REFERENCES c(id))", Dialect.POSTGRES
        )
    assert exc.value.code == "CERTIFIED_DDL_UNSUPPORTED_COLUMN_CONSTRAINT"


# --------------------------------------------------------------------------
# The headline number
# --------------------------------------------------------------------------


def test_counts_every_statement_in_subset_and_out(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"V1.sql": f"{IN_SUBSET}\n{ALTER}\n{VIEW}\n"})
    report = scan_repository(root, Dialect.POSTGRES)
    assert report.totals["discovered"] == 3
    assert report.totals["inSubset"] == 2
    assert report.totals["outOfSubset"] == 1
    assert report.totals["scanErrors"] == 0
    assert report.upper_bound_coverage == pytest.approx(2 / 3, abs=0.001)


def test_every_discovered_unit_has_a_disposition_even_when_translation_is_blocked(
    tmp_path: Path,
) -> None:
    report = scan_repository(_repo(tmp_path, {"V1.sql": f"{IN_SUBSET}\n{ALTER}\n{VIEW}"}), Dialect.POSTGRES)
    assert report.disposition_coverage == 1.0
    assert report.totals["dispositionCovered"] == report.totals["dispositionUnits"] == 3
    assert report.totals["dispositionUnknown"] == 0
    assert report.disposition_counts == {
        "AUTOMATED_TRANSLATION_CANDIDATE": 2,
        "MANUAL_MIGRATION_REQUIRED": 1,
    }


def test_scan_profile_names_all_active_sql_profiles(tmp_path: Path) -> None:
    report = scan_repository(_repo(tmp_path, {"V1.sql": IN_SUBSET}), Dialect.POSTGRES)
    assert report.profile == (
        "certified-ddl-v1 + certified-alter-v1 + certified-drop-v1 + certified-schema-v1 "
        "+ certified-routine-v1 + certified-view-v1 + certified-comment-v1 + certified-privilege-v1 "
        "+ certified-dml-v1 + certified-rls-v1"
    )


def test_statements_are_split_by_the_real_parser_not_by_semicolons(tmp_path: Path) -> None:
    # A semicolon inside a string literal would make naive splitting report
    # two statements where there is one, silently inflating the denominator.
    root = _repo(
        tmp_path,
        {"V1.sql": "CREATE TABLE note (id INTEGER PRIMARY KEY, body VARCHAR(40) DEFAULT 'a;b');"},
    )
    report = scan_repository(root, Dialect.POSTGRES)
    assert report.totals["discovered"] == 1


def test_migration_units_stay_in_the_denominator(tmp_path: Path) -> None:
    # Unlike the component scanner -- where a function returning no JSX is a
    # helper rather than a migration unit -- a view or an uncertified ALTER
    # IS work the customer needs done. Excluding it would flatter the ratio
    # by hiding exactly what this engine cannot do.
    root = _repo(tmp_path, {"V1.sql": f"{ALTER}\n{VIEW}\n"})
    report = scan_repository(root, Dialect.POSTGRES)
    assert report.totals["discovered"] == 2
    assert report.upper_bound_coverage == pytest.approx(1 / 2, abs=0.001)


def test_empty_schema_reports_zero_rather_than_dividing_by_zero(tmp_path: Path) -> None:
    report = scan_repository(_repo(tmp_path, {}), Dialect.POSTGRES)
    assert report.totals["discovered"] == 0
    assert report.upper_bound_coverage == 0.0
    assert report.blockers == []


# --------------------------------------------------------------------------
# Ranking, and the honesty problem the first real scan exposed
# --------------------------------------------------------------------------


def test_ranks_blockers_by_frequency_with_plain_language(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"V1.sql": f"{ALTER}\n{ALTER}\n{VIEW}\n"})
    report = scan_repository(root, Dialect.POSTGRES)
    assert report.blockers[0].reason_code == "CERTIFIED_ALTER_UNSUPPORTED_ACTION"
    assert report.blockers[0].count == 2
    for blocker in report.blockers:
        assert not blocker.what.startswith("CERTIFIED_DDL_")
        assert len(blocker.what) > 20


def test_distinguishes_occurrences_from_distinct_reasons(tmp_path: Path) -> None:
    # This is the correction the first real scan forced. One copy-pasted
    # idiom produced 340 of 342 occurrences of a single blocker; ranking by
    # occurrences alone would have pointed the next expansion at a problem
    # that is really one line of SQL repeated across a schema.
    repeated = "CREATE TABLE t{i} (h VARCHAR(64) CHECK (h IS NULL OR h LIKE 'a%'));"
    body = "\n".join(repeated.replace("{i}", str(i)) for i in range(6))
    report = scan_repository(_repo(tmp_path, {"V1.sql": body}), Dialect.POSTGRES)
    blocker = report.blockers[0]
    assert blocker.count == 6
    assert blocker.distinct_reasons == 1
    assert "Distinct" in render_markdown(report)


def test_examples_are_deduplicated(tmp_path: Path) -> None:
    body = "\n".join(f"ALTER TABLE t{i} ALTER COLUMN c SET NOT NULL;" for i in range(5))
    report = scan_repository(_repo(tmp_path, {"V1.sql": body}), Dialect.POSTGRES)
    # All five share one reason, so quoting the same problem five times
    # would be noise rather than evidence.
    assert len(report.blockers[0].example_statements) == 1


def test_is_deterministic_so_two_scans_diff_cleanly(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"V1.sql": f"{IN_SUBSET}\n{ALTER}\n{VIEW}\n"})
    first = scan_repository(root, Dialect.POSTGRES)
    second = scan_repository(root, Dialect.POSTGRES)
    assert first.blockers == second.blockers
    assert first.families == second.families


def test_families_account_for_every_blocked_statement(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"V1.sql": f"{ALTER}\n{VIEW}\n"})
    report = scan_repository(root, Dialect.POSTGRES)
    assert sum(f.count for f in report.families) == report.totals["outOfSubset"]


# --------------------------------------------------------------------------
# Honesty of the number itself
# --------------------------------------------------------------------------


def test_states_the_upper_bound_caveat(tmp_path: Path) -> None:
    report = scan_repository(_repo(tmp_path, {"V1.sql": IN_SUBSET}), Dialect.POSTGRES)
    joined = " ".join(report.caveats)
    assert "UPPER BOUND" in joined
    assert "re-parsed by the TARGET dialect" in joined
    assert "Distinct" in joined


def test_the_upper_bound_really_does_bound_a_real_run(tmp_path: Path) -> None:
    # The claim is only worth making if it holds against the real pipeline,
    # so this asserts it rather than asserting the wording.
    root = _repo(tmp_path, {"V1.sql": f"{IN_SUBSET}\n{ALTER}\n"})
    report = scan_repository(root, Dialect.POSTGRES)
    translated = 0
    for statement in (IN_SUBSET, ALTER):
        if translate_ddl(statement, "postgres", "mysql")["status"] == "PASSED":
            translated += 1
    assert translated <= report.totals["inSubset"]


def test_a_parser_rejection_is_a_subset_boundary_not_an_engine_error(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"V1.sql": "CREATE TABLE ((("})
    report = scan_repository(root, Dialect.POSTGRES)
    assert report.totals["scanErrors"] == 0
    assert report.findings[0].reason_code == "CERTIFIED_DDL_PARSE_FAILED"
    assert report.findings[0].family == "source-format"


def test_a_clean_report_is_not_padded_with_a_scan_error_warning(tmp_path: Path) -> None:
    report = scan_repository(_repo(tmp_path, {"V1.sql": IN_SUBSET}), Dialect.POSTGRES)
    assert report.totals["scanErrors"] == 0
    assert "SCAN_ERROR" not in report.caveats[0]


def test_a_missing_repository_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DialectError) as exc:
        scan_repository(tmp_path / "nope", Dialect.POSTGRES)
    assert exc.value.code == "REPOSITORY_NOT_FOUND"


# --------------------------------------------------------------------------
# Reaching a human, and the CLI
# --------------------------------------------------------------------------


def test_markdown_carries_the_count_the_ranking_and_the_caveat(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"V1.sql": f"{IN_SUBSET}\n{ALTER}\n{VIEW}\n"})
    markdown = render_markdown(scan_repository(root, Dialect.POSTGRES))
    assert "2 of 3 statements are inside the certified subset" in markdown
    assert "66.7%" in markdown
    assert "CERTIFIED_ALTER_UNSUPPORTED_ACTION" in markdown
    assert "UPPER BOUND" in markdown


def test_cli_writes_both_formats_and_exits_non_zero_when_incomplete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {"V1.sql": f"{IN_SUBSET}\n{ALTER}\n"})
    out = tmp_path / "out"
    code = main(["scan", "--repository", str(root), "--source-dialect", "postgres", "--output", str(out)])
    capsys.readouterr()
    assert code == 2
    payload = json.loads((out / "feasibility-report.json").read_text(encoding="utf-8"))
    assert payload["kind"] == "elmos.sql-dialect-feasibility-scan"
    assert (out / "feasibility-report.md").exists()


def test_cli_exits_zero_only_when_everything_is_in_subset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {"V1.sql": IN_SUBSET})
    code = main(["scan", "--repository", str(root), "--source-dialect", "postgres"])
    capsys.readouterr()
    assert code == 0


def test_cli_can_gate_100_percent_disposition_without_claiming_translation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {"V1.sql": f"{IN_SUBSET}\n{VIEW}"})
    code = main(
        [
            "scan",
            "--repository",
            str(root),
            "--source-dialect",
            "postgres",
            "--require-disposition-complete",
        ]
    )
    capsys.readouterr()
    assert code == 0
