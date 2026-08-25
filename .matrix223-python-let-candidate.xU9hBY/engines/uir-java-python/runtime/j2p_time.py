"""``java.time``, implemented on Java's own model rather than Python's datetime.

Python's ``datetime`` is the obvious place to start and the wrong one:

* it holds **microseconds**, and ``Instant`` holds **nanoseconds**, so
  ``Instant.ofEpochSecond(0, 1)`` has no representation there at all;
* its year range is 1 to 9999, while ``LocalDate`` runs to ±999999999;
* its ``timedelta`` normalises differently from ``Duration``, and prints
  nothing like ``PT2H3M4.5S``.

So the types here carry the same fields Java carries — an ``Instant`` is a
second count plus a nanosecond adjustment — and the calendar arithmetic is done
directly on the proleptic Gregorian day number.

What is deliberately *not* here: named time zones.  ``ZoneId.of("Asia/Shanghai")``
resolves through the tz database, and the JVM's bundled copy and Python's
``zoneinfo`` are separately versioned.  Two runtimes can disagree about a past
or future offset, and nothing in this file can detect that.  Fixed offsets have
no such dependency and are supported.
"""

from __future__ import annotations

from j2p_errors import RuntimeExceptionJ

NANOS_PER_SECOND = 1_000_000_000
NANOS_PER_MILLI = 1_000_000
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400

#: Java's LocalDate bounds.
MIN_YEAR = -999_999_999
MAX_YEAR = 999_999_999


class DateTimeExceptionJ(RuntimeExceptionJ):
    java_name = "java.time.DateTimeException"


class DateTimeParseExceptionJ(DateTimeExceptionJ):
    java_name = "java.time.format.DateTimeParseException"


class ArithmeticOverflow(Exception):
    """Internal marker; converted to ArithmeticException by the caller."""


# ---------------------------------------------------------------------------
# Proleptic Gregorian calendar arithmetic
# ---------------------------------------------------------------------------


def is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def length_of_month(year: int, month: int) -> int:
    if month == 2 and is_leap_year(year):
        return 29
    return _DAYS_IN_MONTH[month - 1]


def days_from_civil(year: int, month: int, day: int) -> int:
    """Days since 1970-01-01, valid for the full LocalDate range.

    Python's ``date.toordinal`` would do this but only between years 1 and
    9999; Java's LocalDate goes far outside that, so the arithmetic is done
    here instead of borrowed.
    """

    y = year - (1 if month <= 2 else 0)
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil_from_days(z: int) -> tuple[int, int, int]:
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + (3 if mp < 10 else -9)
    return (y + (1 if m <= 2 else 0), m, d)


def _check_date(year: int, month: int, day: int) -> None:
    if year < MIN_YEAR or year > MAX_YEAR:
        raise DateTimeExceptionJ(
            f"Invalid value for Year (valid values {MIN_YEAR} - {MAX_YEAR}): {year}"
        )
    if month < 1 or month > 12:
        raise DateTimeExceptionJ(
            f"Invalid value for MonthOfYear (valid values 1 - 12): {month}"
        )
    if day < 1 or day > 31:
        raise DateTimeExceptionJ(
            f"Invalid value for DayOfMonth (valid values 1 - 28/31): {day}"
        )
    if day > length_of_month(year, month):
        if day == 29 and month == 2:
            raise DateTimeExceptionJ(
                f"Invalid date 'February 29' as '{year}' is not a leap year"
            )
        raise DateTimeExceptionJ(
            f"Invalid date '{_MONTH_NAMES[month - 1]} {day}'"
        )


_MONTH_NAMES = (
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
)


def _pad(value: int, width: int) -> str:
    sign = "-" if value < 0 else ""
    return sign + str(abs(value)).rjust(width, "0")


def _format_year(year: int) -> str:
    """Java pads to 4 digits and prefixes a `+` beyond that."""

    if 0 <= year <= 9999:
        return str(year).rjust(4, "0")
    if year > 9999:
        return "+" + str(year)
    return "-" + str(abs(year)).rjust(4, "0")


# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------


