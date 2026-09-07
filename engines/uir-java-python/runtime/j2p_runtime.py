"""Java semantics, implemented in Python.

Generated Python does not use Python's arithmetic directly.  Python integers are
arbitrary precision, Python's ``//`` floors, Python's ``%`` takes the sign of the
divisor, and Python's ``repr(float)`` does not spell numbers the way
``Double.toString`` does.  Every one of those differences silently changes
program behaviour, and every one of them is a bug a migration is supposed not to
introduce.  So the emitter routes arithmetic through this module instead.

Nothing here is decorative.  Each rule below is asserted by a differential test
that compiles and runs the original Java and compares the two outputs byte for
byte, and by a mutation experiment that deletes the rule and requires the tests
to go red.
"""

from __future__ import annotations

import math
import struct

# java.time lives in its own module: it is large, and it is built on Java's own
# (seconds, nanos) model rather than Python's datetime, whose precision and year
# range are both narrower than Java's.
from j2p_time import (  # noqa: F401
    ChronoUnit,
    Clock,
    DateTimeExceptionJ,
    DateTimeFormatter,
    DateTimeParseExceptionJ,
    Duration,
    Instant,
    LocalDate,
    LocalDateTime,
    LocalTime,
    ZoneOffset,
)

INT_MIN = -(2 ** 31)
INT_MAX = 2 ** 31 - 1
LONG_MIN = -(2 ** 63)
LONG_MAX = 2 ** 63 - 1
CHAR_MAX = 2 ** 16 - 1


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


from j2p_errors import (  # noqa: F401
    ArithmeticExceptionJ,
    ArrayIndexOutOfBoundsExceptionJ,
    ClassCastExceptionJ,
    IllegalArgumentExceptionJ,
    IllegalStateExceptionJ,
    IndexOutOfBoundsExceptionJ,
    JavaException,
    JavaThrowable,
    ArrayStoreExceptionJ,
    CloneNotSupportedExceptionJ,
    ConcurrentModificationExceptionJ,
    FileNotFoundExceptionJ,
    IOExceptionJ,
    InterruptedExceptionJ,
    NoSuchAlgorithmExceptionJ,
    NoSuchFileExceptionJ,
    TimeoutExceptionJ,
    UncheckedIOExceptionJ,
    NoSuchElementExceptionJ,
    NullPointerExceptionJ,
    SecurityExceptionJ,
    NumberFormatExceptionJ,
    RuntimeExceptionJ,
    StringIndexOutOfBoundsExceptionJ,
    UnsupportedOperationExceptionJ,
)


EXCEPTION_BY_SIMPLE_NAME: dict[str, type[JavaThrowable]] = {
    "DateTimeException": DateTimeExceptionJ,
    "DateTimeParseException": DateTimeParseExceptionJ,
    "Throwable": JavaThrowable,
    "Exception": JavaException,
    "RuntimeException": RuntimeExceptionJ,
    "ArithmeticException": ArithmeticExceptionJ,
    "NullPointerException": NullPointerExceptionJ,
    "ClassCastException": ClassCastExceptionJ,
    "NumberFormatException": NumberFormatExceptionJ,
    "IndexOutOfBoundsException": IndexOutOfBoundsExceptionJ,
    "ArrayIndexOutOfBoundsException": ArrayIndexOutOfBoundsExceptionJ,
    "StringIndexOutOfBoundsException": StringIndexOutOfBoundsExceptionJ,
    "IllegalArgumentException": IllegalArgumentExceptionJ,
    "IllegalStateException": IllegalStateExceptionJ,
    "NoSuchElementException": NoSuchElementExceptionJ,
    "SecurityException": SecurityExceptionJ,
    "ConcurrentModificationException": ConcurrentModificationExceptionJ,
    "ArrayStoreException": ArrayStoreExceptionJ,
    "CloneNotSupportedException": CloneNotSupportedExceptionJ,
    "InterruptedException": InterruptedExceptionJ,
    "IOException": IOExceptionJ,
    "UncheckedIOException": UncheckedIOExceptionJ,
    "FileNotFoundException": FileNotFoundExceptionJ,
    "NoSuchFileException": NoSuchFileExceptionJ,
    "NoSuchAlgorithmException": NoSuchAlgorithmExceptionJ,
    "TimeoutException": TimeoutExceptionJ,
    "UnsupportedOperationException": UnsupportedOperationExceptionJ,
}


def throwable_class(simple_name: str) -> type[JavaThrowable]:
    try:
        return EXCEPTION_BY_SIMPLE_NAME[simple_name]
    except KeyError:
        raise KeyError(
            f"unsupported Java throwable {simple_name!r}; the front end must "
            f"reject it rather than let it reach the runtime"
        ) from None


# ---------------------------------------------------------------------------
# Integral wrapping
# ---------------------------------------------------------------------------


def jint(value: int) -> int:
    """Wrap to 32-bit two's complement, as every Java ``int`` operation does."""

    return ((value + 2 ** 31) & (2 ** 32 - 1)) - 2 ** 31


def jlong(value: int) -> int:
    return ((value + 2 ** 63) & (2 ** 64 - 1)) - 2 ** 63


def jbyte(value: int) -> int:
    return ((value + 2 ** 7) & (2 ** 8 - 1)) - 2 ** 7


def jshort(value: int) -> int:
    return ((value + 2 ** 15) & (2 ** 16 - 1)) - 2 ** 15


def jchar(value: int) -> int:
    """``char`` is the one unsigned integral type in Java."""

    return value & CHAR_MAX


WRAP = {"int": jint, "long": jlong, "byte": jbyte, "short": jshort, "char": jchar}


def wrap(kind: str, value: int) -> int:
    return WRAP[kind](value)


# ---------------------------------------------------------------------------
# Integer division and remainder
# ---------------------------------------------------------------------------


def idiv(kind: str, a: int, b: int) -> int:
    """Java integer division: truncates toward zero, not toward -infinity.

    ``-7 / 2`` is ``-3`` in Java and ``-4`` with Python's ``//``.
    """

    if b == 0:
        raise ArithmeticExceptionJ("/ by zero")
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return WRAP[kind](q)


def irem(kind: str, a: int, b: int) -> int:
    """Java remainder takes the sign of the *dividend*.

    ``-7 % 2`` is ``-1`` in Java and ``1`` in Python.
    """

    if b == 0:
        raise ArithmeticExceptionJ("/ by zero")
    r = abs(a) % abs(b)
    if a < 0:
        r = -r
    return WRAP[kind](r)


def ddiv(a: float, b: float) -> float:
    """Floating division never throws in Java; it produces inf/NaN."""

    if b == 0.0:
        if a == 0.0 or math.isnan(a):
            return math.nan
        sign = math.copysign(1.0, a) * math.copysign(1.0, b)
        return math.inf if sign > 0 else -math.inf
    try:
        return a / b
    except OverflowError:  # pragma: no cover - defensive
        return math.inf


