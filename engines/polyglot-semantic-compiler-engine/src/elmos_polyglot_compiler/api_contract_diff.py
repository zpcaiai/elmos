"""ELMOS API Contract & Backward-Compatibility Drift Diffing Engine.

Analyzes REST/OpenAPI and RPC interface schemas before and after transformation
to identify breaking field removals, type narrowing hazards, and route incompatibilities.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ContractDiffItem:
    endpoint: str
    category: str  # FIELD_REMOVED, FIELD_ADDED, TYPE_NARROWING, OPTIONALITY_CHANGED
    severity: str  # BREAKING, WARNING, NON_BREAKING
    description: str
    field_name: Optional[str] = None


@dataclass
class ContractDiffReport:
    total_changes: int
    breaking_changes_count: int
    warnings_count: int
    non_breaking_count: int
    is_backward_compatible: bool
    duration_ms: float
    changes: List[ContractDiffItem]


class ApiContractDiffer:
    """Compares source and target API interface schemas for compatibility drift."""

    def compare_specs(
        self,
        source_spec: Dict[str, Any],
        target_spec: Dict[str, Any],
    ) -> ContractDiffReport:
        start_time = time.perf_counter()
        changes: List[ContractDiffItem] = []

        src_endpoints = source_spec.get("endpoints", {})
        tgt_endpoints = target_spec.get("endpoints", {})

        # Check for removed endpoints
        for ep_key, src_ep in src_endpoints.items():
            if ep_key not in tgt_endpoints:
                changes.append(
                    ContractDiffItem(
                        endpoint=ep_key,
                        category="ENDPOINT_REMOVED",
                        severity="BREAKING",
                        description=f"Endpoint '{ep_key}' present in source service was dropped in target",
                    )
                )
                continue

            tgt_ep = tgt_endpoints[ep_key]

            # Compare request fields
            src_req = src_ep.get("request_fields", {})
            tgt_req = tgt_ep.get("request_fields", {})

            for f_name, f_info in src_req.items():
                if f_name not in tgt_req:
                    # Request field missing in target -> WARNING/BREAKING depending on required
                    is_req = f_info.get("required", False)
                    changes.append(
                        ContractDiffItem(
                            endpoint=ep_key,
                            category="FIELD_REMOVED",
                            severity="BREAKING" if is_req else "WARNING",
                            field_name=f_name,
                            description=f"Request field '{f_name}' removed from endpoint '{ep_key}'",
                        )
                    )
                else:
                    tgt_info = tgt_req[f_name]
                    if f_info.get("type") != tgt_info.get("type"):
                        changes.append(
                            ContractDiffItem(
                                endpoint=ep_key,
                                category="TYPE_NARROWING",
                                severity="BREAKING",
                                field_name=f_name,
                                description=f"Type changed from {f_info.get('type')} to {tgt_info.get('type')}",
                            )
                        )

            # Compare response fields
            src_resp = src_ep.get("response_fields", {})
            tgt_resp = tgt_ep.get("response_fields", {})

            for f_name, f_info in src_resp.items():
                if f_name not in tgt_resp:
                    changes.append(
                        ContractDiffItem(
                            endpoint=ep_key,
                            category="FIELD_REMOVED",
                            severity="BREAKING",
                            field_name=f_name,
                            description=f"Response field '{f_name}' missing in target response DTO",
                        )
                    )

            for f_name in tgt_resp:
                if f_name not in src_resp:
                    changes.append(
                        ContractDiffItem(
                            endpoint=ep_key,
                            category="FIELD_ADDED",
                            severity="NON_BREAKING",
                            field_name=f_name,
                            description=f"Non-breaking additive field '{f_name}' added to response",
                        )
                    )

        breaking_count = sum(1 for c in changes if c.severity == "BREAKING")
        warnings_count = sum(1 for c in changes if c.severity == "WARNING")
        non_breaking_count = sum(1 for c in changes if c.severity == "NON_BREAKING")
        duration_ms = round((time.perf_counter() - start_time) * 1000, 3)

        return ContractDiffReport(
            total_changes=len(changes),
            breaking_changes_count=breaking_count,
            warnings_count=warnings_count,
            non_breaking_count=non_breaking_count,
            is_backward_compatible=(breaking_count == 0),
            duration_ms=duration_ms,
            changes=changes,
        )


# Global singleton
_contract_differ = ApiContractDiffer()


def run_api_contract_diff(
    source_spec: Optional[Dict[str, Any]] = None,
    target_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute API contract diff and return JSON report."""
    if source_spec is None:
        source_spec = {
            "endpoints": {
                "POST /api/v1/orders": {
                    "request_fields": {
                        "order_id": {"type": "string", "required": True},
                        "amount": {"type": "float", "required": True},
                        "currency": {"type": "string", "required": False},
                    },
                    "response_fields": {
                        "order_id": {"type": "string"},
                        "status": {"type": "string"},
                        "created_at": {"type": "string"},
                    },
                }
            }
        }

    if target_spec is None:
        target_spec = {
            "endpoints": {
                "POST /api/v1/orders": {
                    "request_fields": {
                        "order_id": {"type": "string", "required": True},
                        "amount": {"type": "float", "required": True},
                        # currency removed -> WARNING
                    },
                    "response_fields": {
                        "order_id": {"type": "string"},
                        "status": {"type": "string"},
                        "created_at": {"type": "string"},
                        "transaction_hash": {"type": "string"},  # NON_BREAKING
                    },
                }
            }
        }

    rep = _contract_differ.compare_specs(source_spec, target_spec)
    return {
        "status": "COMPATIBLE" if rep.is_backward_compatible else "BREAKING_CHANGES_DETECTED",
        "is_backward_compatible": rep.is_backward_compatible,
        "breaking_changes_count": rep.breaking_changes_count,
        "warnings_count": rep.warnings_count,
        "non_breaking_count": rep.non_breaking_count,
        "total_changes": rep.total_changes,
        "duration_ms": rep.duration_ms,
        "changes": [asdict(c) for c in rep.changes],
    }
