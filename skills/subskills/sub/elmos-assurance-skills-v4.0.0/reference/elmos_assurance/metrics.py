"""Calibration arithmetic; these calculations do not establish sampling validity."""
import math


def zero_event_upper_bound(n: int, confidence: float = 0.95) -> float:
    """One-sided exact binomial upper bound after 0/n events, fixed n IID trials."""
    if type(n) is not int or n <= 0 or not 0 < confidence < 1:
        raise ValueError("INVALID_SAMPLE_OR_CONFIDENCE")
    return -math.expm1(math.log1p(-confidence) / n)


def mutation_summary(killed: int, survived: int, unknown: int,
                     excluded_reviewed: int = 0) -> dict:
    values = [killed, survived, unknown, excluded_reviewed]
    if any(type(v) is not int or v < 0 for v in values):
        raise ValueError("INVALID_MUTATION_COUNTS")
    total = killed + survived + unknown
    return {"killed": killed, "survived": survived, "unknown": unknown,
            "excluded_reviewed": excluded_reviewed, "effective_denominator": total,
            "conservative_ratio": killed / total if total else None,
            "complete": total > 0 and unknown == 0}