def drem(a: float, b: float) -> float:
    if math.isnan(a) or math.isnan(b) or math.isinf(a) or b == 0.0:
        return math.nan
    if math.isinf(b):
        return a
    return math.fmod(a, b)


# ---------------------------------------------------------------------------
# Shifts
# ---------------------------------------------------------------------------


def shl(kind: str, a: int, b: int) -> int:
    """Java masks the shift distance to 5 bits for int, 6 bits for long."""

    b &= 63 if kind == "long" else 31
    return WRAP[kind](a << b)


def shr(kind: str, a: int, b: int) -> int:
    b &= 63 if kind == "long" else 31
    return WRAP[kind](a >> b)


def ushr(kind: str, a: int, b: int) -> int:
    """``>>>`` shifts in zeros, operating on the unsigned bit pattern."""

    width = 64 if kind == "long" else 32
    b &= width - 1
    return WRAP[kind]((a & (2 ** width - 1)) >> b)


# ---------------------------------------------------------------------------
# Narrowing conversions
# ---------------------------------------------------------------------------


def d2i(value: float) -> int:
    """``(int) someDouble``: NaN becomes 0 and out-of-range *saturates*.

    Python's ``int()`` raises on NaN and never saturates, so a naive
    translation of a cast turns a silently clamped value into a crash.
    """

    if math.isnan(value):
        return 0
    if value >= INT_MAX:
        return INT_MAX
    if value <= INT_MIN:
        return INT_MIN
    return int(value)


def d2l(value: float) -> int:
    if math.isnan(value):
        return 0
    if value >= LONG_MAX:
        return LONG_MAX
    if value <= LONG_MIN:
        return LONG_MIN
    return int(value)


def i2d(value: int) -> float:
    return float(value)


def f32(value: float) -> float:
    """Round a Python double to the nearest IEEE-754 single."""

    return struct.unpack("<f", struct.pack("<f", value))[0]


# ---------------------------------------------------------------------------
# String conversion
# ---------------------------------------------------------------------------


def jdouble_to_string(value: float) -> str:
    """Reproduce ``Double.toString``.

    Java switches to scientific notation outside ``[1e-3, 1e7)`` and spells it
    ``1.0E7``; Python's ``repr`` switches outside ``[1e-4, 1e16)`` and spells it
    ``1e+16``.  Both pick the shortest round-tripping digit string, so the digits
    agree and only the *formatting* has to be redone here.
    """

    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    if value == 0.0:
        return "-0.0" if math.copysign(1.0, value) < 0 else "0.0"

    negative = value < 0
    magnitude = abs(value)

    digits, exponent = _shortest_digits(magnitude)

    if 1e-3 <= magnitude < 1e7:
        text = _plain_decimal(digits, exponent)
    else:
        text = _scientific(digits, exponent)
    return "-" + text if negative else text


def _shortest_digits(magnitude: float) -> tuple[str, int]:
    """Return ``(digits, exponent)`` with value == 0.d1d2... * 10**exponent.

    Uses Python's shortest round-trip repr as the digit source.
    """

    text = repr(magnitude)
    if "e" in text or "E" in text:
        mantissa, _, exp_text = text.replace("E", "e").partition("e")
        exponent = int(exp_text)
    else:
        mantissa, exponent = text, 0

    if "." in mantissa:
        int_part, _, frac_part = mantissa.partition(".")
    else:
        int_part, frac_part = mantissa, ""

    digits = (int_part + frac_part).lstrip("0")
    leading_zeros = len(int_part + frac_part) - len((int_part + frac_part).lstrip("0"))
    # Decimal point sits after len(int_part) digits; shift by stripped zeros.
    exponent += len(int_part) - leading_zeros
    digits = digits.rstrip("0") or "0"
    return digits, exponent


def _plain_decimal(digits: str, exponent: int) -> str:
    if exponent <= 0:
        return "0." + "0" * (-exponent) + digits
    if exponent >= len(digits):
        return digits + "0" * (exponent - len(digits)) + ".0"
    return digits[:exponent] + "." + digits[exponent:]


def _scientific(digits: str, exponent: int) -> str:
    head = digits[0]
    tail = digits[1:] or "0"
    return f"{head}.{tail}E{exponent - 1}"


