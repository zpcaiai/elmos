"""Tests for Expanded Enterprise Standard Library Shims and Native ASan Sanitizers."""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines" / "polyglot-route-engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_polyglot_route.ast_compiler.shims import (
    ShimRegistry,
    get_collection_type,
    list_add,
    list_size,
    list_contains,
    list_clear,
    map_get,
    map_put,
    map_contains_key,
    map_remove,
    set_add,
    set_contains,
    string_length,
    string_trim,
    string_contains,
    string_starts_with,
    string_ends_with,
    string_replace,
    string_to_lower,
    string_to_upper,
    string_split,
    string_join,
    json_serialize,
    json_deserialize,
    log_info,
    log_error,
    file_read_text,
    file_write_text,
    file_exists,
    path_combine,
    http_get,
    now_iso,
    epoch_millis,
    sleep_millis,
    math_abs,
    math_min,
    math_max,
    math_sqrt,
    uuid_v4,
    sha256_hex,
)
from elmos_polyglot_route.ast_compiler.fuzzing.sanitizers import (
    NativeSanitizerRunner,
    SanitizerType,
)


ALL_LANGS = ("java", "csharp", "go", "rust", "python", "typescript", "cpp", "swift", "objc", "kotlin", "php")


def test_collections_shim_types_and_operations():
    """Verify list, map, set types and operations across all 11 target languages."""
    for lang in ALL_LANGS:
        # Collection types
        l_type = get_collection_type("list_type", lang, "Order", "Order")
        m_type = get_collection_type("map_type", lang, "string", "Order")
        s_type = get_collection_type("set_type", lang, "string", "string")
        assert len(l_type) > 0, f"Empty list type for {lang}"
        assert len(m_type) > 0, f"Empty map type for {lang}"
        assert len(s_type) > 0, f"Empty set type for {lang}"

        # List operations
        add_expr = list_add("orders", "newOrder", lang)
        size_expr = list_size("orders", lang)
        contains_expr = list_contains("orders", "newOrder", lang)
        clear_expr = list_clear("orders", lang)
        assert "orders" in add_expr
        assert "orders" in size_expr
        assert "orders" in contains_expr
        assert "orders" in clear_expr

        # Map operations
        get_expr = map_get("orderMap", "orderId", lang)
        put_expr = map_put("orderMap", "orderId", "newOrder", lang)
        has_expr = map_contains_key("orderMap", "orderId", lang)
        rem_expr = map_remove("orderMap", "orderId", lang)
        assert "orderMap" in get_expr
        assert "orderMap" in put_expr
        assert "orderMap" in has_expr
        assert "orderMap" in rem_expr

        # Set operations
        s_add = set_add("orderSet", "orderId", lang)
        s_has = set_contains("orderSet", "orderId", lang)
        assert "orderSet" in s_add
        assert "orderSet" in s_has


def test_strings_shim_operations():
    """Verify string standard library operations across all 11 languages."""
    for lang in ALL_LANGS:
        len_expr = string_length("customerName", lang)
        trim_expr = string_trim("customerName", lang)
        contains_expr = string_contains("customerName", '"Corp"', lang)
        starts_expr = string_starts_with("customerName", '"Acme"', lang)
        ends_expr = string_ends_with("customerName", '"Inc"', lang)
        replace_expr = string_replace("customerName", '"old"', '"new"', lang)
        lower_expr = string_to_lower("customerName", lang)
        upper_expr = string_to_upper("customerName", lang)
        split_expr = string_split("customerName", '","', lang)
        join_expr = string_join('","', "nameList", lang)

        assert "customerName" in len_expr
        assert "customerName" in trim_expr
        assert "customerName" in contains_expr
        assert "customerName" in starts_expr
        assert "customerName" in ends_expr
        assert "customerName" in replace_expr
        assert "customerName" in lower_expr
        assert "customerName" in upper_expr
        assert "customerName" in split_expr
        assert "nameList" in join_expr


