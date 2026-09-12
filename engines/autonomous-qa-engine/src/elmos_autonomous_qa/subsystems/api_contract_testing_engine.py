"""API Schema Contract Testing & Boundary Fuzz Payload Synthesizer.

Generates extreme boundary values, malformed data, and injection attack vectors
to verify that API endpoints enforce strict schema validation contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class FuzzPayload:
    payload_id: str
    target_field: str
    fuzz_category: str  # BOUNDARY_INTEGER, NULL_INJECTION, TYPE_CONFUSION, SQL_INJECTION, XSS
    value: Any
    expected_status: int = 400
    description: str = ""


@dataclass
class ContractValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)


class APIContractTestingEngine:
    """Synthesizes boundary fuzz payloads and validates payloads against JSON schema."""

    @classmethod
    def synthesize_boundary_payloads(cls, schema: Dict[str, Any]) -> List[FuzzPayload]:
        payloads: List[FuzzPayload] = []
        counter = 0

        properties = schema.get("properties", {})
        for field_name, field_def in properties.items():
            f_type = field_def.get("type", "string")

            if f_type == "integer":
                # Boundary integers
                for val, desc in (
                    (-2147483649, "32-bit signed underflow"),
                    (2147483648, "32-bit signed overflow"),
                    (0, "zero boundary"),
                    (-1, "negative boundary"),
                    ("not_an_int", "type confusion string"),
                    (None, "null value"),
                ):
                    counter += 1
                    payloads.append(
                        FuzzPayload(
                            payload_id=f"FUZZ-INT-{counter}",
                            target_field=field_name,
                            fuzz_category="BOUNDARY_INTEGER" if isinstance(val, int) else "TYPE_CONFUSION",
                            value=val,
                            description=desc,
                        )
                    )

            elif f_type == "string":
                # String boundaries & security injection probes
                for val, cat, desc in (
                    ("", "BOUNDARY_STRING", "empty string"),
                    ("A" * 4096, "BUFFER_OVERFLOW", "long 4KB string"),
                    (None, "NULL_INJECTION", "null in non-null string"),
                    ("' OR '1'='1' --", "SQL_INJECTION", "SQL injection quote escape"),
                    ("<script>alert(1)</script>", "XSS", "XSS tag injection"),
                    ("../../../etc/passwd", "PATH_TRAVERSAL", "Directory traversal probe"),
                ):
                    counter += 1
                    payloads.append(
                        FuzzPayload(
                            payload_id=f"FUZZ-STR-{counter}",
                            target_field=field_name,
                            fuzz_category=cat,
                            value=val,
                            description=desc,
                        )
                    )

            elif f_type == "number":
                for val, desc in (
                    (float('inf'), "infinite float"),
                    (-1e308, "extreme negative double"),
                    (1e308, "extreme positive double"),
                    (None, "null float"),
                ):
                    counter += 1
                    payloads.append(
                        FuzzPayload(
                            payload_id=f"FUZZ-NUM-{counter}",
                            target_field=field_name,
                            fuzz_category="BOUNDARY_NUMBER",
                            value=val if not math.isinf(val if val is not None else 0) else 9999999999.99,
                            description=desc,
                        )
                    )

        return payloads

    @classmethod
    def validate_instance(cls, schema: Dict[str, Any], instance: Dict[str, Any]) -> ContractValidationResult:
        errors: List[str] = []

        # Check required
        required = schema.get("required", [])
        for req_field in required:
            if req_field not in instance or instance[req_field] is None:
                errors.append(f"Missing required field: {req_field}")

        # Check property types
        properties = schema.get("properties", {})
        for k, v in instance.items():
            if k not in properties:
                if not schema.get("additionalProperties", True):
                    errors.append(f"Unexpected property: {k}")
                continue

            expected_type = properties[k].get("type")
            if expected_type == "integer" and not isinstance(v, int):
                errors.append(f"Field {k} expected integer, got {type(v).__name__}")
            elif expected_type == "string" and not isinstance(v, str):
                errors.append(f"Field {k} expected string, got {type(v).__name__}")
            elif expected_type == "boolean" and not isinstance(v, bool):
                errors.append(f"Field {k} expected boolean, got {type(v).__name__}")
            elif expected_type == "array" and not isinstance(v, list):
                errors.append(f"Field {k} expected array, got {type(v).__name__}")

        return ContractValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
        )
