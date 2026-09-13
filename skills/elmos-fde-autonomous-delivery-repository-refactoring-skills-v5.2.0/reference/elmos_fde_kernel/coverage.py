from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CoverageReport:
    observed: int = 0
    verified_absent: int = 0
    unknown: int = 0
    unsupported: int = 0

    def __post_init__(self) -> None:
        if min(self.observed, self.verified_absent, self.unknown, self.unsupported) < 0:
            raise ValueError("coverage counts cannot be negative")

    @property
    def total(self) -> int:
        return self.observed + self.verified_absent + self.unknown + self.unsupported

    @property
    def resolved_ratio(self) -> float:
        return 1.0 if self.total == 0 else (self.observed + self.verified_absent) / self.total

    @property
    def honest_complete(self) -> bool:
        return self.unknown == 0 and self.unsupported == 0

    def statement(self) -> str:
        return f"observed={self.observed}; verified_absent={self.verified_absent}; unknown={self.unknown}; unsupported={self.unsupported}; resolved_ratio={self.resolved_ratio:.3f}"