def jstr(value) -> str:
    """Java's string conversion, as applied by ``+`` and ``String.valueOf``."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, JChar):
        return chr(value.code)
    if isinstance(value, float):
        return jdouble_to_string(value)
    if isinstance(value, JArray):
        return value.java_identity()
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    to_string = getattr(value, "toString", None)
    if callable(to_string):
        return to_string()
    return str(value)


def concat(*parts) -> str:
    return "".join(jstr(p) for p in parts)


class JEnum:
    """One enum constant.

    A constant used to be emitted as its ordinal, which is right for exactly one
    observation (comparing two constants) and wrong for every other: Java prints
    ``ADD``, not ``0``, and ``name()`` and ``ordinal()`` are separate things.
    Being a distinct object per constant also makes ``==`` -- identity in Java,
    and the way enums are actually compared -- come out right without any
    special handling.

    ``equals``/``hashCode`` are left as Python's defaults, which are identity
    based exactly as Java's are.
    """

    __slots__ = ("_enum", "_name", "_ordinal")

    def __init__(self, enum_name: str, name: str, ordinal: int) -> None:
        self._enum = enum_name
        self._name = name
        self._ordinal = ordinal

    def name(self) -> str:
        return self._name

    def ordinal(self) -> int:
        return self._ordinal

    def toString(self) -> str:
        return self._name

    def compareTo(self, other: "JEnum") -> int:
        return self._ordinal - other._ordinal

    def __str__(self) -> str:
        return self._name

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self._enum}.{self._name}"


class JChar:
    """A ``char`` value that remembers it is a character, not a number.

    Java's ``System.out.println('a' + 1)`` prints ``98`` while
    ``println("" + 'a')`` prints ``a``.  Carrying the distinction in the value
    (rather than losing it at the first assignment) is what lets the emitter get
    both cases right.
    """

    __slots__ = ("code",)

    def __init__(self, code: int) -> None:
        self.code = code & CHAR_MAX

    def __int__(self) -> int:
        return self.code

    def __index__(self) -> int:
        return self.code

    def __eq__(self, other) -> bool:
        if isinstance(other, JChar):
            return self.code == other.code
        if isinstance(other, int):
            return self.code == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.code)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"JChar({self.code!r})"


def char_of(value) -> JChar:
    if isinstance(value, JChar):
        return value
    if isinstance(value, str):
        if len(value) != 1:
            raise IllegalArgumentExceptionJ("not a single character")
        return JChar(ord(value))
    return JChar(int(value))


def num(value):
    """Unwrap a ``JChar`` for arithmetic, leaving other numbers untouched."""

    return value.code if isinstance(value, JChar) else value


# ---------------------------------------------------------------------------
# Arrays
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "int": 0,
    "long": 0,
    "short": 0,
    "byte": 0,
    "double": 0.0,
    "float": 0.0,
    "boolean": False,
}


class JArray:
    """A fixed-length Java array with bounds checking and default values.

    Python lists grow, accept negative indices, and raise ``IndexError``.  All
    three differ observably from Java, so arrays get their own type.
    """

    __slots__ = ("data", "element")

    def __init__(self, element: str, length: int | None = None, values=None) -> None:
        self.element = element
        if values is not None:
            self.data = list(values)
        else:
            if length is None:
                raise ValueError("length or values required")
            if length < 0:
                raise NegativeArraySizeExceptionJ(str(length))
            default = _DEFAULTS.get(element, JChar(0) if element == "char" else None)
            self.data = [default] * length

    @property
    def length(self) -> int:
        return len(self.data)

    def _check(self, index: int) -> int:
        index = num(index)
        if index < 0 or index >= len(self.data):
            raise ArrayIndexOutOfBoundsExceptionJ(
                f"Index {index} out of bounds for length {len(self.data)}"
            )
        return index

    def get(self, index: int):
        return self.data[self._check(index)]

    def set(self, index: int, value):
        self.data[self._check(index)] = value
        return value

    def __len__(self) -> int:
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def java_identity(self) -> str:
        return f"[{self.element}@{id(self):x}"


class NegativeArraySizeExceptionJ(RuntimeExceptionJ):
    java_name = "java.lang.NegativeArraySizeException"


EXCEPTION_BY_SIMPLE_NAME["NegativeArraySizeException"] = NegativeArraySizeExceptionJ


def new_array(element: str, length: int) -> JArray:
    return JArray(element, length=num(length))


def array_of(element: str, values) -> JArray:
    return JArray(element, values=list(values))


# ---------------------------------------------------------------------------
# Null checks
# ---------------------------------------------------------------------------


def iabs(kind: str, value: int) -> int:
    """``Math.abs`` on an integral type.

    ``Math.abs(Integer.MIN_VALUE)`` is ``Integer.MIN_VALUE``: negating it
    overflows and wraps.  Python's ``abs`` would return 2147483648, a value the
    Java program can never observe.
    """

    return WRAP[kind](value if value >= 0 else -value)


def nonnull(value, what: str = "value"):
    if value is None:
        raise NullPointerExceptionJ(f"Cannot invoke method because {what} is null")
    return value


# ---------------------------------------------------------------------------
# java.lang.String
# ---------------------------------------------------------------------------


class JString:
    """Static-side helpers for ``String``; instances stay Python ``str``."""

    @staticmethod
    def length(s: str) -> int:
        return len(nonnull(s, "string"))

    @staticmethod
    def charAt(s: str, index: int) -> JChar:
        index = num(index)
        if index < 0 or index >= len(s):
            raise StringIndexOutOfBoundsExceptionJ(
                f"index {index}, length {len(s)}"
            )
        return JChar(ord(s[index]))

    @staticmethod
    def substring(s: str, start: int, end: int | None = None) -> str:
        start = num(start)
        end = len(s) if end is None else num(end)
        if start < 0 or end > len(s) or start > end:
            raise StringIndexOutOfBoundsExceptionJ(
                f"begin {start}, end {end}, length {len(s)}"
            )
        return s[start:end]

    @staticmethod
    def indexOf(s: str, target) -> int:
        if isinstance(target, JChar):
            target = chr(target.code)
        return s.find(target)

    @staticmethod
    def isEmpty(s: str) -> bool:
        return len(s) == 0

    @staticmethod
    def equals(a, b) -> bool:
        return a == b

    @staticmethod
    def toUpperCase(s: str) -> str:
        return s.upper()

    @staticmethod
    def toLowerCase(s: str) -> str:
        return s.lower()

    @staticmethod
    def trim(s: str) -> str:
        # Java's trim strips code points <= U+0020, not Unicode whitespace.
        return s.strip("".join(chr(c) for c in range(0x21)))

    @staticmethod
    def valueOf(value) -> str:
        return jstr(value)

    @staticmethod
    def isBlank(s: str) -> bool:
        # Java's definition is "empty or every code point is
        # Character.isWhitespace", which is NOT Python's str.isspace():
        # Python counts U+00A0 as whitespace and Java does not.
        return all(is_java_whitespace(ord(ch)) for ch in s)

    @staticmethod
    def strip(s: str) -> str:
        start, end = 0, len(s)
        while start < end and is_java_whitespace(ord(s[start])):
            start += 1
        while end > start and is_java_whitespace(ord(s[end - 1])):
            end -= 1
        return s[start:end]

    @staticmethod
    def startsWith(s: str, prefix: str, offset: int = 0) -> bool:
        return s.startswith(prefix, num(offset))

    @staticmethod
    def endsWith(s: str, suffix: str) -> bool:
        return s.endswith(suffix)

    @staticmethod
    def contains(s: str, part) -> bool:
        return jstr(part) in s

    @staticmethod
    def replace(s: str, target, replacement) -> str:
        return s.replace(jstr(target), jstr(replacement))

    @staticmethod
    def lastIndexOf(s: str, target) -> int:
        if isinstance(target, JChar):
            target = chr(target.code)
        return s.rfind(target)

    @staticmethod
    def repeat(s: str, count: int) -> str:
        count = num(count)
        if count < 0:
            raise IllegalArgumentExceptionJ(f"count is negative: {count}")
        return s * count

    @staticmethod
    def concat(s: str, other: str) -> str:
        return s + nonnull(other, "string")

    @staticmethod
    def equalsIgnoreCase(s: str, other) -> bool:
        if other is None:
            return False
        return s.lower() == other.lower()

    @staticmethod
    def compareTo(s: str, other: str) -> int:
        """Java returns the *char difference*, not just its sign.

        ``"a".compareTo("A")`` is 32, not 1.  Programs that print or arithmetic
        on the result would diverge from a sign-only implementation.
        """

        nonnull(other, "string")
        for a, b in zip(s, other):
            if a != b:
                return jint(ord(a) - ord(b))
        return jint(len(s) - len(other))

    @staticmethod
    def hashCode(s: str) -> int:
        """``h = 31*h + c``, wrapped to 32 bits at every step."""

        h = 0
        for ch in s:
            h = jint(31 * h + ord(ch))
        return h

    @staticmethod
    def getBytes(s: str, charset: str) -> JArray:
        """``String.getBytes(charset)``.

        Java returns *signed* bytes, so a UTF-8 continuation byte such as 0xC3
        comes back as -61.  Handing back Python's unsigned values would make
        every hash and every comparison over the result differ.  The no-argument
        overload is refused by the emitter: it uses the platform default
        charset, which depends on the machine the program runs on.
        """

        codec = charset.codec if isinstance(charset, JCharset) else charset
        # Java's String.getBytes(Charset) never throws: the encoder is set to
        # REPLACE, so a character the charset cannot represent becomes '?'.
        # Python raises instead, which would turn a lossy-but-successful call
        # into a crash -- found by the differential on "h\u00e9llo" as ASCII.
        raw = s.encode(codec, errors="replace")
        return array_of("byte", [jbyte(b) for b in raw])

    @staticmethod
    def matches(s: str, translated_pattern: str) -> bool:
        """``String.matches`` requires the *whole* string to match.

        Java\'s ``matches`` is anchored at both ends whether or not the pattern
        says so, which is ``re.fullmatch``, not ``re.match``.  The pattern
        arriving here has already been translated and vetted by the emitter.
        """

        return _compiled(translated_pattern).fullmatch(s) is not None

    @staticmethod
    def split(s: str, separator: str) -> JArray:
        """``String.split`` with a *literal* separator.

        Java drops trailing empty strings when the limit is zero, so
        ``"a,b,,".split(",")`` has length 2, while Python's ``str.split`` gives
        four elements.  The emitter refuses any separator that is not a literal
        without regex metacharacters, because Java and Python regex dialects do
        not agree.
        """

        if separator == "":
            parts = list(s)
        else:
            parts = s.split(separator)
        while len(parts) > 1 and parts[-1] == "":
            parts.pop()
        if parts == [""] and s == "":
            parts = [""]
        return array_of("ref", parts)


def is_java_whitespace(code_point: int) -> bool:
    """``Character.isWhitespace``.

    Deliberately spelled out rather than delegating to Python: Python treats
    U+00A0 (non-breaking space) and U+2007 as whitespace and Java does not,
    which changes what ``isBlank`` and ``strip`` do.
    """

    if code_point in (0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D, 0x1E, 0x1F, 0x20):
        return True
    if code_point in (0xA0, 0x2007, 0x202F):
        return False  # non-breaking: whitespace to Python, not to Java
    import unicodedata

    return unicodedata.category(chr(code_point)) in ("Zs", "Zl", "Zp")


def throwable_to_string(exception: JavaThrowable) -> str:
    """``Throwable.toString``: the class name, and the message when present."""

    if exception.message is None:
        return exception.java_name
    return f"{exception.java_name}: {exception.message}"


def throw(exception: JavaThrowable):
    """Raise from expression position.

    Java allows ``case X -> throw ...`` inside a switch *expression*; Python has
    no raise expression.  Only the selected branch of a conditional is
    evaluated, so routing the throw through a call preserves that.
    """

    raise exception


class UnsupportedOperationOnImmutable(UnsupportedOperationExceptionJ):
    java_name = "java.lang.UnsupportedOperationException"


class JList:
    """An immutable ``List.of`` result.

    Java's ``List.of`` rejects nulls and throws on every mutating method.  A
    plain Python list would silently accept both, so a program that relies on
    the immutability contract would behave differently after migration.
    """

    __slots__ = ("_items",)

    def __init__(self, items) -> None:
        self._items = list(items)
        for item in self._items:
            if item is None:
                raise NullPointerExceptionJ("element is null")

    def size(self) -> int:
        return len(self._items)

    def isEmpty(self) -> bool:
        return not self._items

    def get(self, index: int):
        index = num(index)
        if index < 0 or index >= len(self._items):
            raise IndexOutOfBoundsExceptionJ(
                f"Index {index} out of bounds for length {len(self._items)}"
            )
        return self._items[index]

    def contains(self, value) -> bool:
        return any(_java_equals(item, value) for item in self._items)

    def indexOf(self, value) -> int:
        for index, item in enumerate(self._items):
            if _java_equals(item, value):
                return index
        return -1

    def add(self, *_args):
        raise UnsupportedOperationExceptionJ(None)

    def remove(self, *_args):
        raise UnsupportedOperationExceptionJ(None)

    def set(self, *_args):
        raise UnsupportedOperationExceptionJ(None)

    def clear(self):
        raise UnsupportedOperationExceptionJ(None)

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other) -> bool:
        if isinstance(other, (JList, JArrayList)):
            return list(self) == list(other)
        return NotImplemented

    def __hash__(self) -> int:
        return _java_list_hash(self._items)

    def toString(self) -> str:
        return "[" + ", ".join(jstr(v) for v in self._items) + "]"


class JArrayList:
    """A mutable ``ArrayList`` with Java's bounds behaviour."""

    __slots__ = ("_items",)

    def __init__(self, initial=None) -> None:
        self._items = list(initial) if initial is not None else []

    def size(self) -> int:
        return len(self._items)

    def isEmpty(self) -> bool:
        return not self._items

    def add(self, value) -> bool:
        self._items.append(value)
        return True

    def get(self, index: int):
        index = num(index)
        if index < 0 or index >= len(self._items):
            raise IndexOutOfBoundsExceptionJ(
                f"Index {index} out of bounds for length {len(self._items)}"
            )
        return self._items[index]

    def set(self, index: int, value):
        index = num(index)
        if index < 0 or index >= len(self._items):
            raise IndexOutOfBoundsExceptionJ(
                f"Index {index} out of bounds for length {len(self._items)}"
            )
        previous = self._items[index]
        self._items[index] = value
        return previous

    def contains(self, value) -> bool:
        return any(_java_equals(item, value) for item in self._items)

    def indexOf(self, value) -> int:
        for index, item in enumerate(self._items):
            if _java_equals(item, value):
                return index
        return -1

    def clear(self) -> None:
        self._items.clear()

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other) -> bool:
        if isinstance(other, (JList, JArrayList)):
            return list(self) == list(other)
        return NotImplemented

    def __hash__(self) -> int:
        return _java_list_hash(self._items)

    def toString(self) -> str:
        return "[" + ", ".join(jstr(v) for v in self._items) + "]"


