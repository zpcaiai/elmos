"""Domain Semantic Slot representation and extraction utilities.

A Domain Slot is a typed, bounded semantic seam in a deterministic DDD skeleton
where high-level business rules, pricing logic, complex state transitions, or domain
algorithms can be injected by advanced LLM models (Claude/Codex) with minimal context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple


class SlotType(Enum):
    CALCULATION = "CALCULATION"
    STATE_TRANSITION = "STATE_TRANSITION"
    VALIDATION = "VALIDATION"
    WORKFLOW_ORCHESTRATION = "WORKFLOW_ORCHESTRATION"
    POLICY_EVALUATION = "POLICY_EVALUATION"


@dataclass
class SlotParameter:
    name: str
    type_name: str
    description: str = ""


@dataclass
class SlotInvariant:
    expression: str
    description: str = ""


@dataclass
class DomainSlotSpec:
    slot_id: str
    slot_name: str
    target_file: str
    enclosing_class: str = ""
    method_signature: str = ""
    description: str = ""
    slot_type: SlotType = SlotType.CALCULATION
    parameters: List[SlotParameter] = field(default_factory=list)
    return_type: str = "void"
    invariants: List[SlotInvariant] = field(default_factory=list)
    required_dependencies: List[str] = field(default_factory=list)
    safe_stub_code: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def source_file(self) -> str:
        return self.target_file


    def render_marker_start(self, comment_prefix: str = "//") -> str:
        return f"{comment_prefix} [[ELMOS_DOMAIN_SLOT_START: {self.slot_id} | {self.slot_name}]]"

    def render_marker_end(self, comment_prefix: str = "//") -> str:
        return f"{comment_prefix} [[ELMOS_DOMAIN_SLOT_END: {self.slot_id}]]"


@dataclass
class SlotSynthesisResult:
    slot_id: str
    synthesized_code: str
    model_name: str = "claude-3-5-sonnet"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    ast_valid: bool = True
    conformance_passed: bool = True
    warnings: List[str] = field(default_factory=list)


class DomainSlotParser:
    """Extracts and replaces semantic domain slots inside generated code."""

    SLOT_PATTERN = re.compile(
        r"(?P<prefix>//|#)\s*\[\[ELMOS_DOMAIN_SLOT_START:\s*(?P<slot_id>[a-zA-Z0-9_\-]+)(?:\s*\|\s*(?P<slot_name>[^\]]+))?\]\]\n"
        r"(?P<body>.*?)\n"
        r"(?P=prefix)\s*\[\[ELMOS_DOMAIN_SLOT_END:\s*(?P=slot_id)\]\]",
        re.DOTALL
    )

    @classmethod
    def find_slots_in_content(cls, content: str) -> List[Tuple[str, str, str]]:
        """Finds all (slot_id, slot_name, body) in source code content."""
        results = []
        for match in cls.SLOT_PATTERN.finditer(content):
            slot_id = match.group("slot_id")
            slot_name = match.group("slot_name") or slot_id
            body = match.group("body")
            results.append((slot_id, slot_name.strip(), body))
        return results

    @classmethod
    def replace_slot(cls, content: str, slot_id: str, new_code: str, comment_prefix: str = "//") -> str:
        """Replaces a specific slot body with new synthesized code, preserving boundary markers."""
        pattern = re.compile(
            rf"(?P<prefix>//|#)\s*\[\[ELMOS_DOMAIN_SLOT_START:\s*{re.escape(slot_id)}(?:\s*\|\s*[^\]]+)?\]\]\n"
            r".*?\n"
            rf"(?P=prefix)\s*\[\[ELMOS_DOMAIN_SLOT_END:\s*{re.escape(slot_id)}\]\]",
            re.DOTALL
        )

        def replacer(match: re.Match[str]) -> str:
            prefix = match.group("prefix")
            matched_header = match.group(0).splitlines()[0]
            footer = f"{prefix} [[ELMOS_DOMAIN_SLOT_END: {slot_id}]]"
            return f"{matched_header}\n{new_code}\n{footer}"

        new_content, count = pattern.subn(replacer, content)
        if count == 0:
            raise ValueError(f"Domain slot '{slot_id}' not found in target content.")
        return new_content
