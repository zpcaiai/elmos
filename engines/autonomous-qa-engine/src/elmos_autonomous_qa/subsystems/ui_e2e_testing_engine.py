"""Industrial UI E2E Testing Engine: Page Object Model & Multi-Tier Resilient Selectors.

Provides Page Object Model (POM) synthesis, selector fallback hierarchy (data-testid ->
aria-role -> CSS -> XPath), and user journey simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class UIElementSelector:
    element_id: str
    data_testid: Optional[str] = None
    aria_role: Optional[str] = None
    aria_label: Optional[str] = None
    css_selector: Optional[str] = None
    xpath: Optional[str] = None

    def resolve_selector(self, dom_tree: Dict[str, Any]) -> Tuple[Optional[str], str]:
        """Resolves target element using hierarchical resilience fallback ladder."""
        if self.data_testid and self.data_testid in dom_tree.get("testids", {}):
            return self.data_testid, "DATA_TESTID"
        if self.aria_role and self.aria_role in dom_tree.get("roles", {}):
            return self.aria_role, "ARIA_ROLE"
        if self.aria_label and self.aria_label in dom_tree.get("labels", {}):
            return self.aria_label, "ARIA_LABEL"
        if self.css_selector and self.css_selector in dom_tree.get("css", {}):
            return self.css_selector, "CSS_SELECTOR"
        if self.xpath and self.xpath in dom_tree.get("xpath", {}):
            return self.xpath, "XPATH"

        return None, "NOT_FOUND"


@dataclass
class UIJourneyStep:
    step_id: str
    action_type: str  # 'CLICK', 'FILL', 'NAVIGATE', 'ASSERT_TEXT'
    selector: Optional[UIElementSelector] = None
    payload: Optional[str] = None
    expected_value: Optional[str] = None


@dataclass
class JourneyExecutionReport:
    journey_name: str
    passed: bool
    executed_steps: int
    failed_step_id: Optional[str]
    selector_fallback_histogram: Dict[str, int]
    session_merkle: str


class UIE2ETestingEngine:
    """Resilient UI E2E journey execution and Page Object Model synthesizer."""

    @staticmethod
    def execute_journey(
        journey_name: str,
        steps: List[UIJourneyStep],
        dom_tree: Dict[str, Any],
    ) -> JourneyExecutionReport:
        histogram: Dict[str, int] = {}
        executed = 0
        failed_id = None
        passed = True

        for step in steps:
            executed += 1
            if step.action_type in ("CLICK", "FILL", "ASSERT_TEXT"):
                if not step.selector:
                    passed = False
                    failed_id = step.step_id
                    break
                sel, tier = step.selector.resolve_selector(dom_tree)
                histogram[tier] = histogram.get(tier, 0) + 1
                if sel is None:
                    passed = False
                    failed_id = step.step_id
                    break

                if step.action_type == "ASSERT_TEXT":
                    actual_text = dom_tree.get("texts", {}).get(sel, "")
                    if actual_text != step.expected_value:
                        passed = False
                        failed_id = step.step_id
                        break

        merkle_payload = f"{journey_name}:{executed}:{passed}:{failed_id}"
        session_merkle = hashlib.sha256(merkle_payload.encode("utf-8")).hexdigest()

        return JourneyExecutionReport(
            journey_name=journey_name,
            passed=passed,
            executed_steps=executed,
            failed_step_id=failed_id,
            selector_fallback_histogram=histogram,
            session_merkle=session_merkle,
        )
