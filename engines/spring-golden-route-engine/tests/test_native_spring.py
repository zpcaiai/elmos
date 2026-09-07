from __future__ import annotations

import pytest
from elmos_spring_golden_route.native_spring_bridge import (
    native_scan_bytecode_bytes,
    native_shadow_diff,
)


def _make_class_bytes(name: str, parent: str, annot: str) -> bytes:
    b = bytearray()
    b.extend([0xCA, 0xFE, 0xBA, 0xBE, 0x00, 0x00, 0x00, 0x3D, 0x00, 0x06])
    b.extend([0x07, 0x00, 0x02])
    name_b = name.encode("utf-8")
    b.extend([0x01, len(name_b) >> 8, len(name_b) & 0xFF])
    b.extend(name_b)
    b.extend([0x07, 0x00, 0x04])
    parent_b = parent.encode("utf-8")
    b.extend([0x01, len(parent_b) >> 8, len(parent_b) & 0xFF])
    b.extend(parent_b)
    annot_b = annot.encode("utf-8")
    b.extend([0x01, len(annot_b) >> 8, len(annot_b) & 0xFF])
    b.extend(annot_b)
    b.extend([0x00, 0x21, 0x00, 0x01, 0x00, 0x03, 0x00, 0x00])
    return bytes(b)


def test_native_bytecode_scanner() -> None:
    data = _make_class_bytes(
        "com/example/api/OrderController",
        "java/lang/Object",
        "Lorg/springframework/web/bind/annotation/RestController;",
    )
    result = native_scan_bytecode_bytes(data)
    assert result is not None
    assert result["class_name"] == "com/example/api/OrderController"
    assert result["is_controller"] is True
    assert result["is_service"] is False
    assert result["major_version"] == 61


def test_native_shadow_diff() -> None:
    primary = {
        "status": 200,
        "headers": {"content-type": "application/json", "x-request-id": "req-1"},
        "body": '{"code": 0, "data": {"items": [1, 2, 3]}, "timestamp": 12345}',
        "latency_ms": 10.0,
    }
    shadow = {
        "status": 200,
        "headers": {"content-type": "application/json", "x-request-id": "req-2"},
        "body": '{"data": {"items": [1, 2, 3]}, "code": 0, "timestamp": 67890}',
        "latency_ms": 8.5,
    }

    diff = native_shadow_diff(primary, shadow)
    assert diff is not None
    assert diff["is_match"] is True
    assert diff["status_code_match"] is True
    assert len(diff["header_mismatches"]) == 0
    assert len(diff["body_mismatches"]) == 0
