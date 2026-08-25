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
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawStatement:
    text: str
    #: 1-based line where the statement starts, for locating it in the file.
    start_line: int


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


def split_statements(source: str) -> list[RawStatement]:
    statements: list[RawStatement] = []
    buffer: list[str] = []
    line = 1
    start_line = 1
    index = 0
    length = len(source)

    while index < length:
        char = source[index]

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

        # $$ ... $$ / $tag$ ... $tag$ body -- semicolons inside are not separators
        tag = _dollar_tag(source, index)
        if tag is not None:
            end = source.find(tag, index + len(tag))
            end = length if end == -1 else end + len(tag)
            chunk = source[index:end]
            line += chunk.count("\n")
            buffer.append(chunk)
            index = end
            continue

        if char == ";":
            text = "".join(buffer).strip()
            if text:
                statements.append(RawStatement(text=text, start_line=start_line))
            buffer = []
            index += 1
            # the next statement starts after any whitespace that follows
            while index < length and source[index] in " \t\r\n":
                if source[index] == "\n":
                    line += 1
                index += 1
            start_line = line
            continue

        if char == "\n":
            line += 1
        buffer.append(char)
        index += 1

    text = "".join(buffer).strip()
    if text:
        statements.append(RawStatement(text=text, start_line=start_line))
    return statements
