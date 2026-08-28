from __future__ import annotations
def demographic_parity_difference(a_positive,a_total,b_positive,b_total):
 if min(a_total,b_total)<=0: raise ValueError("empty group")
 return a_positive/a_total-b_positive/b_total
def four_fifths_ratio(a_positive,a_total,b_positive,b_total):
 rates=[a_positive/a_total,b_positive/b_total]
 return min(rates)/max(rates) if max(rates)>0 else 1.0
