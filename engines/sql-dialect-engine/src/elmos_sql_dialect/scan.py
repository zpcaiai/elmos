"""Coverage pre-check: how much of a real schema can this engine translate?

Same purpose as `engines/component-dialect-engine`'s `scan`, and written
after it for the same reason: a certified subset is only honest if its
boundary is visible BEFORE anyone commits to a migration. Without a
pre-check the only way to learn that a schema is 12% convertible is to run
the whole migration and read the wreckage.

Properties that make the number trustworthy:

  - **Parse-only.** Nothing is emitted, nothing is written, no target
    dialect is chosen. Subset membership is a property of the source.

  - **Split by the real parser.** Statements are separated by `sqlglot`
    itself, not by splitting on semicolons -- a semicolon inside a string
    literal, a `$$`-quoted function body or a `BEGIN ... END` block would
    make naive splitting silently miscount.

  - **Counted, never extrapolated.** Every number is a count of statements
    actually parsed.

  - **An UPPER BOUND, and it says so.** Parsing proves a statement is
    inside `certified-ddl-v1` from the SOURCE side; emission is still
    re-validated by the target dialect's strict parser during a real run.

One deliberate difference from the component scanner. There, a function
returning no JSX is a *helper* -- not a migration unit -- so it is
excluded from the denominator. Here there is no equivalent: an
`ALTER TABLE`, a view or a stored procedure IS a migration unit the
customer needs translated. Excluding it would flatter the ratio by
hiding exactly the work the engine cannot do. So everything executable
stays in the denominator, and only comments and blank statements are
dropped.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

import sqlglot
from sqlglot import exp

from .models import Dialect, DialectError
from .parser import parse_alter_table, parse_create_index, parse_create_table

FindingStatus = Literal["IN_SUBSET", "OUT_OF_SUBSET", "SCAN_ERROR"]

#: Directories never worth walking into.
IGNORED_DIRECTORIES = frozenset(
    {
        ".git", "node_modules", "target", "build", "dist", "out",
        "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache",
    }
)

BlockerFamily = Literal[
    "statement-kind",
    "types",
    "constraints",
    "defaults",
    "identifiers",
    "structure",
    "source-format",
]

#: Plain-language meaning per reason code, plus the family it belongs to.
#:
#: Without this a coverage report is a wall of SCREAMING_SNAKE_CASE that
#: nobody can act on. Codes absent here fall back to the parser's own
#: message, which is always populated -- an unmapped code degrades to less
#: readable, never to wrong.
BLOCKER_CATALOG: dict[str, tuple[BlockerFamily, str]] = {
    "CERTIFIED_DDL_UNSUPPORTED_STATEMENT": (
        "statement-kind",
        "a statement no certified profile covers -- CREATE VIEW, stored procedures, "
        "triggers, GRANT/REVOKE and DML all land here",
    ),
    "CERTIFIED_ALTER_UNSUPPORTED_STATEMENT": (
        "statement-kind",
        "not a single ALTER TABLE statement",
    ),
    "CERTIFIED_ALTER_UNSUPPORTED_ACTION": (
        "statement-kind",
        "an ALTER TABLE action outside ADD/DROP/RENAME COLUMN and ADD/DROP CONSTRAINT -- "
        "column type, nullability and default changes need the column's full type, which a "
        "single ALTER statement does not carry",
    ),
    "CERTIFIED_ALTER_UNSUPPORTED_STATEMENT_MODIFIER": (
        "statement-kind",
        "an ALTER TABLE modifier outside the certified set (IF EXISTS and similar)",
    ),
    "CERTIFIED_ALTER_UNSUPPORTED_CONSTRAINT": (
        "constraints",
        "an ADD CONSTRAINT clause outside PRIMARY KEY / UNIQUE / FOREIGN KEY / CHECK",
    ),
    "CERTIFIED_ALTER_UNSUPPORTED_COLUMN_CONSTRAINT": (
        "constraints",
        "an inline PRIMARY KEY or UNIQUE on an added column -- the dialects differ on whether "
        "that may be combined with ADD COLUMN, so add the column and the constraint separately",
    ),
    "CERTIFIED_ALTER_MISSING_TYPE": ("types", "an added column with no type"),
    "CERTIFIED_ALTER_EMPTY": ("structure", "an ALTER TABLE carrying no action"),
    "CERTIFIED_DDL_MULTIPLE_STATEMENTS": (
        "statement-kind",
        "more than one statement handed to a single translate call",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER": (
        "statement-kind",
        "a modifier on the statement outside the certified set (IF NOT EXISTS, "
        "TEMPORARY, table options, tablespaces, and similar)",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_TYPE": (
        "types",
        "a column type outside the certified cross-dialect set",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_TYPE_PARAM": (
        "types",
        "a type parameter outside the certified set (precision/scale/charset variants)",
    ),
    "CERTIFIED_DDL_UNREACHABLE_TYPE": (
        "types",
        "a type this engine cannot render on every target dialect",
    ),
    "CERTIFIED_DDL_UNBOUNDED_VARCHAR": (
        "types",
        "a VARCHAR with no length -- unlimited in PostgreSQL, VARCHAR(1) in SQL Server, "
        "rejected outright by MySQL and Oracle; declare an explicit length",
    ),
    "CERTIFIED_DDL_UNBOUNDED_DECIMAL": (
        "types",
        "a DECIMAL/NUMBER with no precision -- arbitrary precision in PostgreSQL and Oracle, "
        "with no fixed-precision equivalent on MySQL or SQL Server",
    ),
    "CERTIFIED_DDL_UNSIGNED_BIGINT_UNREPRESENTABLE": (
        "types",
        "a BIGINT UNSIGNED column -- its range reaches 18446744073709551615, which no "
        "canonical integer holds and which PostgreSQL, Oracle and SQL Server cannot express",
    ),
    "CERTIFIED_DDL_MYSQL_AUTO_INCREMENT_NOT_KEY": (
        "structure",
        "an identity/auto-increment column that is not a key -- legal in PostgreSQL, Oracle "
        "and SQL Server, rejected by MySQL with errno 1075",
    ),
    "CERTIFIED_DDL_LENGTH_EXCEEDS_TARGET": (
        "types",
        "a CHAR/VARCHAR length the target dialect's documented maximum does not allow",
    ),
    "CERTIFIED_DDL_PRECISION_EXCEEDS_TARGET": (
        "types",
        "a DECIMAL precision or scale the target dialect's documented maximum does not allow",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_COLUMN_CONSTRAINT": (
        "constraints",
        "a column constraint outside NOT NULL / PRIMARY KEY / UNIQUE / DEFAULT / CHECK / REFERENCES",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_CONSTRAINT": (
        "constraints",
        "a table-level constraint outside the certified set",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_CHECK": (
        "constraints",
        "a CHECK expression outside simple column-to-literal comparisons",
    ),
    "CERTIFIED_DDL_MULTI_LEVEL_CHECK": (
        "constraints",
        "a CHECK with nested or mixed AND/OR levels",
    ),
    "CERTIFIED_DDL_EMPTY_CHECK": ("constraints", "a CHECK with no comparison in it"),
    "CERTIFIED_DDL_MISSING_CONNECTOR": (
        "constraints",
        "a multi-comparison CHECK with no single AND/OR connector",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_REFERENTIAL_ACTION": (
        "constraints",
        "an ON DELETE / ON UPDATE action outside the certified set",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_DEFAULT": (
        "defaults",
        "a DEFAULT that is not a plain literal -- function calls like now() and "
        "expressions land here, because their spelling and semantics differ per dialect",
    ),
    "CERTIFIED_DDL_DEFAULT_TYPE_MISMATCH": (
        "defaults",
        "a DEFAULT literal whose type disagrees with the declared column type",
    ),
    "CERTIFIED_DDL_UNREACHABLE_DEFAULT": (
        "defaults",
        "a DEFAULT this engine cannot render on every target dialect",
    ),
    "CERTIFIED_DDL_QUALIFIED_TABLE_NAME": (
        "identifiers",
        "a schema- or database-qualified name; qualification rules differ per dialect",
    ),
    "CERTIFIED_DDL_QUOTED_IDENTIFIER": (
        "identifiers",
        "a quoted identifier -- quoting character and case-folding differ per dialect",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE": (
        "identifiers",
        "an identifier outside a plain unquoted [A-Za-z_][A-Za-z0-9_]* name",
    ),
    "CERTIFIED_DDL_MISSING_IDENTIFIER": ("identifiers", "a missing table, column or index name"),
    "CERTIFIED_DDL_UNKNOWN_COLUMN": (
        "structure",
        "a constraint or index referencing a column the statement never declares",
    ),
    "CERTIFIED_DDL_DUPLICATE_COLUMN": ("structure", "the same column declared twice"),
    "CERTIFIED_DDL_EMPTY_TABLE": ("structure", "a CREATE TABLE with no columns"),
    "CERTIFIED_DDL_EMPTY_INDEX": ("structure", "a CREATE INDEX with no columns"),
    "CERTIFIED_DDL_UNSUPPORTED_TABLE_ITEM": (
        "structure",
        "an item inside CREATE TABLE that is neither a column nor a certified constraint",
    ),
    "CERTIFIED_DDL_PARSE_FAILED": (
        "source-format",
        "sqlglot rejected the statement under the declared source dialect -- a syntax "
        "error, or dialect-specific syntax the reader does not accept",
    ),
}


@dataclass(frozen=True)
class ScanFinding:
    source_path: str
    #: 1-based position of the statement within its file.
    statement_index: int
    status: FindingStatus
    #: The statement kind sqlglot identified, e.g. "Create", "Alter", "Insert".
    statement_kind: str | None
    reason_code: str | None
    reason: str | None
    family: str | None
    #: First line of the statement, trimmed -- enough to recognise it.
    excerpt: str


@dataclass(frozen=True)
class BlockerGroup:
    reason_code: str
    family: str | None
    what: str
    #: Total blocked statements carrying this code.
    count: int
    #: How many DISTINCT reasons produced that count.
    #:
    #: This is the number that should drive a roadmap, and it is why the
    #: two are reported separately. On the first real scan a single
    #: copy-pasted idiom -- `CHECK (h IS NULL OR h ~ '^[0-9a-f]{64}$')` --
    #: accounted for 340 of 342 occurrences of one blocker. Ranking by
    #: occurrences alone would have pointed the next expansion at a problem
    #: that is really one line of SQL repeated across a schema.
    distinct_reasons: int
    share_of_blocked: float
    example_statements: list[str]


@dataclass(frozen=True)
class FamilyGroup:
    family: str
    count: int
    share_of_blocked: float


@dataclass(frozen=True)
class FeasibilityReport:
    schema_version: str
    kind: str
    profile: str
    repository: str
    source_dialect: str
    scanned_at: str
    totals: dict[str, int]
    upper_bound_coverage: float
    blockers: list[BlockerGroup]
    families: list[FamilyGroup]
    findings: list[ScanFinding]
    caveats: list[str] = field(default_factory=list)


def discover_sql_files(repository: str | os.PathLike[str]) -> list[Path]:
    """Every `.sql` file under `repository`, sorted, skipping build output."""
    root = Path(repository)
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRECTORIES]
        for name in filenames:
            if name.endswith(".sql"):
                found.append(Path(dirpath) / name)
    return sorted(found)


def _excerpt(statement: exp.Expr) -> str:
    text = statement.sql().strip().replace("\n", " ")
    return text[:110] + ("..." if len(text) > 110 else "")


def _classify(statement: exp.Expr, dialect: Dialect) -> tuple[FindingStatus, str | None, str | None]:
    """Parse one statement through the real certified parser.

    Returns ``(status, reason_code, reason)``. A `DialectError` is a subset
    boundary; anything else is an engine defect and is reported as such
    rather than being folded into the blocked count.
    """
    # The parsed node goes straight through. Serialising it back to SQL so the
    # parser could parse it a second time was two thirds of the work here, and
    # the round trip could only lose fidelity relative to the node the splitter
    # already produced.
    #
    # sqlglot's stubs type a parsed statement as an internal `Expr` alias that
    # is not assignable to `Expression` (see the same note in `parser.py`), so
    # narrow it here. The runtime object is an `Expression`; `Expr` only ever
    # appears in annotations, which this module never evaluates.
    assert isinstance(statement, exp.Expression)
    try:
        if isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "TABLE":
            parse_create_table(statement, dialect)
        elif isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "INDEX":
            parse_create_index(statement, dialect)
        elif isinstance(statement, exp.Alter):
            # certified-alter-v1. Routed here so the coverage number tracks
            # what the engine can really do rather than one profile of it.
            parse_alter_table(statement, dialect)
        else:
            # Not a CREATE TABLE / CREATE INDEX at all. This is the single
            # most important number in the report, so it is produced by the
            # same fail-closed path as everything else rather than by a
            # special case that could drift from the parser.
            parse_create_table(statement, dialect)
        return "IN_SUBSET", None, None
    except DialectError as exc:
        return "OUT_OF_SUBSET", exc.code, exc.message
    except Exception as exc:  # noqa: BLE001 - deliberately broad; see below
        # NOT a subset boundary -- a defect in this engine. Kept separate so
        # a crash can never be laundered into a coverage percentage.
        return "SCAN_ERROR", "ENGINE_ERROR", f"{type(exc).__name__}: {exc}"


def scan_repository(
    repository: str | os.PathLike[str],
    source_dialect: Dialect,
    examples_per_blocker: int = 5,
    include_all_findings: bool = False,
) -> FeasibilityReport:
    """Parse every statement in every `.sql` file and report subset membership."""
    root = Path(repository)
    if not root.exists():
        raise DialectError("REPOSITORY_NOT_FOUND", str(root))

    findings: list[ScanFinding] = []
    for path in discover_sql_files(root):
        relative = str(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                ScanFinding(relative, 0, "SCAN_ERROR", None, "FILE_UNREADABLE", str(exc), None, "")
            )
            continue

        # Split with the REAL parser. Splitting on ";" would miscount any
        # file containing a semicolon inside a string literal, a $$-quoted
        # body, or a BEGIN ... END block.
        try:
            statements = sqlglot.parse(text, read=source_dialect.value)
        except Exception as exc:  # noqa: BLE001 - sqlglot raises several types
            findings.append(
                ScanFinding(
                    relative, 0, "OUT_OF_SUBSET", None,
                    "CERTIFIED_DDL_PARSE_FAILED",
                    f"{source_dialect.value} parser rejected the file: {exc}",
                    "source-format", "",
                )
            )
            continue

        index = 0
        for statement in statements:
            if statement is None:
                continue  # a comment or trailing separator, not a statement
            index += 1
            status, code, reason = _classify(statement, source_dialect)
            family = BLOCKER_CATALOG.get(code or "", (None, ""))[0] if code else None
            findings.append(
                ScanFinding(
                    relative, index, status, type(statement).__name__,
                    code, reason, family, _excerpt(statement),
                )
            )

    return _build_report(root, source_dialect, findings, examples_per_blocker, include_all_findings)


def _distinct_examples(group: list[ScanFinding], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for finding in group:
        key = finding.reason or finding.excerpt
        if key in seen:
            continue
        seen.add(key)
        out.append(finding.excerpt)
        if len(out) >= limit:
            break
    return out


def _build_report(
    root: Path,
    source_dialect: Dialect,
    findings: list[ScanFinding],
    examples_per_blocker: int,
    include_all_findings: bool,
) -> FeasibilityReport:
    in_subset = sum(1 for f in findings if f.status == "IN_SUBSET")
    blocked = [f for f in findings if f.status == "OUT_OF_SUBSET"]
    scan_errors = sum(1 for f in findings if f.status == "SCAN_ERROR")
    denominator = in_subset + len(blocked)

    by_code: dict[str, list[ScanFinding]] = {}
    for finding in blocked:
        by_code.setdefault(finding.reason_code or "UNKNOWN", []).append(finding)

    blockers = [
        BlockerGroup(
            reason_code=code,
            family=BLOCKER_CATALOG.get(code, (None, ""))[0],
            what=BLOCKER_CATALOG.get(code, (None, group[0].reason or "no description available"))[1],
            count=len(group),
            distinct_reasons=len({f.reason for f in group}),
            share_of_blocked=round(len(group) / len(blocked), 3) if blocked else 0.0,
            # Deduplicated, so the examples show distinct problems rather
            # than the same line quoted five times.
            example_statements=_distinct_examples(group, examples_per_blocker),
        )
        for code, group in by_code.items()
    ]
    # Frequency first; ties broken by code so the report is deterministic
    # and diffable across runs.
    blockers.sort(key=lambda b: (-b.count, b.reason_code))

    family_counts: dict[str, int] = {}
    for finding in blocked:
        if finding.family:
            family_counts[finding.family] = family_counts.get(finding.family, 0) + 1
    families = [
        FamilyGroup(name, count, round(count / len(blocked), 3) if blocked else 0.0)
        for name, count in family_counts.items()
    ]
    families.sort(key=lambda f: (-f.count, f.family))

    caveats = [
        "This is an UPPER BOUND. Parsing proves a statement is inside certified-ddl-v1 from the SOURCE "
        "side. During a real run each emission is re-parsed by the TARGET dialect in strict mode, and a "
        "statement can still be reported BLOCKED there.",
        "Counts are exact -- every statement was really parsed by sqlglot and by this engine's certified "
        "parser. Nothing is sampled or extrapolated.",
        "Read the `Distinct` column, not just the count. A blocker with 342 occurrences but 3 distinct "
        "reasons is one idiom repeated across a schema; widening the subset for it buys far less than the "
        "raw count suggests, and ranking by occurrences alone would misdirect the roadmap.",
        "Statements are split by the real parser, not by semicolons, so string literals, $$-quoted bodies "
        "and BEGIN ... END blocks are counted correctly.",
        "Everything executable stays in the denominator. Unlike the component scanner -- where a function "
        "returning no JSX is a helper rather than a migration unit -- an ALTER TABLE, view or stored "
        "procedure IS work the customer needs done, so excluding it would flatter the ratio by hiding "
        "exactly what this engine cannot do.",
    ]
    if scan_errors:
        caveats.insert(
            0,
            f"{scan_errors} statement(s) produced SCAN_ERROR. Those are engine defects, NOT subset "
            "boundaries, and they are excluded from the blocker ranking. Please report them.",
        )

    return FeasibilityReport(
        schema_version="1.0",
        kind="elmos.sql-dialect-feasibility-scan",
        profile="certified-ddl-v1 + certified-alter-v1",
        repository=str(root.resolve()),
        source_dialect=source_dialect.value,
        scanned_at=datetime.now(timezone.utc).isoformat(),
        totals={
            "discovered": denominator,
            "inSubset": in_subset,
            "outOfSubset": len(blocked),
            "scanErrors": scan_errors,
            "files": len({f.source_path for f in findings}),
        },
        upper_bound_coverage=round(in_subset / denominator, 3) if denominator else 0.0,
        blockers=blockers,
        families=families,
        findings=findings if include_all_findings else [f for f in findings if f.status != "IN_SUBSET"],
        caveats=caveats,
    )


def report_to_dict(report: FeasibilityReport) -> dict[str, object]:
    return asdict(report)


def report_to_json(report: FeasibilityReport) -> str:
    return json.dumps(report_to_dict(report), indent=2) + "\n"


def render_markdown(report: FeasibilityReport) -> str:
    """Human-readable rendering of the same facts.

    A migration decision gets made by someone who will not read JSON, and
    if the honest version is only machine-readable then the optimistic
    version is what reaches the decision.
    """
    totals = report.totals

    def pct(value: float) -> str:
        return f"{value * 100:.1f}%"

    lines: list[str] = [
        f"# Feasibility scan -- {report.profile}",
        "",
        f"- Repository: `{report.repository}`",
        f"- Source dialect: `{report.source_dialect}`",
        f"- Scanned: {report.scanned_at}",
        "",
        "## Result",
        "",
        f"**{totals['inSubset']} of {totals['discovered']} statements are inside the certified "
        f"subset ({pct(report.upper_bound_coverage)}, upper bound), across {totals['files']} files.**",
        "",
        "| | Count |",
        "|---|---|",
        f"| SQL files | {totals['files']} |",
        f"| Statements discovered | {totals['discovered']} |",
        f"| In subset (upper bound) | {totals['inSubset']} |",
        f"| Out of subset | {totals['outOfSubset']} |",
        f"| Scan errors (engine defects) | {totals['scanErrors']} |",
        "",
    ]

    if report.blockers:
        lines += [
            "## What is blocking, most frequent first",
            "",
            "`Distinct` is the number that should drive a roadmap: a high count with a low "
            "distinct value is one idiom copy-pasted across a schema, not many problems.",
            "",
            "| Blocker | Statements | Distinct | Share | What it is |",
            "|---|---|---|---|---|",
        ]
        for blocker in report.blockers:
            lines.append(
                f"| `{blocker.reason_code}` | {blocker.count} | {blocker.distinct_reasons} | "
                f"{pct(blocker.share_of_blocked)} | {blocker.what} |"
            )
        lines += ["", "### By family", "", "| Family | Statements | Share |", "|---|---|---|"]
        for family in report.families:
            lines.append(f"| {family.family} | {family.count} | {pct(family.share_of_blocked)} |")
        lines.append("")
        top = report.blockers[0]
        if len(report.blockers) > 1:
            lines += [
                f"Removing the single largest blocker (`{top.reason_code}`) would move at most "
                f"{top.count} statement(s) -- \"at most\" because a statement can be blocked by more "
                "than one construct and only the first one encountered is reported here.",
                "",
            ]

    lines += ["## Read this before deciding", ""]
    lines += [f"- {caveat}" for caveat in report.caveats]
    lines.append("")
    return "\n".join(lines)


def iter_statement_excerpts(findings: Iterable[ScanFinding]) -> list[str]:
    """Convenience for callers building their own summaries."""
    return [f.excerpt for f in findings]