def _java_equals(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, JChar) or isinstance(b, JChar):
        return num(a) == num(b)
    return a == b


def _java_list_hash(items) -> int:
    result = 1
    for item in items:
        result = jint(31 * result + java_hash_code(item))
    return jint(result)


def java_hash_code(value) -> int:
    """``Object.hashCode`` for the values this translation produces."""

    if value is None:
        return 0
    if isinstance(value, bool):
        return 1231 if value else 1237
    if isinstance(value, str):
        return JString.hashCode(value)
    if isinstance(value, JChar):
        return value.code
    if isinstance(value, int):
        return jint(value ^ (value >> 32)) if not (INT_MIN <= value <= INT_MAX) else jint(value)
    if isinstance(value, float):
        import struct as _struct

        bits = _struct.unpack("<q", _struct.pack("<d", value))[0]
        return jint(bits ^ ((bits >> 32) & 0xFFFFFFFF))
    hash_code = getattr(value, "hashCode", None)
    if callable(hash_code):
        return hash_code()
    return jint(hash(value))


class _JKey:
    """A dict key that hashes and compares the way Java's map keys do.

    Python's ``dict`` uses ``__hash__``/``__eq__``; Java's uses
    ``hashCode``/``equals``.  They agree for strings and for the classes this
    translation generates, and disagree in two places that matter: ``True == 1``
    and ``1.0 == 1`` are true in Python and false in Java (a ``Boolean`` key and
    an ``Integer`` key are never equal, nor are ``Integer`` and ``Double``).
    Wrapping the key in its Java type makes the distinction survive.
    """

    __slots__ = ("value", "_kind", "_hash")

    def __init__(self, value) -> None:
        self.value = value
        if value is None:
            self._kind, self._hash = "null", 0
        elif isinstance(value, bool):
            self._kind, self._hash = "bool", java_hash_code(value)
        elif isinstance(value, JChar):
            self._kind, self._hash = "char", value.code
        elif isinstance(value, float):
            self._kind, self._hash = "float", java_hash_code(value)
        elif isinstance(value, int):
            self._kind, self._hash = "int", java_hash_code(value)
        elif isinstance(value, str):
            self._kind, self._hash = "str", java_hash_code(value)
        else:
            self._kind, self._hash = "obj", java_hash_code(value)

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other) -> bool:
        if not isinstance(other, _JKey):
            return NotImplemented
        if self._kind != other._kind:
            return False
        if self._kind == "char":
            return self.value.code == other.value.code
        return _java_equals(self.value, other.value)


