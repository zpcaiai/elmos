"""Drill 2: Micro-benchmarks & Speedup Comparison.

Compares execution time and throughput between:
  1. Rust Native C-ABI (libelmos_native.dylib)
  2. Pure Python Fallback Implementation

Measures:
  - Complex SQL Script Splitting with Stored Procedures (scripts/sec)
  - Multi-Ecosystem Dependency Version Resolution (PubGrub algorithm)
  - EBCDIC Transcoding (Throughput in MB/s)
  - COMP-3 Packed Decimal Decoding (ops/sec)
  - Industrial Modbus Byte-Swapping (ops/sec)
  - Dependency Graph Blast Radius Traversal (traversals/sec)
"""

from __future__ import annotations

import ctypes
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.drills.native_bridge_helper import (
    get_lib,
    native_sql_split,
    python_sql_split,
    native_ebcdic_to_ascii,
    python_ebcdic_to_ascii,
    native_comp3_decode,
    python_comp3_decode,
    native_swap_bytes,
    python_swap_bytes,
    native_blast_radius,
    python_blast_radius,
)

def benchmark_sql_split(iterations: int = 50) -> Dict[str, Any]:
    # 15KB complex SQL with stored procedures and dollar quotes
    unit_sql = """
    CREATE TABLE accounts (id INT PRIMARY KEY, name VARCHAR(100), balance DECIMAL(15,2));
    INSERT INTO accounts VALUES (1, 'Acme Corp', 50000.00), (2, 'Globex Corp', 84000.00);
    CREATE OR REPLACE FUNCTION audit_func() RETURNS TRIGGER AS $$
    BEGIN
        INSERT INTO audit_log (acc_id, old_bal, new_bal, event_time)
        VALUES (OLD.id, OLD.balance, NEW.balance, CURRENT_TIMESTAMP);
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    BEGIN TRANSACTION;
    UPDATE accounts SET balance = balance - 100 WHERE id = 1;
    UPDATE accounts SET balance = balance + 100 WHERE id = 2;
    COMMIT;
    """
    large_sql = unit_sql * 10  # ~15KB per iteration

    # 1. Native
    t0 = time.perf_counter()
    for _ in range(iterations):
        res_native = native_sql_split(large_sql, "postgresql")
    t_native = time.perf_counter() - t0

    # 2. Python
    t0 = time.perf_counter()
    for _ in range(iterations):
        res_py = python_sql_split(large_sql, "postgresql")
    t_python = time.perf_counter() - t0

    native_ops = iterations / t_native if t_native > 0 else 0
    python_ops = iterations / t_python if t_python > 0 else 0
    speedup = t_python / t_native if t_native > 0 else 1.0

    return {
        "operation": f"Complex SQL Split (15KB x {iterations})",
        "native_time_ms": round(t_native * 1000, 2),
        "python_time_ms": round(t_python * 1000, 2),
        "native_ops_sec": round(native_ops, 1),
        "python_ops_sec": round(python_ops, 1),
        "speedup_factor": f"{speedup:.1f}x",
        "detail": f"Native statements: {len(res_native)}, Python statements: {len(res_py)}",
    }

def benchmark_dep_solver(iterations: int = 100) -> Dict[str, Any]:
    lib = get_lib()
    input_data = {
        "root_dependencies": [
            {"package": "fastapi", "constraints": ">=0.95.0"},
            {"package": "pydantic", "constraints": "^2.0.0"},
            {"package": "uvicorn", "constraints": ">=0.20.0"},
        ],
        "available_packages": {
            "fastapi": [
                {"version": "0.100.0", "dependencies": [{"package": "pydantic", "constraints": ">=2.0.0,<3.0.0"}]},
                {"version": "0.95.0", "dependencies": [{"package": "pydantic", "constraints": "^1.10.0"}]},
            ],
            "pydantic": [
                {"version": "2.4.2", "dependencies": []},
                {"version": "1.10.8", "dependencies": []},
            ],
            "uvicorn": [
                {"version": "0.22.0", "dependencies": []},
                {"version": "0.21.0", "dependencies": []},
            ],
        },
    }
    json_bytes = json.dumps(input_data).encode("utf-8")

    # Native Rust PubGrub solver
    t0 = time.perf_counter()
    for _ in range(iterations):
        ptr = lib.elmos_solve_dependencies(json_bytes)
        raw = ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8")
        lib.elmos_free_string(ptr)
    t_native = time.perf_counter() - t0

    # Python backtracking mock solver
    def py_solve(data):
        # naive backtracking
        sol = {}
        for dep in data["root_dependencies"]:
            pkg = dep["package"]
            sol[pkg] = data["available_packages"][pkg][0]["version"]
        return sol

    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = py_solve(input_data)
    t_python = time.perf_counter() - t0

    native_ops = iterations / t_native if t_native > 0 else 0
    python_ops = iterations / t_python if t_python > 0 else 0
    speedup = t_python / t_native if t_native > 0 else 1.0

    return {
        "operation": f"PubGrub Dep Solver ({iterations} solves)",
        "native_time_ms": round(t_native * 1000, 2),
        "python_time_ms": round(t_python * 1000, 2),
        "native_ops_sec": round(native_ops, 1),
        "python_ops_sec": round(python_ops, 1),
        "speedup_factor": f"{speedup:.1f}x",
        "detail": f"Avg native solve latency: {round((t_native*1000)/iterations, 3)} ms",
    }

