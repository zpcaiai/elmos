"""WCAG 2.2 Accessibility Compliance & Color Contrast Ratio Engine.

Implements exact W3C WCAG 2.2 algorithms:
- Relative luminance formula: L = 0.2126 * R + 0.7152 * G + 0.0722 * B
- Contrast ratio formula: (L1 + 0.05) / (L2 + 0.05)
- Evaluates Level AA (4.5:1 normal, 3.0:1 large) and AAA (7.0:1 normal, 4.5:1 large)
- Validates ARIA attributes and heading hierarchy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ContrastEvaluationResult:
    foreground_rgb: Tuple[int, int, int]
    background_rgb: Tuple[int, int, int]
    fg_luminance: float
    bg_luminance: float
    contrast_ratio: float
    passes_aa_normal: bool
    passes_aa_large: bool
    passes_aaa_normal: bool
    passes_aaa_large: bool


@dataclass
class A11yAuditReport:
    total_checks: int
    violations_count: int
    compliance_score: float
    contrast_evaluations: List[ContrastEvaluationResult] = field(default_factory=list)
    aria_violations: List[str] = field(default_factory=list)
    heading_violations: List[str] = field(default_factory=list)


class WCAGA11yComplianceEngine:
    """Audits DOM structures and styles against WCAG 2.2 standards."""

    @classmethod
    def calculate_relative_luminance(cls, r: int, g: int, b: int) -> float:
        """W3C sRGB to linear relative luminance formula."""
        def channel_lum(c: int) -> float:
            val = c / 255.0
            return val / 12.92 if val <= 0.04045 else ((val + 0.055) / 1.055) ** 2.4

        rs = channel_lum(r)
        gs = channel_lum(g)
        bs = channel_lum(b)
        return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs

    @classmethod
    def calculate_contrast_ratio(
        cls,
        fg_rgb: Tuple[int, int, int],
        bg_rgb: Tuple[int, int, int],
    ) -> ContrastEvaluationResult:
        """Calculates contrast ratio (L1 + 0.05) / (L2 + 0.05)."""
        l1 = cls.calculate_relative_luminance(*fg_rgb)
        l2 = cls.calculate_relative_luminance(*bg_rgb)

        lighter = max(l1, l2)
        darker = min(l1, l2)
        ratio = round((lighter + 0.05) / (darker + 0.05), 2)

        return ContrastEvaluationResult(
            foreground_rgb=fg_rgb,
            background_rgb=bg_rgb,
            fg_luminance=round(l1, 4),
            bg_luminance=round(l2, 4),
            contrast_ratio=ratio,
            passes_aa_normal=ratio >= 4.5,
            passes_aa_large=ratio >= 3.0,
            passes_aaa_normal=ratio >= 7.0,
            passes_aaa_large=ratio >= 4.5,
        )

    @classmethod
    def audit_headings(cls, headings: List[int]) -> List[str]:
        """Audits heading levels (e.g. [1, 2, 4]) for illegal skipped levels."""
        violations: List[str] = []
        if not headings:
            return violations

        if headings[0] != 1:
            violations.append(f"First heading level is h{headings[0]}, expected h1")

        for i in range(1, len(headings)):
            prev = headings[i - 1]
            curr = headings[i]
            if curr > prev + 1:
                violations.append(f"Skipped heading level: h{prev} -> h{curr}")

        return violations

    @classmethod
    def audit_aria_roles(cls, elements: List[Dict[str, Any]]) -> List[str]:
        """Validates ARIA roles and required attributes."""
        violations: List[str] = []
        valid_roles = {"button", "dialog", "alert", "navigation", "main", "link", "checkbox"}

        for el in elements:
            role = el.get("role")
            tag = el.get("tag", "div")
            if role:
                if role not in valid_roles:
                    violations.append(f"Invalid ARIA role '{role}' on <{tag}>")
                if role == "button" and not (el.get("aria-label") or el.get("text")):
                    violations.append(f"Button role on <{tag}> requires accessible name (text or aria-label)")
                if role == "dialog" and not (el.get("aria-labelledby") or el.get("aria-label")):
                    violations.append(f"Dialog role on <{tag}> requires aria-label or aria-labelledby")

        return violations