class Duration:
    """A ``(seconds, nanos)`` pair, normalised so ``0 <= nanos < 1e9``."""

    __slots__ = ("seconds", "nanos")

    def __init__(self, seconds: int, nanos: int = 0) -> None:
        seconds += nanos // NANOS_PER_SECOND
        nanos %= NANOS_PER_SECOND
        self.seconds = seconds
        self.nanos = nanos

    # -- factories --------------------------------------------------------

    @staticmethod
    def ZERO() -> "Duration":
        return Duration(0, 0)

    @staticmethod
    def ofSeconds(seconds: int, nano_adjustment: int = 0) -> "Duration":
        return Duration(seconds, nano_adjustment)

    @staticmethod
    def ofMillis(millis: int) -> "Duration":
        return Duration(0, millis * NANOS_PER_MILLI)

    @staticmethod
    def ofNanos(nanos: int) -> "Duration":
        return Duration(0, nanos)

    @staticmethod
    def ofMinutes(minutes: int) -> "Duration":
        return Duration(minutes * SECONDS_PER_MINUTE, 0)

    @staticmethod
    def ofHours(hours: int) -> "Duration":
        return Duration(hours * SECONDS_PER_HOUR, 0)

    @staticmethod
    def ofDays(days: int) -> "Duration":
        return Duration(days * SECONDS_PER_DAY, 0)

    @staticmethod
    def between(start, end) -> "Duration":
        return Duration(
            end.epoch_second() - start.epoch_second(), end.nano() - start.nano()
        )

    # -- accessors --------------------------------------------------------

    def getSeconds(self) -> int:
        return self.seconds

    def getNano(self) -> int:
        return self.nanos

    def toMillis(self) -> int:
        return self.seconds * 1000 + self.nanos // NANOS_PER_MILLI

    def toNanos(self) -> int:
        return self.seconds * NANOS_PER_SECOND + self.nanos

    def toSeconds(self) -> int:
        return self.seconds

    def toMinutes(self) -> int:
        return _truncate_div(self.seconds, SECONDS_PER_MINUTE)

    def toHours(self) -> int:
        return _truncate_div(self.seconds, SECONDS_PER_HOUR)

    def toDays(self) -> int:
        return _truncate_div(self.seconds, SECONDS_PER_DAY)

    def isZero(self) -> bool:
        return self.seconds == 0 and self.nanos == 0

    def isNegative(self) -> bool:
        return self.seconds < 0

    # -- arithmetic -------------------------------------------------------

    def plus(self, other: "Duration") -> "Duration":
        return Duration(self.seconds + other.seconds, self.nanos + other.nanos)

    def minus(self, other: "Duration") -> "Duration":
        return Duration(self.seconds - other.seconds, self.nanos - other.nanos)

    def plusSeconds(self, seconds: int) -> "Duration":
        return Duration(self.seconds + seconds, self.nanos)

    def plusMillis(self, millis: int) -> "Duration":
        return Duration(self.seconds, self.nanos + millis * NANOS_PER_MILLI)

    def multipliedBy(self, factor: int) -> "Duration":
        return Duration(0, self.toNanos() * factor)

    def negated(self) -> "Duration":
        return Duration(0, -self.toNanos())

    def abs(self) -> "Duration":
        return self.negated() if self.isNegative() else self

    def compareTo(self, other: "Duration") -> int:
        mine, theirs = (self.seconds, self.nanos), (other.seconds, other.nanos)
        return (mine > theirs) - (mine < theirs)

    # -- protocol ---------------------------------------------------------

    def __eq__(self, other) -> bool:
        if isinstance(other, Duration):
            return self.seconds == other.seconds and self.nanos == other.nanos
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.seconds, self.nanos))

    def toString(self) -> str:
        """ISO-8601, spelled the way ``Duration.toString`` spells it.

        Zero is ``PT0S``.  Negative durations print a minus on the *component*,
        so ``Duration.ofSeconds(-1)`` is ``PT-1S`` rather than ``-PT1S``, and a
        negative sub-second part borrows from the seconds field.
        """

        # No special case for zero: the general path below already produces
        # "PT0S" for it.  An early return here could never fail, so it could
        # never be tested, and an untestable rule is indistinguishable from no
        # rule at all.
        hours = _truncate_div(self.seconds, SECONDS_PER_HOUR)
        minutes = _truncate_div(self.seconds % SECONDS_PER_HOUR
                                if self.seconds >= 0
                                else -((-self.seconds) % SECONDS_PER_HOUR),
                                SECONDS_PER_MINUTE)
        secs = self.seconds % SECONDS_PER_MINUTE if self.seconds >= 0 else -(
            (-self.seconds) % SECONDS_PER_MINUTE
        )

        out = "PT"
        if hours != 0:
            out += f"{hours}H"
        if minutes != 0:
            out += f"{minutes}M"
        if secs == 0 and self.nanos == 0 and (hours != 0 or minutes != 0):
            return out
        if secs == 0 and self.nanos > 0 and self.seconds < 0:
            out += "-0"
        else:
            out += str(secs)
        if self.nanos > 0:
            out += ("." + str(self.nanos).rjust(9, "0")).rstrip("0")
        return out + "S"