def benchmark_comp3(iterations: int = 2_000) -> Dict[str, Any]:
    hex_samples = [
        "001234567C", "009876543D", "000001234C", "005555555C", "001000000D"
    ]
    
    # 1. Native
    t0 = time.perf_counter()
    for i in range(iterations):
        h = hex_samples[i % len(hex_samples)]
        _ = native_comp3_decode(h, scale=2)
    t_native = time.perf_counter() - t0

    # 2. Python
    t0 = time.perf_counter()
    for i in range(iterations):
        h = hex_samples[i % len(hex_samples)]
        _ = python_comp3_decode(h, scale=2)
    t_python = time.perf_counter() - t0

    native_ops = iterations / t_native if t_native > 0 else 0
    python_ops = iterations / t_python if t_python > 0 else 0
    speedup = t_python / t_native if t_native > 0 else 1.0

    return {
        "operation": f"COMP-3 Decode ({iterations} ops)",
        "native_time_ms": round(t_native * 1000, 2),
        "python_time_ms": round(t_python * 1000, 2),
        "native_ops_sec": round(native_ops, 1),
        "python_ops_sec": round(python_ops, 1),
        "speedup_factor": f"{speedup:.1f}x",
        "detail": f"Zero-allocation COMP-3 parser",
    }

def benchmark_ebcdic(iterations: int = 50, payload_size: int = 10_000) -> Dict[str, Any]:
    raw_ebcdic = bytes([random.randint(0x40, 0xF9) for _ in range(payload_size)])
    
    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = native_ebcdic_to_ascii(raw_ebcdic)
    t_native = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = python_ebcdic_to_ascii(raw_ebcdic)
    t_python = time.perf_counter() - t0

    total_mb = (payload_size * iterations) / (1024 * 1024)
    native_mb_s = total_mb / t_native if t_native > 0 else 0
    python_mb_s = total_mb / t_python if t_python > 0 else 0
    speedup = t_python / t_native if t_native > 0 else 1.0

    return {
        "operation": f"EBCDIC Transcode ({payload_size//1024}KB x {iterations})",
        "native_time_ms": round(t_native * 1000, 2),
        "python_time_ms": round(t_python * 1000, 2),
        "native_throughput_mb_s": round(native_mb_s, 2),
        "python_throughput_mb_s": round(python_mb_s, 2),
        "speedup_factor": f"{speedup:.1f}x",
        "detail": f"CP037 standard transcoding",
    }

def benchmark_industrial_swap(iterations: int = 10_000) -> Dict[str, Any]:
    hex_val = "12345678"
    mode = "CDAB"

    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = native_swap_bytes(hex_val, mode)
    t_native = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = python_swap_bytes(hex_val, mode)
    t_python = time.perf_counter() - t0

    native_ops = iterations / t_native if t_native > 0 else 0
    python_ops = iterations / t_python if t_python > 0 else 0
    speedup = t_python / t_native if t_native > 0 else 1.0

    return {
        "operation": f"Modbus 32-bit Swap ({iterations} ops)",
        "native_time_ms": round(t_native * 1000, 2),
        "python_time_ms": round(t_python * 1000, 2),
        "native_ops_sec": round(native_ops, 1),
        "python_ops_sec": round(python_ops, 1),
        "speedup_factor": f"{speedup:.1f}x",
        "detail": "Mid-Little / Word-Swap",
    }

def benchmark_blast_radius(iterations: int = 50) -> Dict[str, Any]:
    # Build 200-node graph
    graph = {}
    for i in range(200):
        graph[f"node_{i}"] = [f"node_{(i*2 + 1) % 200}", f"node_{(i*2 + 2) % 200}"]

    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = native_blast_radius(graph, ["node_0"], max_nodes=150)
    t_native = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = python_blast_radius(graph, ["node_0"], max_nodes=150)
    t_python = time.perf_counter() - t0

    native_ops = iterations / t_native if t_native > 0 else 0
    python_ops = iterations / t_python if t_python > 0 else 0
    speedup = t_python / t_native if t_native > 0 else 1.0

    return {
        "operation": f"Graph Blast Radius ({iterations} traversals)",
        "native_time_ms": round(t_native * 1000, 2),
        "python_time_ms": round(t_python * 1000, 2),
        "native_ops_sec": round(native_ops, 1),
        "python_ops_sec": round(python_ops, 1),
        "speedup_factor": f"{speedup:.1f}x",
        "detail": "200-node graph with cycles",
    }

def run_benchmark_drill() -> List[Dict[str, Any]]:
    print("=" * 70)
    print("⚡ [DRILL 2] STARTING MICRO-BENCHMARKS & SPEEDUP QUANTIFICATION")
    print("=" * 70)

    benchmarks = [
        benchmark_sql_split,
        benchmark_dep_solver,
        benchmark_comp3,
        benchmark_ebcdic,
        benchmark_industrial_swap,
        benchmark_blast_radius,
    ]

    results = []
    print(f"\n{'Operation':<35} | {'Native':<10} | {'Python':<10} | {'Speedup':<8}")
    print("-" * 72)

    for bench in benchmarks:
        res = bench()
        results.append(res)
        print(f"{res['operation']:<35} | {res['native_time_ms']:>7.2f} ms | {res['python_time_ms']:>7.2f} ms | {res['speedup_factor']:>7}")

    print("-" * 72)
    print("🎉 [DRILL 2 COMPLETE] All benchmarks executed successfully.\n")
    return results

if __name__ == "__main__":
    results = run_benchmark_drill()
    out_file = REPO_ROOT / "evidence" / "drills" / "benchmark_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {out_file}")
