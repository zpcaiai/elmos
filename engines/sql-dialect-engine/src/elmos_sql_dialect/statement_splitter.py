"""Quote-aware statement splitter -- the fallback when the real parser cannot
take a whole file.

`scan_repository` splits with sqlglot on purpose: splitting on ";" miscounts
any file containing a semicolon inside a string literal, a $$-quoted body or a
BEGIN ... END block, and that comment is right. But when the parser refuses the
*file*, today the whole file collapses to one finding -- measured, that is 750 KB
of real schema across 5 files thrown away by 5 single constructs, and it flatters
every coverage ratio by shrinking the denominator exactly where the hard input is.

So the parser stays the primary splitter and this is only the fallback. It is
lexical, not grammatical: it tracks the things that can legally contain a
semicolon and splits on the ones that cannot.

Client-side constructs are split out of the SQL stream before the dialect
parser sees them. Measured 2026-09-01 (FINDINGS-2026-09-01-b3.md):

- psql ``\\set`` / ``\\c`` are newline-terminated, not semicolon-terminated.
  Leaving them glued to the next statement reported a parse failure that
  blamed the dialect grammar for a client command.
- MySQL ``source path`` / ``\\. path`` never reach a server.
- MySQL ``DELIMITER`` changes the statement terminator. Not recognising it
  sliced routine bodies into fake PARSE_FAILED fragments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RawStatement:
    text: str
    #: 1-based line where the statement starts, for locating it in the file.
    start_line: int


_MYSQL_SOURCE = re.compile(r"^(?:source|\.)\s+\S+\s*$", re.IGNORECASE)
_MYSQL_DELIMITER = re.compile(r"^DELIMITER\s+(\S+)\s*$", re.IGNORECASE)


def _dialect_name(dialect: object | None) -> str | None:
    if dialect is None:
        return None
    raw = getattr(dialect, "value", dialect)
    return str(raw).strip().lower()


def _is_mysql(dialect: object | None) -> bool:
    return _dialect_name(dialect) == "mysql"


def _dollar_tag(source: str, index: int) -> str | None:
    """Return the full `$tag$` opener at `index`, or None."""

    if source[index] != "$":
        return None
    end = index + 1
    while end < len(source) and (source[end].isalnum() or source[end] == "_"):
        end += 1
    if end < len(source) and source[end] == "$":
        return source[index : end + 1]
    return None


def _strip_leading_trivia(sql: str) -> str:
    """Remove ordinary comments and whitespace before the first payload token.

    Optimizer/version hints (``/*+`` / ``/*!``) and unterminated block comments
    are retained, matching ``parser.strip_leading_comments``. The splitter
    needs this locally so a ``--`` header cannot hide a following ``\\set``.
    """

    index = 0
    length = len(sql)
    while index < length:
        while index < length and sql[index].isspace():
            index += 1
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            if newline < 0:
                return ""
            index = newline + 1
            continue
        if sql.startswith("/*", index):
            if sql.startswith("/*+", index) or sql.startswith("/*!", index):
                return sql[index:]
            closing = sql.find("*/", index + 2)
            if closing < 0:
                return sql[index:]
            index = closing + 2
            continue
        break
    return sql[index:]


def _first_payload_line(text: str) -> str:
    return _strip_leading_trivia(text).split("\n", 1)[0].strip()


def looks_like_client_directive(text: str, dialect: str | None = None) -> bool:
    """True when *text* is a client-side command, not a SQL statement.

    Leading comments are stripped first: ``-- prose\\n\\set ON_ERROR_STOP on``
    is a directive, not a parse failure. MySQL ``source`` / ``DELIMITER`` are
    recognised only for the mysql dialect -- ``source`` is a legal identifier
    elsewhere.
    """

    payload = _strip_leading_trivia(text)
    if payload.startswith("\\"):
        return True
    if not _is_mysql(dialect):
        return False
    first_line = _first_payload_line(text)
    return (
        _MYSQL_SOURCE.fullmatch(first_line) is not None
        or _MYSQL_DELIMITER.fullmatch(first_line) is not None
    )


def _mysql_delimiter(text: str) -> str | None:
    match = _MYSQL_DELIMITER.fullmatch(_first_payload_line(text))
    if match is None:
        return None
    return match.group(1)


def _line_end(source: str, index: int) -> int:
    newline = source.find("\n", index)
    return len(source) if newline < 0 else newline + 1


def _skip_whitespace(source: str, index: int, line: int) -> tuple[int, int]:
    length = len(source)
    while index < length and source[index] in " \t\r\n":
        if source[index] == "\n":
            line += 1
        index += 1
    return index, line


def split_statements(source: str, dialect: str | None = None) -> list[RawStatement]:
    statements: list[RawStatement] = []
    buffer: list[str] = []
    line = 1
    start_line = 1
    index = 0
    length = len(source)
    terminator = ";"
    mysql = _is_mysql(dialect)

    def flush() -> None:
        nonlocal start_line, index, line
        text = "".join(buffer).strip()
        buffer.clear()
        if text:
            statements.append(RawStatement(text=text, start_line=start_line))
        index, line = _skip_whitespace(source, index, line)
        start_line = line

    while index < length:
        char = source[index]
        at_line_start = index == 0 or source[index - 1] == "\n"

        # -- line comment
        if char == "-" and source.startswith("--", index):
            end = source.find("\n", index)
            end = length if end == -1 else end
            buffer.append(source[index:end])
            index = end
            continue

        # /* block comment */ -- not nested in standard SQL
        if char == "/" and source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = length if end == -1 else end + 2
            chunk = source[index:end]
            line += chunk.count("\n")
            buffer.append(chunk)
            index = end
            continue

        # 'string literal' with '' escaping
        if char == "'":
            end = index + 1
            while end < length:
                if source[end] == "'":
                    if end + 1 < length and source[end + 1] == "'":
                        end += 2
                        continue
                    end += 1
                    break
                end += 1
            chunk = source[index:end]
            line += chunk.count("\n")
            buffer.append(chunk)
            index = end
            continue

        # "quoted identifier" / `backtick identifier`
        if char in '"`':
            closer = char
            end = index + 1
            while end < length and source[end] != closer:
                end += 1
            end = min(end + 1, length)
            chunk = source[index:end]
            line += chunk.count("\n")
            buffer.append(chunk)
            index = end
            continue

        # $$ ... $$ / $tag$ ... $tag$ body -- semicolons inside are not separators.
        # Skip when the tag is the active MySQL DELIMITER: sakila uses
        # ``DELIMITER $$`` and then ``END $$``, which is a terminator, not a
        # postgres dollar quote.
        tag = _dollar_tag(source, index)
        if tag is not None and tag != terminator:
            end = source.find(tag, index + len(tag))
            end = length if end == -1 else end + len(tag)
            chunk = source[index:end]
            line += chunk.count("\n")
            buffer.append(chunk)
            index = end
            continue

        if at_line_start and not _strip_leading_trivia("".join(buffer)).strip():
            # psql client commands are newline-terminated. Measured: a ``--``
            # header glued ``\set ON_ERROR_STOP on`` onto the following
            # ``BEGIN``, which then reported as PARSE_FAILED.
            look = index
            while look < length and source[look] in " \t":
                look += 1
            if look < length and source.startswith("\\", look):
                end = _line_end(source, look)
                chunk = source[index:end]
                line += chunk.count("\n")
                buffer.append(chunk)
                index = end
                flush()
                continue
            if mysql:
                line_end = _line_end(source, look if look < length else index)
                first_line = source[index:line_end].strip()
                if _MYSQL_SOURCE.fullmatch(first_line) or _MYSQL_DELIMITER.fullmatch(
                    first_line
                ):
                    chunk = source[index:line_end]
                    line += chunk.count("\n")
                    buffer.append(chunk)
                    index = line_end
                    new_delimiter = _mysql_delimiter("".join(buffer))
                    flush()
                    if new_delimiter is not None:
                        terminator = new_delimiter
                    continue

        if terminator != ";" and source.startswith(terminator, index):
            index += len(terminator)
            flush()
            continue

        if terminator == ";" and char == ";":
            index += 1
            flush()
            continue

        if char == "\n":
            line += 1
        buffer.append(char)
        index += 1

    text = "".join(buffer).strip()
    if text:
        statements.append(RawStatement(text=text, start_line=start_line))
    return statements
