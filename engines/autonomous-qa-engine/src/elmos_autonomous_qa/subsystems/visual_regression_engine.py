"""Industrial Visual Regression and Layout Shift Geometry Diffing Engine.

Calculates bounding box Intersection-over-Union (IoU), computed CSS property diffs,
and Cumulative Layout Shift (CLS) scores for pixel and layout stability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class BoundingBox:
    x: float
    y: float
    width: float
    height: float

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def intersection(self, other: BoundingBox) -> float:
        x_left = max(self.x, other.x)
        y_top = max(self.y, other.y)
        x_right = min(self.x + self.width, other.x + other.width)
        y_bottom = min(self.y + self.height, other.y + other.height)

        if x_right < x_left or y_bottom < y_top:
            return 0.0
        return (x_right - x_left) * (y_bottom - y_top)

    def iou(self, other: BoundingBox) -> float:
        inter = self.intersection(other)
        union = self.area + other.area - inter
        if union <= 0.0:
            return 1.0 if self.area == 0.0 and other.area == 0.0 else 0.0
        return round(inter / union, 4)


@dataclass
class VisualDiffResult:
    is_identical: bool
    layout_shift_score: float
    iou_scores: Dict[str, float]
    css_mismatches: Dict[str, Dict[str, Tuple[Any, Any]]]
    passed_tolerance: bool


class VisualRegressionEngine:
    """Audits DOM element geometry, CSS styles, and layout shifts."""

    @staticmethod
    def diff_layouts(
        baseline_elements: Dict[str, Tuple[BoundingBox, Dict[str, Any]]],
        candidate_elements: Dict[str, Tuple[BoundingBox, Dict[str, Any]]],
        viewport_area: float = 1920.0 * 1080.0,
        cls_threshold: float = 0.05,
        min_iou_threshold: float = 0.95,
    ) -> VisualDiffResult:
        iou_scores: Dict[str, float] = {}
        css_mismatches: Dict[str, Dict[str, Tuple[Any, Any]]] = {}
        total_cls = 0.0

        all_keys = set(baseline_elements.keys()) | set(candidate_elements.keys())

        for elem_id in sorted(all_keys):
            if elem_id not in baseline_elements or elem_id not in candidate_elements:
                iou_scores[elem_id] = 0.0
                total_cls += 0.05
                continue

            base_box, base_css = baseline_elements[elem_id]
            cand_box, cand_css = candidate_elements[elem_id]

            iou = base_box.iou(cand_box)
            iou_scores[elem_id] = iou

            dx = abs(base_box.x - cand_box.x)
            dy = abs(base_box.y - cand_box.y)
            shift_dist = (dx**2 + dy**2) ** 0.5

            if shift_dist > 0.0:
                impact_fraction = (base_box.area + cand_box.area - base_box.intersection(cand_box)) / viewport_area
                distance_fraction = shift_dist / 1080.0
                total_cls += impact_fraction * distance_fraction

            mismatches = {}
            for prop, val in base_css.items():
                cand_val = cand_css.get(prop)
                if cand_val != val:
                    mismatches[prop] = (val, cand_val)
            if mismatches:
                css_mismatches[elem_id] = mismatches

        is_identical = (all(s == 1.0 for s in iou_scores.values())) and (len(css_mismatches) == 0)
        passed = (total_cls <= cls_threshold) and (all(s >= min_iou_threshold for s in iou_scores.values()))

        return VisualDiffResult(
            is_identical=is_identical,
            layout_shift_score=round(total_cls, 4),
            iou_scores=iou_scores,
            css_mismatches=css_mismatches,
            passed_tolerance=passed,
        )
