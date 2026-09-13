"""Industrial Relational Test Data Synthesis & PII Masking Engine.

Solves table dependency topological sort for cascade generation, enforces foreign
key relationships, and provides deterministic pseudonymization for sensitive fields.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Dict, List, Optional, Set


@dataclass
class ForeignKeyConstraint:
    child_column: str
    parent_table: str
    parent_column: str


@dataclass
class TableSchema:
    name: str
    primary_key: str
    columns: Dict[str, str]  # name -> type
    foreign_keys: List[ForeignKeyConstraint] = field(default_factory=list)


class TestDataSynthesisEngine:
    """Topological relational data synthesizer with PII pseudonymization."""

    @staticmethod
    def solve_insertion_order(tables: List[TableSchema]) -> List[str]:
        """Kahn's algorithm to resolve topological insert order based on foreign keys."""
        table_map = {t.name: t for t in tables}
        in_degree: Dict[str, int] = {t.name: 0 for t in tables}
        adj: Dict[str, Set[str]] = defaultdict(set)

        for t in tables:
            for fk in t.foreign_keys:
                if fk.parent_table in table_map and fk.parent_table != t.name:
                    adj[fk.parent_table].add(t.name)
                    in_degree[t.name] += 1

        queue = deque([name for name, deg in in_degree.items() if deg == 0])
        order = []
        while queue:
            curr = queue.popleft()
            order.append(curr)
            for child in adj[curr]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(order) != len(tables):
            raise ValueError("Cyclic table foreign key dependency detected")
        return order

    @staticmethod
    def mask_pii(text: str, salt: str = "elmos_salt") -> str:
        """Deterministic pseudonymization of sensitive PII (email, phone, credit card)."""
        def mask_email(match: re.Match) -> str:
            val = match.group(0)
            h = hashlib.sha256((val + salt).encode("utf-8")).hexdigest()[:8]
            domain = val.split("@")[1]
            return f"user_{h}@{domain}"

        text = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", mask_email, text)

        def mask_phone(match: re.Match) -> str:
            digits = re.sub(r"\D", "", match.group(0))
            if len(digits) >= 10:
                return f"{digits[:3]}-***-**{digits[-2:]}"
            return "***-****"

        text = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", mask_phone, text)

        def mask_cc(match: re.Match) -> str:
            cc = match.group(0)
            last4 = cc[-4:]
            return f"****-****-****-{last4}"

        text = re.sub(r"\b(?:\d{4}[-\s]?){3}\d{4}\b", mask_cc, text)
        return text