def test_json_shim_serialization_and_deserialization():
    """Verify JSON serialization and deserialization across all 11 languages."""
    for lang in ALL_LANGS:
        ser_expr = json_serialize("orderRecord", lang)
        deser_expr = json_deserialize("jsonPayload", "OrderRecord", lang)
        assert len(ser_expr) > 0
        assert len(deser_expr) > 0
        assert "orderRecord" in ser_expr
        assert "jsonPayload" in deser_expr


def test_io_and_filesystem_shims():
    """Verify I/O, File, Path, and HTTP client standard library shims."""
    for lang in ALL_LANGS:
        log_i = log_info(lang, '"order processed"')
        log_e = log_error(lang, '"order failed"')
        f_read = file_read_text('"/etc/config.json"', lang)
        f_write = file_write_text('"/tmp/out.txt"', '"payload"', lang)
        f_exist = file_exists('"/tmp/lock"', lang)
        p_comb = path_combine('"baseDir"', '"subDir"', lang)
        http_g = http_get('"https://api.enterprise.com/orders"', lang)

        assert len(log_i) > 0
        assert len(log_e) > 0
        assert len(f_read) > 0
        assert len(f_write) > 0
        assert len(f_exist) > 0
        assert len(p_comb) > 0
        assert len(http_g) > 0


def test_datetime_and_clock_shims():
    """Verify ISO timestamps, epoch milliseconds, and sleep across all languages."""
    for lang in ALL_LANGS:
        iso = now_iso(lang)
        epoch = epoch_millis(lang)
        sleep = sleep_millis("500", lang)
        assert len(iso) > 0
        assert len(epoch) > 0
        assert "500" in sleep


def test_math_crypto_and_uuid_shims():
    """Verify math, UUID, and SHA-256 hash shims."""
    for lang in ALL_LANGS:
        m_abs = math_abs("delta", lang)
        m_min = math_min("x", "y", lang)
        m_max = math_max("x", "y", lang)
        m_sqrt = math_sqrt("variance", lang)
        u_v4 = uuid_v4(lang)
        h_sha = sha256_hex("rawBuffer", lang)

        assert "delta" in m_abs
        assert "x" in m_min and "y" in m_min
        assert "x" in m_max and "y" in m_max
        assert "variance" in m_sqrt
        assert len(u_v4) > 0
        assert "rawBuffer" in h_sha


def test_native_sanitizer_runner_cpp_asan():
    """Verify NativeSanitizerRunner compiles and runs C++20 under AddressSanitizer."""
    runner = NativeSanitizerRunner()
    clean_cpp = '''
    #include <iostream>
    #include <vector>
    int main() {
        std::vector<int> v = {10, 20, 30};
        int sum = 0;
        for (int x : v) sum += x;
        if (sum != 60) return 1;
        std::cout << "OK" << std::endl;
        return 0;
    }
    '''
    res = runner.run_cpp_sanitizer(clean_cpp, SanitizerType.ASAN)
    assert res.passed is True, f"C++ ASan failed: {res.stderr}"
    assert res.exit_code == 0


def test_native_sanitizer_runner_rust_and_go():
    """Verify NativeSanitizerRunner on Rust and Go."""
    runner = NativeSanitizerRunner()
    clean_rust = '''
    fn main() {
        let mut v = vec![1, 2, 3];
        v.push(4);
        assert_eq!(v.len(), 4);
    }
    '''
    r_res = runner.run_rust_sanitizer(clean_rust)
    assert r_res.passed is True, f"Rust sanitizer failed: {r_res.stderr}"

    clean_go = '''
    package main
    import "sync"
    func main() {
        var mu sync.Mutex
        val := 0
        mu.Lock()
        val += 1
        mu.Unlock()
        _ = val
    }
    '''
    g_res = runner.run_go_race_sanitizer(clean_go)
    assert g_res.passed is True, f"Go race detector failed: {g_res.stderr}"