class JMap:
    """A Java ``Map``.

    Iteration order is the interesting part.  ``HashMap`` and ``Map.of`` leave it
    *unspecified* -- and ``Map.of`` actively randomises it per JVM run, so two
    runs of the same program print entries in different orders.  Nothing in
    Python reproduces that, so this class stores insertion order and the
    **emitter refuses to iterate** a map whose declared type does not promise an
    order.  Everything order-independent (``get``, ``containsKey``, ``size``,
    ``equals``) is exact and is allowed.

    ``sorted_keys`` covers ``TreeMap``, whose order *is* specified.
    """

    __slots__ = ("_data", "_immutable", "_sorted", "_kind")

    def __init__(self, entries=None, immutable=False, sorted_keys=False,
                 kind="HashMap") -> None:
        self._data: dict = {}
        self._immutable = immutable
        self._sorted = sorted_keys
        self._kind = kind
        if entries:
            for key, value in entries:
                if immutable:
                    if key is None or value is None:
                        raise NullPointerExceptionJ(None)
                    if _JKey(key) in self._data:
                        raise IllegalArgumentExceptionJ(f"duplicate key: {jstr(key)}")
                self._data[_JKey(key)] = value

    # -- order-independent -------------------------------------------------

    def size(self) -> int:
        return len(self._data)

    def isEmpty(self) -> bool:
        return not self._data

    def get(self, key):
        return self._data.get(_JKey(key))

    def getOrDefault(self, key, fallback):
        found = self._data.get(_JKey(key), _MISSING)
        return fallback if found is _MISSING else found

    def containsKey(self, key) -> bool:
        return _JKey(key) in self._data

    def containsValue(self, value) -> bool:
        return any(_java_equals(v, value) for v in self._data.values())

    def equals(self, other) -> bool:
        return self == other

    def _check_mutable(self) -> None:
        if self._immutable:
            raise UnsupportedOperationExceptionJ(None)

    def put(self, key, value):
        self._check_mutable()
        wrapped = _JKey(key)
        previous = self._data.get(wrapped)
        self._data[wrapped] = value
        return previous

    def putIfAbsent(self, key, value):
        self._check_mutable()
        wrapped = _JKey(key)
        if wrapped in self._data and self._data[wrapped] is not None:
            return self._data[wrapped]
        self._data[wrapped] = value
        return None

    def remove(self, key):
        self._check_mutable()
        return self._data.pop(_JKey(key), None)

    def clear(self) -> None:
        self._check_mutable()
        self._data.clear()

    def __eq__(self, other) -> bool:
        # Java's Map.equals compares entry sets, not order.
        if not isinstance(other, JMap):
            return NotImplemented
        if len(self._data) != len(other._data):
            return False
        for key, value in self._data.items():
            if key not in other._data:
                return False
            if not _java_equals(other._data[key], value):
                return False
        return True

    def __hash__(self) -> int:
        total = 0
        for key, value in self._data.items():
            total = jint(total + (java_hash_code(key.value) ^ java_hash_code(value)))
        return total

    # -- order-dependent ---------------------------------------------------
    #
    # Reachable only when the emitter established that the declared type
    # promises an order (LinkedHashMap, TreeMap).

    def _ordered_keys(self) -> list:
        keys = list(self._data)
        if self._sorted:
            keys.sort(key=lambda k: _sort_key(k.value))
        return keys

    def keySet(self) -> "JSet":
        return JSet(
            [k.value for k in self._ordered_keys()],
            sorted_values=self._sorted,
            kind="LinkedHashSet",
        )

    def values(self) -> "JArrayList":
        return JArrayList([self._data[k] for k in self._ordered_keys()])

    def entrySet(self) -> "JArrayList":
        return JArrayList(
            [JMapEntry(k.value, self._data[k]) for k in self._ordered_keys()]
        )

    def __iter__(self):
        return iter(k.value for k in self._ordered_keys())

    def __len__(self) -> int:
        return len(self._data)

    def toString(self) -> str:
        return "{" + ", ".join(
            f"{jstr(k.value)}={jstr(self._data[k])}" for k in self._ordered_keys()
        ) + "}"


class JMapEntry:
    __slots__ = ("_key", "_value")

    def __init__(self, key, value) -> None:
        self._key = key
        self._value = value

    def getKey(self):
        return self._key

    def getValue(self):
        return self._value

    def toString(self) -> str:
        return f"{jstr(self._key)}={jstr(self._value)}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, JMapEntry):
            return NotImplemented
        return _java_equals(self._key, other._key) and _java_equals(
            self._value, other._value
        )

    def __hash__(self) -> int:
        return jint(java_hash_code(self._key) ^ java_hash_code(self._value))