def _truncate_div(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


# ---------------------------------------------------------------------------
# Instant
# ---------------------------------------------------------------------------


class Instant:
    __slots__ = ("seconds", "nanos")

    def __init__(self, seconds: int, nanos: int = 0) -> None:
        seconds += nanos // NANOS_PER_SECOND
        nanos %= NANOS_PER_SECOND
        self.seconds = seconds
        self.nanos = nanos

    @staticmethod
    def EPOCH() -> "Instant":
        return Instant(0, 0)

    @staticmethod
    def ofEpochSecond(second: int, nano_adjustment: int = 0) -> "Instant":
        return Instant(second, nano_adjustment)

    @staticmethod
    def ofEpochMilli(milli: int) -> "Instant":
        return Instant(0, milli * NANOS_PER_MILLI)

    @staticmethod
    def now(clock=None) -> "Instant":
        """The wall clock.

        Translatable, but a program that calls it cannot be *differentially*
        verified: two runs observe different values by design.  Pass a fixed
        Clock to get a comparable program.
        """

        if clock is not None:
            return clock.instant()
        import time as _time

        nanos = _time.time_ns()
        return Instant(nanos // NANOS_PER_SECOND, nanos % NANOS_PER_SECOND)

    @staticmethod
    def parse(text: str) -> "Instant":
        return _parse_instant(text)

    # -- accessors --------------------------------------------------------

    def getEpochSecond(self) -> int:
        return self.seconds

    def getNano(self) -> int:
        return self.nanos

    def toEpochMilli(self) -> int:
        return self.seconds * 1000 + self.nanos // NANOS_PER_MILLI

    def epoch_second(self) -> int:
        return self.seconds

    def nano(self) -> int:
        return self.nanos

    # -- arithmetic -------------------------------------------------------

    def plusSeconds(self, seconds: int) -> "Instant":
        return Instant(self.seconds + seconds, self.nanos)

    def minusSeconds(self, seconds: int) -> "Instant":
        return Instant(self.seconds - seconds, self.nanos)

    def plusMillis(self, millis: int) -> "Instant":
        return Instant(self.seconds, self.nanos + millis * NANOS_PER_MILLI)

    def plusNanos(self, nanos: int) -> "Instant":
        return Instant(self.seconds, self.nanos + nanos)

    def plus(self, duration: Duration) -> "Instant":
        return Instant(self.seconds + duration.seconds, self.nanos + duration.nanos)

    def minus(self, duration: Duration) -> "Instant":
        return Instant(self.seconds - duration.seconds, self.nanos - duration.nanos)

    def isBefore(self, other: "Instant") -> bool:
        return (self.seconds, self.nanos) < (other.seconds, other.nanos)

    def isAfter(self, other: "Instant") -> bool:
        return (self.seconds, self.nanos) > (other.seconds, other.nanos)

    def compareTo(self, other: "Instant") -> int:
        mine, theirs = (self.seconds, self.nanos), (other.seconds, other.nanos)
        return (mine > theirs) - (mine < theirs)

    def __eq__(self, other) -> bool:
        if isinstance(other, Instant):
            return self.seconds == other.seconds and self.nanos == other.nanos
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.seconds, self.nanos))

    def toString(self) -> str:
        day = _floor_div(self.seconds, SECONDS_PER_DAY)
        sod = self.seconds - day * SECONDS_PER_DAY
        year, month, dom = civil_from_days(day)
        hour, minute, second = sod // 3600, (sod // 60) % 60, sod % 60
        text = (
            f"{_format_year(year)}-{_pad(month, 2)}-{_pad(dom, 2)}"
            f"T{_pad(hour, 2)}:{_pad(minute, 2)}"
        )
        # ISO_INSTANT always prints seconds, and prints the fraction in groups
        # of three digits -- never one or two.
        text += f":{_pad(second, 2)}"
        if self.nanos != 0:
            text += "." + _fraction(self.nanos)
        return text + "Z"


