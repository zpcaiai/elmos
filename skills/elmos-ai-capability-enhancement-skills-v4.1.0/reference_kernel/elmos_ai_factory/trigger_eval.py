from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from typing import Iterable

@dataclass(frozen=True)
class TriggerObservation:
    expected: bool
    observed: bool
    task_success: bool
    control_success: bool = False

@dataclass(frozen=True)
class TriggerMetrics:
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    f1: float
    false_activation_rate: float
    task_success_lift: float
    wilson_low: float


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _wilson(successes: int, total: int, z: float = 1.96) -> float:
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z*z/total
    centre = p + z*z/(2*total)
    spread = z * sqrt((p*(1-p) + z*z/(4*total))/total)
    return max(0.0, (centre-spread)/denominator)


def evaluate_trigger(observations: Iterable[TriggerObservation]) -> TriggerMetrics:
    rows = list(observations)
    if not rows:
        raise ValueError("at least one observation is required")
    tp=sum(r.expected and r.observed for r in rows)
    fp=sum((not r.expected) and r.observed for r in rows)
    tn=sum((not r.expected) and (not r.observed) for r in rows)
    fn=sum(r.expected and (not r.observed) for r in rows)
    precision=_safe_div(tp,tp+fp); recall=_safe_div(tp,tp+fn)
    f1=_safe_div(2*precision*recall,precision+recall)
    far=_safe_div(fp,fp+tn)
    success=_safe_div(sum(r.task_success for r in rows),len(rows))
    control=_safe_div(sum(r.control_success for r in rows),len(rows))
    return TriggerMetrics(tp,fp,tn,fn,precision,recall,f1,far,success-control,_wilson(tp,tp+fn))


def trigger_gate(metrics: TriggerMetrics, *, min_precision: float=.9, min_recall: float=.85, max_false_activation: float=.05, min_lift: float=0.0) -> str:
    if metrics.precision < min_precision or metrics.recall < min_recall or metrics.false_activation_rate > max_false_activation:
        return "BLOCKED"
    if metrics.task_success_lift < min_lift or metrics.wilson_low < .5:
        return "BOUNDED"
    return "PASS"
