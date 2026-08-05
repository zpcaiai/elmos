"""Java regex -> Python regex, over a deliberately small verified subset.

Java's and Python's regex dialects look identical and are not.  The three
differences that bite hardest are silent:

* ``.`` excludes *five* line terminators in Java (``\\n \\r \\u0085 \\u2028
  \\u2029``) and only ``\\n`` in Python.
* ``\\d``, ``\\w`` and ``\\s`` are ASCII-only in Java by default and
  Unicode-aware in Python, so ``"٣".matches("\\\\d")`` is false in Java and true
  in Python.
* ``(?<name>...)`` is a named group in Java and a syntax error in Python, which
  spells it ``(?P<name>...)``.

The first two are handled by rewriting: ``.`` becomes the explicit negated class,
and the compiled pattern gets ``re.ASCII``.  Everything else that differs -- and
everything whose equivalence has not been checked -- is **refused**, with the
offending construct named.  The subset that remains (literals, character
classes, anchors, groups, alternation, greedy and reluctant quantifiers) is what
real code overwhelmingly uses, and it is the part where the two engines agree.
"""

from __future__ import annotations

#: What ``.`` means in Java: any character except a line terminator.  Python's
#: ``.`` excludes only \n, so leaving it alone would make the translation match
#: strings the original rejected.
JAVA_DOT = "[^\\n\\r\\u0085\\u2028\\u2029]"


class UnsupportedRegex(Exception):
    """A construct outside the verified subset, named so it can be reported."""


def translate(pattern: str) -> str:
    """Return the Python spelling of ``pattern``, or raise UnsupportedRegex."""

    out: list[str] = []
    i = 0
    n = len(pattern)
    in_class = False
    while i < n:
        ch = pattern[i]

        if ch == "\\":
            if i + 1 >= n:
                raise UnsupportedRegex("pattern ends with a dangling backslash")
            nxt = pattern[i + 1]
            if nxt in "pP":
                raise UnsupportedRegex(
                    "\\p{...} Unicode property classes: Java's category names "
                    "and Python's do not agree"
                )
            if nxt in "QE":
                raise UnsupportedRegex("\\Q...\\E literal quoting is Java-only")
            if nxt in "hHvVRXGZzAk":
                raise UnsupportedRegex(f"\\{nxt} has no Python equivalent")
            if nxt.isdigit():
                raise UnsupportedRegex(
                    "backreferences are numbered differently once groups are "
                    "rewritten, so they are not translated"
                )
            out.append(ch)
            out.append(nxt)
            i += 2
            continue

        if in_class:
            if ch == "]":
                in_class = False
                out.append(ch)
                i += 1
                continue
            if pattern.startswith("&&", i):
                raise UnsupportedRegex(
                    "[a&&b] character-class intersection is Java-only"
                )
            out.append(ch)
            i += 1
            continue

        if ch == "[":
            in_class = True
            out.append(ch)
            i += 1
            continue

        if ch == ".":
            out.append(JAVA_DOT)
            i += 1
            continue

        if ch == "(":
            if pattern.startswith("(?", i):
                rest = pattern[i + 2 :]
                if rest.startswith(":") or rest.startswith("=") or rest.startswith("!"):
                    out.append(pattern[i : i + 3])
                    i += 3
                    continue
                if rest.startswith("<=") or rest.startswith("<!"):
                    out.append(pattern[i : i + 4])
                    i += 4
                    continue
                if rest.startswith("<"):
                    raise UnsupportedRegex(
                        "(?<name>...) named groups: Python spells them "
                        "(?P<name>...), and renaming them would change any "
                        "group reference the caller makes"
                    )
                raise UnsupportedRegex(
                    "inline flags and other (?...) constructs are not "
                    "translated: Java's case folding is ASCII-only by default "
                    "and Python's is not"
                )
            out.append(ch)
            i += 1
            continue

        if ch in "*+?}" or ch == "{":
            # A possessive quantifier (`a*+`, `a{2,3}+`) has no Python
            # equivalent at all -- Python has no possessive form and no atomic
            # group before 3.11's (?>...), and the difference is only visible on
            # backtracking, which makes it exactly the kind of thing that would
            # slip through a spot check.
            if ch in "*+?" and i + 1 < n and pattern[i + 1] == "+":
                raise UnsupportedRegex(
                    "possessive quantifiers have no Python equivalent"
                )
            if ch == "}" and i + 1 < n and pattern[i + 1] == "+":
                raise UnsupportedRegex(
                    "possessive quantifiers have no Python equivalent"
                )
            out.append(ch)
            i += 1
            continue

        out.append(ch)
        i += 1

    if in_class:
        raise UnsupportedRegex("unterminated character class")
    return "".join(out)