def _fraction(nanos: int) -> str:
    if nanos % 1_000_000 == 0:
        return str(nanos // 1_000_000).rjust(3, "0")
    if nanos % 1000 == 0:
        return str(nanos // 1000).rjust(6, "0")
    return str(nanos).rjust(9, "0")


def _floor_div(a: int, b: int) -> int:
    return a // b


def _parse_instant(text: str) -> Instant:
    if not isinstance(text, str) or not text.endswith("Z"):
        raise DateTimeParseExceptionJ(f"Text '{text}' could not be parsed at index 0")
    body = text[:-1]
    try:
        date_part, time_part = body.split("T")
        year_text, month_text, day_text = date_part.split("-", 2) if not date_part.startswith("-") else (
            "-" + date_part[1:].split("-")[0], date_part[1:].split("-")[1], date_part[1:].split("-")[2]
        )
        pieces = time_part.split(":")
        hour, minute = int(pieces[0]), int(pieces[1])
        second, nanos = 0, 0
        if len(pieces) > 2:
            if "." in pieces[2]:
                sec_text, frac = pieces[2].split(".")
                second = int(sec_text)
                nanos = int(frac.ljust(9, "0")[:9])
            else:
                second = int(pieces[2])
        year, month, day = int(year_text), int(month_text), int(day_text)
    except (ValueError, IndexError):
        raise DateTimeParseExceptionJ(
            f"Text '{text}' could not be parsed at index 0"
        ) from None
    _check_date(year, month, day)
    epoch = days_from_civil(year, month, day) * SECONDS_PER_DAY
    return Instant(epoch + hour * 3600 + minute * 60 + second, nanos)


# ---------------------------------------------------------------------------
# LocalDate / LocalTime / LocalDateTime
# ---------------------------------------------------------------------------


class LocalDate:
    __slots__ = ("year", "month", "day")

    def __init__(self, year: int, month: int, day: int) -> None:
        _check_date(year, month, day)
        self.year, self.month, self.day = year, month, day

    @staticmethod
    def of(year: int, month: int, day: int) -> "LocalDate":
        return LocalDate(year, month, day)

    @staticmethod
    def ofEpochDay(day: int) -> "LocalDate":
        y, m, d = civil_from_days(day)
        return LocalDate(y, m, d)

    @staticmethod
    def parse(text: str) -> "LocalDate":
        try:
            negative = text.startswith("-")
            body = text[1:] if negative else text
            year_text, month_text, day_text = body.split("-")
            year = int(year_text) * (-1 if negative else 1)
            return LocalDate(year, int(month_text), int(day_text))
        except (ValueError, IndexError):
            raise DateTimeParseExceptionJ(
                f"Text '{text}' could not be parsed at index 0"
            ) from None

    def getYear(self) -> int:
        return self.year

    def getMonthValue(self) -> int:
        return self.month

    def getDayOfMonth(self) -> int:
        return self.day

    def toEpochDay(self) -> int:
        return days_from_civil(self.year, self.month, self.day)

    def isLeapYear(self) -> bool:
        return is_leap_year(self.year)

    def lengthOfMonth(self) -> int:
        return length_of_month(self.year, self.month)

    def plusDays(self, days: int) -> "LocalDate":
        return LocalDate.ofEpochDay(self.toEpochDay() + days)

    def minusDays(self, days: int) -> "LocalDate":
        return LocalDate.ofEpochDay(self.toEpochDay() - days)

    def plusMonths(self, months: int) -> "LocalDate":
        """Month arithmetic *clamps* the day.

        January 31 plus one month is February 28 (or 29), not March 3.  Adding
        a timedelta of 30 days, which is what a naive translation reaches for,
        gets this wrong for most month lengths.
        """

        total = self.year * 12 + (self.month - 1) + months
        year, month = total // 12, total % 12 + 1
        return LocalDate(year, month, min(self.day, length_of_month(year, month)))

    def minusMonths(self, months: int) -> "LocalDate":
        return self.plusMonths(-months)

    def plusYears(self, years: int) -> "LocalDate":
        year = self.year + years
        return LocalDate(year, self.month, min(self.day, length_of_month(year, self.month)))

    def isBefore(self, other: "LocalDate") -> bool:
        return self._key() < other._key()

    def isAfter(self, other: "LocalDate") -> bool:
        return self._key() > other._key()

    def compareTo(self, other: "LocalDate") -> int:
        return (self._key() > other._key()) - (self._key() < other._key())

    def atStartOfDay(self) -> "LocalDateTime":
        return LocalDateTime(self, LocalTime(0, 0, 0, 0))

    def _key(self) -> tuple:
        return (self.year, self.month, self.day)

    def __eq__(self, other) -> bool:
        if isinstance(other, LocalDate):
            return self._key() == other._key()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._key())

    def toString(self) -> str:
        return f"{_format_year(self.year)}-{_pad(self.month, 2)}-{_pad(self.day, 2)}"


class LocalTime:
    __slots__ = ("hour", "minute", "second", "nano")

    def __init__(self, hour: int, minute: int, second: int = 0, nano: int = 0) -> None:
        if not 0 <= hour <= 23:
            raise DateTimeExceptionJ(
                f"Invalid value for HourOfDay (valid values 0 - 23): {hour}"
            )
        if not 0 <= minute <= 59:
            raise DateTimeExceptionJ(
                f"Invalid value for MinuteOfHour (valid values 0 - 59): {minute}"
            )
        if not 0 <= second <= 59:
            raise DateTimeExceptionJ(
                f"Invalid value for SecondOfMinute (valid values 0 - 59): {second}"
            )
        self.hour, self.minute, self.second, self.nano = hour, minute, second, nano

    @staticmethod
    def of(hour: int, minute: int, second: int = 0, nano: int = 0) -> "LocalTime":
        return LocalTime(hour, minute, second, nano)

    def getHour(self) -> int:
        return self.hour

    def getMinute(self) -> int:
        return self.minute

    def getSecond(self) -> int:
        return self.second

    def toSecondOfDay(self) -> int:
        return self.hour * 3600 + self.minute * 60 + self.second

    def _key(self) -> tuple:
        return (self.hour, self.minute, self.second, self.nano)

    def __eq__(self, other) -> bool:
        if isinstance(other, LocalTime):
            return self._key() == other._key()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._key())

    def toString(self) -> str:
        """Seconds are omitted when zero -- unlike ``Instant.toString``."""

        text = f"{_pad(self.hour, 2)}:{_pad(self.minute, 2)}"
        if self.second != 0 or self.nano != 0:
            text += f":{_pad(self.second, 2)}"
            if self.nano != 0:
                text += "." + _fraction(self.nano)
        return text


