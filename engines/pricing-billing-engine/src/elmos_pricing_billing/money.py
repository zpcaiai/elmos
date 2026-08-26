from __future__ import annotations

from dataclasses import dataclass

from .errors import require

MAX_I64 = (1 << 63) - 1
MIN_I64 = -(1 << 63)
MICRO_PER_MAJOR = 1_000_000
MINOR_PER_MAJOR = 100
MICRO_PER_MINOR = MICRO_PER_MAJOR // MINOR_PER_MAJOR
QUANTITY_SCALE = 1_000_000


def checked_i64(value: int, *, field: str) -> int:
    require(type(value) is int, "INTEGER_REQUIRED", f"{field} must be an integer", field=field)
    require(MIN_I64 <= value <= MAX_I64, "INTEGER_OVERFLOW", f"{field} exceeds signed 64-bit range", field=field)
    return value


def checked_add(*values: int, field: str) -> int:
    for value in values:
        checked_i64(value, field=field)
    return checked_i64(sum(values), field=field)


def checked_mul(left: int, right: int, *, field: str) -> int:
    checked_i64(left, field=field)
    checked_i64(right, field=field)
    return checked_i64(left * right, field=field)


def require_positive(value: int, *, field: str) -> int:
    checked_i64(value, field=field)
    require(value > 0, "POSITIVE_VALUE_REQUIRED", f"{field} must be positive", field=field)
    return value


def require_non_negative(value: int, *, field: str) -> int:
    checked_i64(value, field=field)
    require(value >= 0, "NEGATIVE_VALUE", f"{field} cannot be negative", field=field)
    return value


def normalize_currency(currency: str) -> str:
    normalized = currency.strip().upper()
    require(
        len(normalized) == 3 and normalized.isascii() and normalized.isalpha(),
        "INVALID_CURRENCY",
        "currency must be a three-letter ASCII code",
        currency=currency,
    )
    return normalized


def round_half_up_div(numerator: int, denominator: int) -> int:
    checked_i64(denominator, field="denominator")
    require(denominator > 0, "INVALID_DENOMINATOR", "denominator must be positive")
    checked_i64(numerator, field="numerator")
    if numerator >= 0:
        result = (numerator + denominator // 2) // denominator
    else:
        result = -((-numerator + denominator // 2) // denominator)
    return checked_i64(result, field="rounded_result")


def micro_to_minor(amount_micro: int) -> int:
    return round_half_up_div(amount_micro, MICRO_PER_MINOR)


@dataclass(frozen=True, slots=True)
class Money:
    currency: str
    minor: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        checked_i64(self.minor, field="minor")

    def non_negative(self) -> Money:
        require_non_negative(self.minor, field="minor")
        return self
