from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from typing import Sequence

@dataclass(frozen=True)
class Calibration:
    n: int
    accuracy: float
    false_pass_rate: float
    false_fail_rate: float
    agreement: float
    lower_accuracy_bound: float


def calibrate(human: Sequence[bool], judge: Sequence[bool]) -> Calibration:
    if len(human)!=len(judge) or not human:
        raise ValueError("equal non-empty labels are required")
    n=len(human); correct=sum(a==b for a,b in zip(human,judge))
    false_pass=sum((not h) and j for h,j in zip(human,judge))
    false_fail=sum(h and (not j) for h,j in zip(human,judge))
    p=correct/n; z=1.96
    denominator=1+z*z/n; centre=p+z*z/(2*n); spread=z*sqrt((p*(1-p)+z*z/(4*n))/n)
    low=max(0.0,(centre-spread)/denominator)
    human_pos=sum(human); judge_pos=sum(judge)
    expected=(human_pos/n)*(judge_pos/n)+((n-human_pos)/n)*((n-judge_pos)/n)
    kappa=(p-expected)/(1-expected) if expected < 1 else 1.0
    return Calibration(n,p,false_pass/max(1,n-human_pos),false_fail/max(1,human_pos),kappa,low)


def judge_use_decision(calibration: Calibration, *, self_judge: bool, authoritative: bool, min_accuracy: float=.9, max_false_pass: float=.05) -> str:
    if self_judge and authoritative:
        return "BLOCKED"
    if calibration.accuracy < min_accuracy or calibration.false_pass_rate > max_false_pass:
        return "BLOCKED" if authoritative else "BOUNDED"
    if calibration.lower_accuracy_bound < .75 or calibration.n < 30:
        return "BOUNDED"
    return "PASS_NON_AUTHORITATIVE" if not authoritative else "PASS_WITH_INDEPENDENT_ORACLE"