class LocalDateTime:
    __slots__ = ("date", "time")

    def __init__(self, date: LocalDate, time: LocalTime) -> None:
        self.date, self.time = date, time

    @staticmethod
    def of(year, month, day, hour, minute, second=0, nano=0) -> "LocalDateTime":
        return LocalDateTime(
            LocalDate(year, month, day), LocalTime(hour, minute, second, nano)
        )

    @staticmethod
    def ofEpochSecond(seconds: int, nano: int, offset) -> "LocalDateTime":
        total = seconds + offset.total_seconds
        day = _floor_div(total, SECONDS_PER_DAY)
        sod = total - day * SECONDS_PER_DAY
        return LocalDateTime(
            LocalDate.ofEpochDay(day),
            LocalTime(sod // 3600, (sod // 60) % 60, sod % 60, nano),
        )

    def toLocalDate(self) -> LocalDate:
        return self.date

    def toLocalTime(self) -> LocalTime:
        return self.time

    def getYear(self) -> int:
        return self.date.year

    def getHour(self) -> int:
        return self.time.hour

    def toEpochSecond(self, offset) -> int:
        return (
            self.date.toEpochDay() * SECONDS_PER_DAY
            + self.time.toSecondOfDay()
            - offset.total_seconds
        )

    def toInstant(self, offset) -> Instant:
        return Instant(self.toEpochSecond(offset), self.time.nano)

    def plusDays(self, days: int) -> "LocalDateTime":
        return LocalDateTime(self.date.plusDays(days), self.time)

    def isBefore(self, other: "LocalDateTime") -> bool:
        return self._key() < other._key()

    def isAfter(self, other: "LocalDateTime") -> bool:
        return self._key() > other._key()

    def _key(self) -> tuple:
        return (self.date._key(), self.time._key())

    def __eq__(self, other) -> bool:
        if isinstance(other, LocalDateTime):
            return self._key() == other._key()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._key())

    def toString(self) -> str:
        return self.date.toString() + "T" + self.time.toString()


