from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path
from typing import Any

_LIB = None
_TRIED_LOAD = False


def _find_library() -> Path | None:
    env_path = os.environ.get("ELMOS_NATIVE_LIB")
    if env_path and os.path.isfile(env_path):
        return Path(env_path)

    repo_root = Path(__file__).resolve().parents[4]
    ext = "dylib" if sys.platform == "darwin" else ("dll" if sys.platform == "win32" else "so")
    candidates = [
        repo_root / "native" / "rust-core" / "target" / "release" / f"libelmos_native.{ext}",
        repo_root / "native" / "rust-core" / "target" / "debug" / f"libelmos_native.{ext}",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _get_lib():
    global _LIB, _TRIED_LOAD
    if _TRIED_LOAD:
        return _LIB
    _TRIED_LOAD = True
    lib_path = _find_library()
    if not lib_path:
        return None
    try:
        lib = ctypes.CDLL(str(lib_path))
        lib.elmos_scan_bytecode_bytes.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        lib.elmos_scan_bytecode_bytes.restype = ctypes.c_void_p

        lib.elmos_scan_bytecode_dir.argtypes = [ctypes.c_char_p]
        lib.elmos_scan_bytecode_dir.restype = ctypes.c_void_p

        lib.elmos_shadow_diff_compare.argtypes = [ctypes.c_char_p]
        lib.elmos_shadow_diff_compare.restype = ctypes.c_void_p

        lib.elmos_free_string.argtypes = [ctypes.c_void_p]
        lib.elmos_free_string.restype = None
        _LIB = lib
    except Exception:
        _LIB = None
    return _LIB


def _python_scan_bytecode_bytes(data: bytes) -> dict[str, Any] | None:
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        return None
    try:
        cursor = 4
        minor_version = int.from_bytes(data[cursor : cursor + 2], "big")
        cursor += 2
        major_version = int.from_bytes(data[cursor : cursor + 2], "big")
        cursor += 2
        cp_count = int.from_bytes(data[cursor : cursor + 2], "big")
        cursor += 2

        if cp_count == 0:
            return None

        constant_pool: list[tuple[str, Any] | None] = [None] * cp_count
        i = 1
        while i < cp_count:
            if cursor >= len(data):
                return None
            tag = data[cursor]
            cursor += 1
            if tag == 1:
                length = int.from_bytes(data[cursor : cursor + 2], "big")
                cursor += 2
                s = data[cursor : cursor + length].decode("utf-8", errors="replace")
                cursor += length
                constant_pool[i] = ("Utf8", s)
            elif tag in (3, 4):
                cursor += 4
                constant_pool[i] = ("Other", None)
            elif tag in (5, 6):
                cursor += 8
                constant_pool[i] = ("Other", None)
                i += 1
            elif tag == 7:
                name_idx = int.from_bytes(data[cursor : cursor + 2], "big")
                cursor += 2
                constant_pool[i] = ("Class", name_idx)
            elif tag == 8:
                cursor += 2
                constant_pool[i] = ("Other", None)
            elif tag in (9, 10, 11, 12):
                cursor += 4
                constant_pool[i] = ("Other", None)
            elif tag == 15:
                cursor += 3
                constant_pool[i] = ("Other", None)
            elif tag == 16:
                cursor += 2
                constant_pool[i] = ("Other", None)
            elif tag in (17, 18):
                cursor += 4
                constant_pool[i] = ("Other", None)
            elif tag in (19, 20):
                cursor += 2
                constant_pool[i] = ("Other", None)
            else:
                break
            i += 1

        if cursor + 6 > len(data):
            return None

        cursor += 2  # access_flags
        this_class_idx = int.from_bytes(data[cursor : cursor + 2], "big")
        cursor += 2
        super_class_idx = int.from_bytes(data[cursor : cursor + 2], "big")
        cursor += 2

        def resolve_class_name(idx: int) -> str | None:
            if 0 < idx < len(constant_pool):
                entry = constant_pool[idx]
                if entry and entry[0] == "Class":
                    n_idx = entry[1]
                    if 0 < n_idx < len(constant_pool):
                        n_entry = constant_pool[n_idx]
                        if n_entry and n_entry[0] == "Utf8":
                            return n_entry[1]
            return None

        class_name = resolve_class_name(this_class_idx) or "Unknown"
        super_class = resolve_class_name(super_class_idx)

        interfaces_count = int.from_bytes(data[cursor : cursor + 2], "big")
        cursor += 2
        interfaces = []
        for _ in range(interfaces_count):
            if cursor + 2 <= len(data):
                iface_idx = int.from_bytes(data[cursor : cursor + 2], "big")
                cursor += 2
                if_name = resolve_class_name(iface_idx)
                if if_name:
                    interfaces.append(if_name)

        spring_annotations: set[str] = set()
        referenced_classes: set[str] = set()

        for entry in constant_pool:
            if entry and entry[0] == "Utf8":
                s = entry[1]
                for ann in ("Controller", "RestController", "Service", "Repository", "Component", "Configuration", "Transactional"):
                    if ann in s:
                        spring_annotations.add(ann)
                if s.startswith("L") and s.endswith(";") and "/" in s:
                    referenced_classes.add(s[1:-1])

        return {
            "class_name": class_name,
            "super_class": super_class,
            "interfaces": interfaces,
            "major_version": major_version,
            "minor_version": minor_version,
            "spring_annotations": sorted(list(spring_annotations)),
            "referenced_classes": sorted(list(referenced_classes)),
            "is_controller": "Controller" in spring_annotations or "RestController" in spring_annotations,
            "is_service": "Service" in spring_annotations,
            "is_repository": "Repository" in spring_annotations,
            "is_component": "Component" in spring_annotations,
            "is_configuration": "Configuration" in spring_annotations,
            "is_transactional": "Transactional" in spring_annotations,
        }
    except Exception:
        return None


def _python_scan_bytecode_dir(dir_path: str) -> dict[str, Any]:
    p = Path(dir_path)
    classes = []
    errors = []
    if not p.is_dir():
        return {
            "scanned_classes_count": 0,
            "controllers_count": 0,
            "services_count": 0,
            "repositories_count": 0,
            "classes": [],
            "errors": [f"Directory not found: {dir_path}"],
        }
    for file in p.rglob("*.class"):
        try:
            raw = file.read_bytes()
            meta = _python_scan_bytecode_bytes(raw)
            if meta:
                classes.append(meta)
            else:
                errors.append(f"Failed to parse class: {file}")
        except Exception as ex:
            errors.append(f"{file}: {ex}")

    return {
        "scanned_classes_count": len(classes),
        "controllers_count": sum(1 for c in classes if c.get("is_controller")),
        "services_count": sum(1 for c in classes if c.get("is_service")),
        "repositories_count": sum(1 for c in classes if c.get("is_repository")),
        "classes": classes,
        "errors": errors,
    }


def _python_shadow_diff(
    primary: dict[str, Any],
    shadow: dict[str, Any],
    ignored_headers: list[str] | None = None,
    ignored_body_fields: list[str] | None = None,
    float_tolerance: float | None = None,
) -> dict[str, Any]:
    p_status = primary.get("status", 0)
    s_status = shadow.get("status", 0)
    status_code_match = p_status == s_status

    default_ignored_headers = {
        "date", "x-request-id", "x-trace-id", "server", "keep-alive",
        "transfer-encoding", "content-length", "age", "etag", "set-cookie",
        "x-envoy-upstream-service-time",
    }
    ign_headers = default_ignored_headers | {h.lower() for h in (ignored_headers or [])}

    p_headers = {k.lower(): v.strip() for k, v in primary.get("headers", {}).items() if k.lower() not in ign_headers}
    s_headers = {k.lower(): v.strip() for k, v in shadow.get("headers", {}).items() if k.lower() not in ign_headers}

    header_mismatches = []
    all_header_keys = sorted(set(p_headers.keys()) | set(s_headers.keys()))
    for hk in all_header_keys:
        pval = p_headers.get(hk)
        sval = s_headers.get(hk)
        if pval != sval:
            header_mismatches.append({
                "header_name": hk,
                "primary_value": pval,
                "shadow_value": sval,
            })

    default_ignored_fields = {
        "timestamp", "time", "traceid", "requestid", "spanid", "duration", "executiontimems",
    }
    ign_fields = default_ignored_fields | {f.lower() for f in (ignored_body_fields or [])}
    tol = float_tolerance if float_tolerance is not None else 1e-6

    body_mismatches: list[dict[str, Any]] = []

    def _compare_values(path: str, p_val: Any, s_val: Any):
        if isinstance(p_val, dict) and isinstance(s_val, dict):
            all_keys = sorted(set(p_val.keys()) | set(s_val.keys()))
            for k in all_keys:
                if k.lower() in ign_fields:
                    continue
                sub_path = f"{path}.{k}"
                if k not in p_val:
                    body_mismatches.append({
                        "path": sub_path,
                        "primary_value": None,
                        "shadow_value": s_val[k],
                        "reason": "Field unexpected in shadow response",
                    })
                elif k not in s_val:
                    body_mismatches.append({
                        "path": sub_path,
                        "primary_value": p_val[k],
                        "shadow_value": None,
                        "reason": "Field missing in shadow response",
                    })
                else:
                    _compare_values(sub_path, p_val[k], s_val[k])
        elif isinstance(p_val, list) and isinstance(s_val, list):
            if len(p_val) != len(s_val):
                body_mismatches.append({
                    "path": path,
                    "primary_value": p_val,
                    "shadow_value": s_val,
                    "reason": f"Array length mismatch: {len(p_val)} vs {len(s_val)}",
                })
            else:
                for idx, (p_elem, s_elem) in enumerate(zip(p_val, s_val)):
                    _compare_values(f"{path}[{idx}]", p_elem, s_elem)
        elif isinstance(p_val, (int, float)) and isinstance(s_val, (int, float)):
            if abs(float(p_val) - float(s_val)) > tol:
                body_mismatches.append({
                    "path": path,
                    "primary_value": p_val,
                    "shadow_value": s_val,
                    "reason": f"Numeric difference exceeds tolerance {tol}",
                })
        else:
            if p_val != s_val:
                body_mismatches.append({
                    "path": path,
                    "primary_value": p_val,
                    "shadow_value": s_val,
                    "reason": "Values differ",
                })

    p_body = primary.get("body", "")
    s_body = shadow.get("body", "")

    try:
        p_json = json.loads(p_body)
        s_json = json.loads(s_body)
        _compare_values("$", p_json, s_json)
    except Exception:
        if p_body.strip() != s_body.strip():
            body_mismatches.append({
                "path": "$",
                "primary_value": p_body,
                "shadow_value": s_body,
                "reason": "Text content differs",
            })

    is_match = status_code_match and len(header_mismatches) == 0 and len(body_mismatches) == 0
    p_latency = primary.get("latency_ms", 0.0)
    s_latency = shadow.get("latency_ms", 0.0)
    latency_delta_ms = s_latency - p_latency

    if is_match:
        summary = f"IDENTICAL: Status={p_status}, LatencyDelta={latency_delta_ms:.2f}ms"
    else:
        summary = f"DIFF_DETECTED: StatusMatch={status_code_match}, HeaderDiffs={len(header_mismatches)}, BodyDiffs={len(body_mismatches)}"

    return {
        "is_match": is_match,
        "status_code_match": status_code_match,
        "primary_status": p_status,
        "shadow_status": s_status,
        "header_mismatches": header_mismatches,
        "body_mismatches": body_mismatches,
        "latency_delta_ms": latency_delta_ms,
        "summary": summary,
    }


def native_scan_bytecode_bytes(data: bytes) -> dict[str, Any] | None:
    lib = _get_lib()
    if lib is None:
        return _python_scan_bytecode_bytes(data)
    try:
        ptr = lib.elmos_scan_bytecode_bytes(data, len(data))
        if not ptr:
            return _python_scan_bytecode_bytes(data)
        raw_str = ctypes.string_at(ptr).decode("utf-8")
        lib.elmos_free_string(ptr)
        return json.loads(raw_str)
    except Exception:
        return _python_scan_bytecode_bytes(data)


def native_scan_bytecode_dir(dir_path: str) -> dict[str, Any] | None:
    lib = _get_lib()
    if lib is None:
        return _python_scan_bytecode_dir(dir_path)
    try:
        ptr = lib.elmos_scan_bytecode_dir(dir_path.encode("utf-8"))
        if not ptr:
            return _python_scan_bytecode_dir(dir_path)
        raw_str = ctypes.string_at(ptr).decode("utf-8")
        lib.elmos_free_string(ptr)
        return json.loads(raw_str)
    except Exception:
        return _python_scan_bytecode_dir(dir_path)


def native_shadow_diff(
    primary: dict[str, Any],
    shadow: dict[str, Any],
    ignored_headers: list[str] | None = None,
    ignored_body_fields: list[str] | None = None,
    float_tolerance: float | None = None,
) -> dict[str, Any] | None:
    lib = _get_lib()
    if lib is None:
        return _python_shadow_diff(
            primary, shadow, ignored_headers, ignored_body_fields, float_tolerance
        )
    try:
        req = {
            "primary": primary,
            "shadow": shadow,
            "ignored_headers": ignored_headers or [],
            "ignored_body_fields": ignored_body_fields or [],
            "float_tolerance": float_tolerance,
        }
        payload = json.dumps(req).encode("utf-8")
        ptr = lib.elmos_shadow_diff_compare(payload)
        if not ptr:
            return _python_shadow_diff(
                primary, shadow, ignored_headers, ignored_body_fields, float_tolerance
            )
        raw_str = ctypes.string_at(ptr).decode("utf-8")
        lib.elmos_free_string(ptr)
        return json.loads(raw_str)
    except Exception:
        return _python_shadow_diff(
            primary, shadow, ignored_headers, ignored_body_fields, float_tolerance
        )