class JSet:
    """A Java ``Set``.  Same order story as :class:`JMap`."""

    __slots__ = ("_data", "_immutable", "_sorted", "_kind")

    def __init__(self, values=None, immutable=False, sorted_values=False,
                 kind="HashSet") -> None:
        self._data: dict = {}
        self._immutable = immutable
        self._sorted = sorted_values
        self._kind = kind
        for value in values or ():
            if immutable:
                if value is None:
                    raise NullPointerExceptionJ(None)
                if _JKey(value) in self._data:
                    raise IllegalArgumentExceptionJ(f"duplicate element: {jstr(value)}")
            self._data[_JKey(value)] = True

    def size(self) -> int:
        return len(self._data)

    def isEmpty(self) -> bool:
        return not self._data

    def contains(self, value) -> bool:
        return _JKey(value) in self._data

    def containsAll(self, other) -> bool:
        return all(self.contains(v) for v in other)

    def equals(self, other) -> bool:
        return self == other

    def add(self, value) -> bool:
        if self._immutable:
            raise UnsupportedOperationExceptionJ(None)
        wrapped = _JKey(value)
        if wrapped in self._data:
            return False
        self._data[wrapped] = True
        return True

    def addAll(self, other) -> bool:
        changed = False
        for value in other:
            changed = self.add(value) or changed
        return changed

    def remove(self, value) -> bool:
        if self._immutable:
            raise UnsupportedOperationExceptionJ(None)
        return self._data.pop(_JKey(value), None) is not None

    def clear(self) -> None:
        if self._immutable:
            raise UnsupportedOperationExceptionJ(None)
        self._data.clear()

    def __eq__(self, other) -> bool:
        if not isinstance(other, JSet):
            return NotImplemented
        return len(self._data) == len(other._data) and all(
            k in other._data for k in self._data
        )

    def __hash__(self) -> int:
        total = 0
        for key in self._data:
            total = jint(total + java_hash_code(key.value))
        return total

    def _ordered(self) -> list:
        keys = list(self._data)
        if self._sorted:
            keys.sort(key=lambda k: _sort_key(k.value))
        return [k.value for k in keys]

    def __iter__(self):
        return iter(self._ordered())

    def __len__(self) -> int:
        return len(self._data)

    def toString(self) -> str:
        return "[" + ", ".join(jstr(v) for v in self._ordered()) + "]"


class _Missing:
    __slots__ = ()


_MISSING = _Missing()


def _sort_key(value):
    """Natural ordering for the key types a TreeMap/TreeSet can hold here."""

    if isinstance(value, JChar):
        return value.code
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return value
    compare = getattr(value, "compareTo", None)
    if callable(compare):
        import functools

        return functools.cmp_to_key(lambda a, b: a.compareTo(b))(value)
    raise ClassCastExceptionJ(f"{type(value).__name__} is not Comparable")


class JavaMap:
    """``Map`` static factories."""

    @staticmethod
    def of(*pairs) -> JMap:
        if len(pairs) % 2 != 0:
            raise IllegalArgumentExceptionJ("Map.of takes key/value pairs")
        entries = [(pairs[i], pairs[i + 1]) for i in range(0, len(pairs), 2)]
        return JMap(entries, immutable=True, kind="Map.of")

    @staticmethod
    def copyOf(source) -> JMap:
        if isinstance(source, JMap):
            entries = [(k.value, v) for k, v in source._data.items()]
        else:
            entries = list(source)
        return JMap(entries, immutable=True, kind="Map.copyOf")

    @staticmethod
    def entry(key, value) -> JMapEntry:
        if key is None or value is None:
            raise NullPointerExceptionJ(None)
        return JMapEntry(key, value)

    @staticmethod
    def ofEntries(*entries) -> JMap:
        return JMap(
            [(e.getKey(), e.getValue()) for e in entries],
            immutable=True,
            kind="Map.ofEntries",
        )


class JOptional:
    """``java.util.Optional``.

    Kept as a real object rather than collapsed to ``None``: Java distinguishes
    an empty Optional from an Optional holding null (the latter is impossible --
    ``Optional.of(null)`` throws), and ``get`` on an empty one raises
    ``NoSuchElementException`` rather than returning a falsy value.
    """

    __slots__ = ("_value", "_present")

    def __init__(self, value=None, present=False) -> None:
        self._value = value
        self._present = present

    @staticmethod
    def of(value) -> "JOptional":
        if value is None:
            raise NullPointerExceptionJ(None)
        return JOptional(value, True)

    @staticmethod
    def ofNullable(value) -> "JOptional":
        return JOptional(value, value is not None)

    @staticmethod
    def empty() -> "JOptional":
        return JOptional()

    def isPresent(self) -> bool:
        return self._present

    def isEmpty(self) -> bool:
        return not self._present

    def get(self):
        if not self._present:
            raise NoSuchElementExceptionJ("No value present")
        return self._value

    def orElse(self, fallback):
        return self._value if self._present else fallback

    def orElseGet(self, supplier):
        return self._value if self._present else supplier()

    def orElseThrow(self, supplier=None):
        if self._present:
            return self._value
        if supplier is None:
            raise NoSuchElementExceptionJ("No value present")
        raise supplier()

    def map(self, fn) -> "JOptional":
        if not self._present:
            return JOptional()
        return JOptional.ofNullable(fn(self._value))

    def filter(self, predicate) -> "JOptional":
        if self._present and predicate(self._value):
            return self
        return JOptional()

    def ifPresent(self, action) -> None:
        if self._present:
            action(self._value)

    def toString(self) -> str:
        return f"Optional[{jstr(self._value)}]" if self._present else "Optional.empty"

    def __eq__(self, other) -> bool:
        if not isinstance(other, JOptional):
            return NotImplemented
        if self._present != other._present:
            return False
        return not self._present or _java_equals(self._value, other._value)

    def __hash__(self) -> int:
        return java_hash_code(self._value) if self._present else 0