# ---------------------------------------------------------------------------
# ZoneOffset
# ---------------------------------------------------------------------------


class ZoneOffset:
    """A *fixed* offset.  Named zones are refused by the emitter."""

    __slots__ = ("total_seconds",)

    def __init__(self, total_seconds: int) -> None:
        if abs(total_seconds) > 18 * SECONDS_PER_HOUR:
            raise DateTimeExceptionJ(
                "Zone offset not in valid range: -18:00 to +18:00"
            )
        self.total_seconds = total_seconds

    @staticmethod
    def UTC() -> "ZoneOffset":
        return ZoneOffset(0)

    @staticmethod
    def ofHours(hours: int) -> "ZoneOffset":
        return ZoneOffset(hours * SECONDS_PER_HOUR)

    @staticmethod
    def ofHoursMinutes(hours: int, minutes: int) -> "ZoneOffset":
        return ZoneOffset(hours * SECONDS_PER_HOUR + minutes * SECONDS_PER_MINUTE)

    def getTotalSeconds(self) -> int:
        return self.total_seconds

    def __eq__(self, other) -> bool:
        if isinstance(other, ZoneOffset):
            return self.total_seconds == other.total_seconds
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.total_seconds)

    def toString(self) -> str:
        if self.total_seconds == 0:
            return "Z"
        sign = "+" if self.total_seconds > 0 else "-"
        total = abs(self.total_seconds)
        hours, minutes, seconds = total // 3600, (total // 60) % 60, total % 60
        text = f"{sign}{_pad(hours, 2)}:{_pad(minutes, 2)}"
        if seconds:
            text += f":{_pad(seconds, 2)}"
        return text


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


class Clock:
    __slots__ = ("_fixed", "_offset")

    def __init__(self, fixed: Instant | None = None, offset: ZoneOffset | None = None) -> None:
        self._fixed = fixed
        self._offset = offset or ZoneOffset.UTC()

    @staticmethod
    def fixed(instant: Instant, zone: ZoneOffset) -> "Clock":
        return Clock(instant, zone)

    @staticmethod
    def systemUTC() -> "Clock":
        return Clock(None, ZoneOffset.UTC())

    def instant(self) -> Instant:
        if self._fixed is not None:
            return self._fixed
        return Instant.now()

    def millis(self) -> int:
        return self.instant().toEpochMilli()


# ---------------------------------------------------------------------------
# ChronoUnit
# ---------------------------------------------------------------------------


