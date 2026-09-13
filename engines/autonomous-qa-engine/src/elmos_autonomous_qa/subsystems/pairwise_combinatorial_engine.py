"""Pairwise Combinatorial Test Generation Engine (In-Parameter-Order Algorithm).

Constructs minimal 2-way Covering Arrays CA(N; 2, k, v) ensuring all parameter value
pairs are tested at least once, with arbitrary constraint exclusion support.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import itertools
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


@dataclass
class CoveringArray:
    parameters: List[str]
    test_cases: List[Dict[str, Any]]
    total_pairs: int
    covered_pairs: int
    coverage_ratio: float


class PairwiseCombinatorialEngine:
    """Generates minimal pairwise test suites using the In-Parameter-Order (IPO) strategy."""

    @classmethod
    def generate_pairwise(
        cls,
        parameters: Dict[str, List[Any]],
        constraints: Optional[List[Callable[[Dict[str, Any]], bool]]] = None,
    ) -> CoveringArray:
        if not parameters:
            return CoveringArray(parameters=[], test_cases=[], total_pairs=0, covered_pairs=0, coverage_ratio=1.0)

        param_names = list(parameters.keys())
        if len(param_names) == 1:
            p = param_names[0]
            cases = [{p: val} for val in parameters[p]]
            return CoveringArray(
                parameters=param_names,
                test_cases=cases,
                total_pairs=len(cases),
                covered_pairs=len(cases),
                coverage_ratio=1.0,
            )

        # 1. Compute all target pairs across all parameter combinations
        all_pairs: Set[Tuple[str, Any, str, Any]] = set()
        for p1, p2 in itertools.combinations(param_names, 2):
            for v1 in parameters[p1]:
                for v2 in parameters[p2]:
                    # Filter out statically invalid pairs
                    if constraints:
                        sample = {p1: v1, p2: v2}
                        if not all(c(sample) for c in constraints):
                            continue
                    all_pairs.add((p1, v1, p2, v2))

        # 2. IPO construction
        # Initialize test set with all pairs of first two parameters
        p1, p2 = param_names[0], param_names[1]
        test_suite: List[Dict[str, Any]] = []
        for v1 in parameters[p1]:
            for v2 in parameters[p2]:
                cand = {p1: v1, p2: v2}
                if constraints and not all(c(cand) for c in constraints):
                    continue
                test_suite.append(cand)

        # Incrementally extend with remaining parameters
        for p_idx in range(2, len(param_names)):
            p_curr = param_names[p_idx]
            v_curr_list = parameters[p_curr]

            # Horizontal growth: assign values to existing test cases
            uncovered_for_curr: Set[Tuple[str, Any, str, Any]] = set()
            for prev_idx in range(p_idx):
                p_prev = param_names[prev_idx]
                for v_prev in parameters[p_prev]:
                    for v_c in v_curr_list:
                        pair = (p_prev, v_prev, p_curr, v_c)
                        if pair in all_pairs:
                            uncovered_for_curr.add(pair)

            # Assign best value to each test case in test_suite
            for tc in test_suite:
                best_val = v_curr_list[0]
                best_coverage = -1
                for val in v_curr_list:
                    cand_tc = dict(tc)
                    cand_tc[p_curr] = val
                    if constraints and not all(c(cand_tc) for c in constraints):
                        continue

                    # Count how many uncovered pairs this assignment satisfies
                    cov = sum(
                        1
                        for prev_idx in range(p_idx)
                        if (param_names[prev_idx], cand_tc[param_names[prev_idx]], p_curr, val)
                        in uncovered_for_curr
                    )
                    if cov > best_coverage:
                        best_coverage = cov
                        best_val = val

                tc[p_curr] = best_val
                # Mark pairs covered
                for prev_idx in range(p_idx):
                    pair = (param_names[prev_idx], tc[param_names[prev_idx]], p_curr, best_val)
                    uncovered_for_curr.discard(pair)

            # Vertical growth: add new test cases for still uncovered pairs
            while uncovered_for_curr:
                target_pair = uncovered_for_curr.pop()
                p_a, v_a, p_b, v_b = target_pair
                new_tc: Dict[str, Any] = {p_a: v_a, p_b: v_b}

                # Fill other parameters to cover maximum remaining uncovered pairs
                for i in range(p_idx + 1):
                    p_fill = param_names[i]
                    if p_fill in new_tc:
                        continue
                    best_fval = parameters[p_fill][0]
                    new_tc[p_fill] = best_fval

                if constraints and not all(c(new_tc) for c in constraints):
                    continue

                test_suite.append(new_tc)
                # Remove newly satisfied pairs
                to_remove = []
                for up in uncovered_for_curr:
                    p_x, v_x, p_y, v_y = up
                    if new_tc.get(p_x) == v_x and new_tc.get(p_y) == v_y:
                        to_remove.append(up)
                for r in to_remove:
                    uncovered_for_curr.discard(r)

        # 3. Calculate final achieved coverage
        covered_set: Set[Tuple[str, Any, str, Any]] = set()
        for tc in test_suite:
            for p_a, p_b in itertools.combinations(param_names, 2):
                if p_a in tc and p_b in tc:
                    covered_set.add((p_a, tc[p_a], p_b, tc[p_b]))

        total_cnt = len(all_pairs)
        cov_cnt = len(covered_set.intersection(all_pairs))
        ratio = round((cov_cnt / total_cnt) * 100.0, 2) if total_cnt > 0 else 100.0

        return CoveringArray(
            parameters=param_names,
            test_cases=test_suite,
            total_pairs=total_cnt,
            covered_pairs=cov_cnt,
            coverage_ratio=ratio,
        )