class JStream:
    """A ``java.util.stream.Stream``.

    Eager rather than lazy.  Laziness is observable in Java only through side
    effects in the intermediate operations and through short-circuiting, and the
    emitter refuses the constructs where that difference could show: `peek` is
    not supported, and the short-circuiting terminals (`anyMatch`, `findFirst`)
    are implemented with real short-circuiting below.

    Order is the same story as for maps.  A stream drawn from a `List` is
    ordered; one drawn from a `HashSet` or a `Map.of` is not, and the emitter
    refuses the terminals that would observe order on an unordered stream.
    """

    __slots__ = ("_items",)

    def __init__(self, items) -> None:
        self._items = list(items)

    # -- intermediate ------------------------------------------------------

    def map(self, fn) -> "JStream":
        return JStream([fn(v) for v in self._items])

    def mapToInt(self, fn) -> "JStream":
        return JStream([jint(num(fn(v))) for v in self._items])

    def mapToLong(self, fn) -> "JStream":
        return JStream([jlong(num(fn(v))) for v in self._items])

    def mapToObj(self, fn) -> "JStream":
        return JStream([fn(v) for v in self._items])

    def filter(self, predicate) -> "JStream":
        return JStream([v for v in self._items if predicate(v)])

    def flatMap(self, fn) -> "JStream":
        out = []
        for value in self._items:
            produced = fn(value)
            out.extend(produced._items if isinstance(produced, JStream) else produced)
        return JStream(out)

    def distinct(self) -> "JStream":
        seen: dict = {}
        for value in self._items:
            seen.setdefault(_JKey(value), value)
        return JStream(list(seen.values()))

    def sorted(self, comparator=None) -> "JStream":
        if comparator is None:
            return JStream(sorted(self._items, key=_sort_key))
        import functools

        return JStream(
            sorted(self._items, key=functools.cmp_to_key(lambda a, b: num(comparator(a, b))))
        )

    def limit(self, count: int) -> "JStream":
        return JStream(self._items[: max(0, num(count))])

    def skip(self, count: int) -> "JStream":
        return JStream(self._items[max(0, num(count)) :])

    # -- terminal ----------------------------------------------------------

    def count(self) -> int:
        return jlong(len(self._items))

    def anyMatch(self, predicate) -> bool:
        for value in self._items:
            if predicate(value):
                return True
        return False

    def allMatch(self, predicate) -> bool:
        for value in self._items:
            if not predicate(value):
                return False
        return True

    def noneMatch(self, predicate) -> bool:
        return not self.anyMatch(predicate)

    def findFirst(self) -> JOptional:
        return JOptional(self._items[0], True) if self._items else JOptional()

    def forEach(self, action) -> None:
        for value in self._items:
            action(value)

    def toList(self) -> JList:
        return JList(self._items)

    def collect(self, collector):
        return collector(self._items)

    def reduce(self, identity, accumulator):
        total = identity
        for value in self._items:
            total = accumulator(total, value)
        return total

    def sum(self) -> int:
        total = 0
        for value in self._items:
            total += num(value)
        return jint(total)

    def max(self, comparator=None) -> JOptional:
        if not self._items:
            return JOptional()
        ordered = self.sorted(comparator)._items
        return JOptional(ordered[-1], True)

    def min(self, comparator=None) -> JOptional:
        if not self._items:
            return JOptional()
        ordered = self.sorted(comparator)._items
        return JOptional(ordered[0], True)


class Collectors:
    """The collectors whose result order is defined.

    ``toSet`` and ``toMap`` are absent on purpose: they produce a ``HashSet`` /
    ``HashMap`` whose iteration order Java does not specify, and this runtime
    would have to invent one.  ``toCollection(LinkedHashSet::new)`` and
    ``joining`` are order-defined and are here.
    """

    @staticmethod
    def toList():
        return lambda items: JArrayList(items)

    @staticmethod
    def toUnmodifiableList():
        return lambda items: JList(items)

    @staticmethod
    def joining(separator="", prefix="", suffix=""):
        return lambda items: prefix + separator.join(jstr(v) for v in items) + suffix

    @staticmethod
    def counting():
        return lambda items: jlong(len(items))


def stream_of(source) -> JStream:
    """``collection.stream()``.  The emitter decides whether that is allowed."""

    if isinstance(source, JMap):
        return JStream(list(source))
    return JStream(list(source))


def map_copy(source, kind="HashMap", sorted_keys=False) -> JMap:
    """``new HashMap<>(other)`` and friends: a mutable copy of another map."""

    if isinstance(source, JMap):
        entries = [(k.value, v) for k, v in source._data.items()]
    else:
        entries = [(e.getKey(), e.getValue()) for e in source]
    return JMap(entries, kind=kind, sorted_keys=sorted_keys)


class JavaSet:
    """``Set`` static factories."""

    @staticmethod
    def of(*values) -> JSet:
        return JSet(values, immutable=True, kind="Set.of")

    @staticmethod
    def copyOf(source) -> JSet:
        return JSet(list(source), immutable=True, kind="Set.copyOf")


class JCharset:
    """A ``java.nio.charset.Charset`` with a fixed, machine-independent encoding.

    Only the constants whose byte sequences are defined by the standard are
    here; the platform default is not, because it depends on the machine the
    program runs on and so has nothing to reproduce.
    """

    __slots__ = ("_name", "codec")

    def __init__(self, name: str, codec: str) -> None:
        self._name = name
        self.codec = codec

    def name(self) -> str:
        return self._name

    def toString(self) -> str:
        return self._name


class StandardCharsets:
    UTF_8 = JCharset("UTF-8", "utf-8")
    US_ASCII = JCharset("US-ASCII", "ascii")
    ISO_8859_1 = JCharset("ISO-8859-1", "latin-1")
    UTF_16BE = JCharset("UTF-16BE", "utf-16-be")
    UTF_16LE = JCharset("UTF-16LE", "utf-16-le")


class _RegexHolder:
    """Compiled patterns, cached by their already-translated Python text."""

    cache: dict = {}


def _compiled(pattern: str):
    import re

    found = _RegexHolder.cache.get(pattern)
    if found is None:
        # re.ASCII, because Java's \d, \w, \s and \b are ASCII-only by
        # default and Python's are Unicode-aware: without it "\u0663".matches
        # ("\\d") would be false in Java and true here.
        found = re.compile(pattern, re.ASCII)
        _RegexHolder.cache[pattern] = found
    return found


class JavaList:
    """Static factories.  ``List.of`` is immutable and rejects nulls."""

    @staticmethod
    def of(*values) -> JList:
        return JList(values)

    @staticmethod
    def copyOf(source) -> JList:
        return JList(list(source))


class Objects:
    @staticmethod
    def requireNonNull(value, message: str | None = None):
        if value is None:
            raise NullPointerExceptionJ(message)
        return value

    @staticmethod
    def requireNonNullElse(value, fallback):
        return value if value is not None else Objects.requireNonNull(
            fallback, "defaultObj"
        )

    @staticmethod
    def equals(a, b) -> bool:
        return _java_equals(a, b)

    @staticmethod
    def isNull(value) -> bool:
        return value is None

    @staticmethod
    def nonNull(value) -> bool:
        return value is not None

    @staticmethod
    def toString(value, fallback: str | None = None) -> str:
        if value is None:
            return "null" if fallback is None else fallback
        return jstr(value)

    @staticmethod
    def hash(*values) -> int:
        return _java_list_hash(values)

    @staticmethod
    def hashCode(value) -> int:
        return java_hash_code(value)


class StringBuilder:
    __slots__ = ("_parts",)

    def __init__(self, initial: str | None = None) -> None:
        self._parts: list[str] = []
        if isinstance(initial, str):
            self._parts.append(initial)

    def append(self, value) -> "StringBuilder":
        self._parts.append(jstr(value))
        return self

    def toString(self) -> str:
        return "".join(self._parts)

    def length(self) -> int:
        return sum(len(p) for p in self._parts)

    def reverse(self) -> "StringBuilder":
        self._parts = [self.toString()[::-1]]
        return self