class _ChronoUnit:
    __slots__ = ("name", "seconds")

    def __init__(self, name: str, seconds: int | None) -> None:
        self.name, self.seconds = name, seconds

    def between(self, start, end) -> int:
        """Whole units between two points, truncated toward zero."""

        if isinstance(start, LocalDate) and isinstance(end, LocalDate):
            days = end.toEpochDay() - start.toEpochDay()
            if self.name == "DAYS":
                return days
            if self.name == "WEEKS":
                return _truncate_div(days, 7)
            if self.name in ("MONTHS", "YEARS"):
                months = (end.year - start.year) * 12 + (end.month - start.month)
                if months > 0 and end.day < start.day:
                    months -= 1
                elif months < 0 and end.day > start.day:
                    months += 1
                return months if self.name == "MONTHS" else _truncate_div(months, 12)
            raise DateTimeExceptionJ(f"Unsupported unit: {self.name}")
        if self.seconds is None:
            raise DateTimeExceptionJ(f"Unsupported unit: {self.name}")
        if self.name == "NANOS":
            return (end.epoch_second() - start.epoch_second()) * NANOS_PER_SECOND + (
                end.nano() - start.nano()
            )
        delta_nanos = (
            end.epoch_second() - start.epoch_second()
        ) * NANOS_PER_SECOND + (end.nano() - start.nano())
        return _truncate_div(delta_nanos, self.seconds * NANOS_PER_SECOND)

    def toString(self) -> str:
        return self.name.capitalize()


class ChronoUnit:
    NANOS = _ChronoUnit("NANOS", None)
    MILLIS = _ChronoUnit("MILLIS", None)
    SECONDS = _ChronoUnit("SECONDS", 1)
    MINUTES = _ChronoUnit("MINUTES", SECONDS_PER_MINUTE)
    HOURS = _ChronoUnit("HOURS", SECONDS_PER_HOUR)
    DAYS = _ChronoUnit("DAYS", SECONDS_PER_DAY)
    WEEKS = _ChronoUnit("WEEKS", SECONDS_PER_DAY * 7)
    MONTHS = _ChronoUnit("MONTHS", None)
    YEARS = _ChronoUnit("YEARS", None)


ChronoUnit.MILLIS = _ChronoUnit("MILLIS", None)


# ---------------------------------------------------------------------------
# DateTimeFormatter
# ---------------------------------------------------------------------------

#: Pattern letters this formatter reproduces.  Everything else -- notably the
#: text forms `EEE`, `MMM` and `a` -- depends on the JVM's default Locale, which
#: is not a property of the program, so those are refused rather than guessed.
SUPPORTED_PATTERN_LETTERS = frozenset("yMdHmsSn")


class DateTimeFormatter:
    __slots__ = ("pattern",)

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern

    @staticmethod
    def ofPattern(pattern: str) -> "DateTimeFormatter":
        return DateTimeFormatter(pattern)

    def format(self, value) -> str:
        out: list[str] = []
        index = 0
        pattern = self.pattern
        while index < len(pattern):
            ch = pattern[index]
            if ch.isalpha():
                run = 1
                while index + run < len(pattern) and pattern[index + run] == ch:
                    run += 1
                out.append(self._field(ch, run, value))
                index += run
            elif ch == "'":
                end = pattern.index("'", index + 1)
                out.append(pattern[index + 1 : end])
                index = end + 1
            else:
                out.append(ch)
                index += 1
        return "".join(out)

    @staticmethod
    def _field(letter: str, width: int, value) -> str:
        date = value.date if isinstance(value, LocalDateTime) else value
        time = value.time if isinstance(value, LocalDateTime) else value
        if letter == "y":
            year = date.year
            return str(year).rjust(width, "0")[-width:] if width == 2 else str(year).rjust(width, "0")
        if letter == "M":
            return str(date.month).rjust(width, "0")
        if letter == "d":
            return str(date.day).rjust(width, "0")
        if letter == "H":
            return str(time.hour).rjust(width, "0")
        if letter == "m":
            return str(time.minute).rjust(width, "0")
        if letter == "s":
            return str(time.second).rjust(width, "0")
        if letter in ("S", "n"):
            return str(time.nano).rjust(9, "0")[:width]
        raise DateTimeExceptionJ(f"Unsupported pattern letter: {letter}")