# ---------------------------------------------------------------------------
# Boxed-type statics
# ---------------------------------------------------------------------------


class Integer:
    MIN_VALUE = INT_MIN
    MAX_VALUE = INT_MAX

    @staticmethod
    def parseInt(text: str) -> int:
        try:
            stripped = text.strip() if text is not None else None
            if stripped is None or stripped == "" or stripped != text:
                raise ValueError
            value = int(text, 10)
        except (ValueError, TypeError):
            raise NumberFormatExceptionJ(f'For input string: "{text}"') from None
        if value < INT_MIN or value > INT_MAX:
            raise NumberFormatExceptionJ(f'For input string: "{text}"')
        return value

    @staticmethod
    def toString(value: int) -> str:
        return str(jint(value))

    @staticmethod
    def valueOf(value) -> int:
        return Integer.parseInt(value) if isinstance(value, str) else jint(value)

    @staticmethod
    def compare(a: int, b: int) -> int:
        return (a > b) - (a < b)

    @staticmethod
    def max(a: int, b: int) -> int:
        return a if a >= b else b

    @staticmethod
    def min(a: int, b: int) -> int:
        return a if a <= b else b

    @staticmethod
    def sum(a: int, b: int) -> int:
        return jint(a + b)

    @staticmethod
    def toHexString(value: int) -> str:
        # Java formats the *unsigned* 32-bit pattern: -1 is "ffffffff".
        return format(value & 0xFFFFFFFF, "x")

    @staticmethod
    def toBinaryString(value: int) -> str:
        return format(value & 0xFFFFFFFF, "b")

    @staticmethod
    def toOctalString(value: int) -> str:
        return format(value & 0xFFFFFFFF, "o")

    @staticmethod
    def bitCount(value: int) -> int:
        return bin(value & 0xFFFFFFFF).count("1")

    @staticmethod
    def signum(value: int) -> int:
        return (value > 0) - (value < 0)

    @staticmethod
    def hashCode(value: int) -> int:
        return jint(value)


class Long:
    MIN_VALUE = LONG_MIN
    MAX_VALUE = LONG_MAX

    @staticmethod
    def parseLong(text: str) -> int:
        try:
            value = int(text, 10)
        except (ValueError, TypeError):
            raise NumberFormatExceptionJ(f'For input string: "{text}"') from None
        if value < LONG_MIN or value > LONG_MAX:
            raise NumberFormatExceptionJ(f'For input string: "{text}"')
        return value

    @staticmethod
    def toString(value: int) -> str:
        return str(jlong(value))


class Double:
    @staticmethod
    def parseDouble(text: str) -> float:
        try:
            return float(text)
        except (ValueError, TypeError):
            raise NumberFormatExceptionJ(f'For input string: "{text}"') from None

    @staticmethod
    def toString(value: float) -> str:
        return jdouble_to_string(value)


class Math:
    PI = math.pi
    E = math.e

    @staticmethod
    def abs(value):
        """Only the unambiguous cases; integral abs goes through :func:`iabs`.

        The emitter knows the static type of the argument and calls ``iabs`` with
        it.  Guessing here from the Python value would get
        ``Math.abs(Integer.MIN_VALUE)`` wrong, which is the one case that matters.
        """

        if isinstance(value, float):
            return abs(value)
        raise IllegalStateExceptionJ(
            "integral Math.abs must be emitted as iabs(kind, value)"
        )

    @staticmethod
    def max(a, b):
        return a if a >= b else b

    @staticmethod
    def min(a, b):
        return a if a <= b else b

    @staticmethod
    def floor(value: float) -> float:
        return float(math.floor(value))

    @staticmethod
    def ceil(value: float) -> float:
        return float(math.ceil(value))

    @staticmethod
    def sqrt(value: float) -> float:
        if value < 0:
            return math.nan
        return math.sqrt(value)

    @staticmethod
    def pow(a: float, b: float) -> float:
        try:
            return float(a) ** float(b)
        except (OverflowError, ValueError):
            return math.inf

    @staticmethod
    def round(value: float) -> int:
        """``Math.round`` is ``floor(x + 0.5)``, not banker's rounding.

        Python's ``round(2.5)`` is 2 and ``round(-2.5)`` is -2; Java's are 3
        and -2.  Half of those disagree.
        """

        if math.isnan(value):
            return 0
        if value >= LONG_MAX:
            return LONG_MAX
        if value <= LONG_MIN:
            return LONG_MIN
        return int(math.floor(value + 0.5))

    @staticmethod
    def signum(value: float) -> float:
        if math.isnan(value):
            return math.nan
        if value > 0:
            return 1.0
        if value < 0:
            return -1.0
        return value  # preserves -0.0

    @staticmethod
    def floorDiv(a: int, b: int) -> int:
        if b == 0:
            raise ArithmeticExceptionJ("/ by zero")
        return a // b

    @staticmethod
    def floorMod(a: int, b: int) -> int:
        if b == 0:
            raise ArithmeticExceptionJ("/ by zero")
        return a - Math.floorDiv(a, b) * b

    @staticmethod
    def hypot(a: float, b: float) -> float:
        return math.hypot(a, b)


def _exact(kind: str, value: int, what: str) -> int:
    """Range-check an exact arithmetic result, as Math.*Exact does.

    ``Math.addExact`` exists precisely so that overflow is an exception rather
    than a wrapped value.  Emitting plain wrapping arithmetic for it would
    convert a loud failure into a silently wrong number.
    """

    low, high = (INT_MIN, INT_MAX) if kind == "int" else (LONG_MIN, LONG_MAX)
    if value < low or value > high:
        raise ArithmeticExceptionJ(f"{what} overflow")
    return value


def addExact(kind: str, a: int, b: int) -> int:
    return _exact(kind, a + b, "integer" if kind == "int" else "long")


def subtractExact(kind: str, a: int, b: int) -> int:
    return _exact(kind, a - b, "integer" if kind == "int" else "long")


def multiplyExact(kind: str, a: int, b: int) -> int:
    return _exact(kind, a * b, "integer" if kind == "int" else "long")


def negateExact(kind: str, a: int) -> int:
    return _exact(kind, -a, "integer" if kind == "int" else "long")


def toIntExact(value: int) -> int:
    return _exact("int", value, "integer")


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class _SystemOut:
    @staticmethod
    def println(*args) -> None:
        # ``println()`` prints an empty line; ``println(null)`` prints "null".
        # Collapsing the two would make a null-handling bug invisible.
        print("" if not args else jstr(args[0]))

    @staticmethod
    def print(value) -> None:
        print(jstr(value), end="")


class System:
    out = _SystemOut()
    err = _SystemOut()
