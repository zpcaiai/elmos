use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::panic::catch_unwind;

/// Free a C-string allocated by this library.
#[no_mangle]
pub unsafe extern "C" fn elmos_free_string(ptr: *mut c_char) {
    if !ptr.is_null() {
        drop(CString::from_raw(ptr));
    }
}

// -------------------------------------------------------------
// P0.1: SQL Statement Splitter
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_sql_split(
    sql_ptr: *const c_char,
    dialect_ptr: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if sql_ptr.is_null() {
            return CString::new("[]").unwrap();
        }
        let sql = match CStr::from_ptr(sql_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return CString::new("[]").unwrap(),
        };
        let dialect = if dialect_ptr.is_null() {
            None
        } else {
            CStr::from_ptr(dialect_ptr).to_str().ok()
        };

        let statements = elmos_sql_splitter::split_statements(sql, dialect);
        let json_str = serde_json::to_string(&statements).unwrap_or_else(|_| "[]".to_string());
        CString::new(json_str).unwrap_or_else(|_| CString::new("[]").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P0.2: Data Reconciler
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_reconcile_rows(input_json_ptr: *const c_char) -> *mut c_char {
    let result = catch_unwind(|| {
        if input_json_ptr.is_null() {
            return CString::new("{\"error\": \"null pointer\"}").unwrap();
        }
        let input_str = match CStr::from_ptr(input_json_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        let output_json = elmos_data_reconciler::reconcile_rows_json(input_str);
        CString::new(output_json).unwrap_or_else(|_| CString::new("{\"error\": \"failed to allocate\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P0.3: CST Parser
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_cst_parse(
    source_ptr: *const c_char,
    lang_ptr: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if source_ptr.is_null() {
            return CString::new("{\"error\": \"null source pointer\"}").unwrap();
        }
        let source = match CStr::from_ptr(source_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };
        let lang = if lang_ptr.is_null() {
            "generic"
        } else {
            CStr::from_ptr(lang_ptr).to_str().unwrap_or("generic")
        };

        let tree = elmos_cst_parser::parse_code_cst(source, lang);
        let json_str = serde_json::to_string(&tree).unwrap_or_else(|_| "{}".to_string());
        CString::new(json_str).unwrap_or_else(|_| CString::new("{\"error\": \"failed to allocate\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P0.4: Project Graph Scanner
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_scan_project_graph(
    root_path_ptr: *const c_char,
    max_files: usize,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if root_path_ptr.is_null() {
            return CString::new("{\"error\": \"null path pointer\"}").unwrap();
        }
        let root_path = match CStr::from_ptr(root_path_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        let graph = elmos_symbol_graph::scan_and_build_graph(root_path, max_files);
        let json_str = serde_json::to_string(&graph).unwrap_or_else(|_| "{}".to_string());
        CString::new(json_str).unwrap_or_else(|_| CString::new("{\"error\": \"failed to allocate\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P1.1: Dependency Solver (uv-architecture PubGrub algorithm)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_solve_dependencies(input_json_ptr: *const c_char) -> *mut c_char {
    let result = catch_unwind(|| {
        if input_json_ptr.is_null() {
            return CString::new("{\"status\": \"ERROR\", \"error\": \"null pointer\"}").unwrap();
        }
        let input_str = match CStr::from_ptr(input_json_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"status\": \"ERROR\", \"error\": \"{}\"}}", e)).unwrap(),
        };

        let output_json = elmos_dep_solver::solve_dependencies_json(input_str);
        CString::new(output_json).unwrap_or_else(|_| CString::new("{\"status\": \"ERROR\", \"error\": \"allocation error\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P1.2a: Bytecode Scanner (class file bytes)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_scan_bytecode_bytes(
    bytes_ptr: *const u8,
    len: usize,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if bytes_ptr.is_null() || len == 0 {
            return CString::new("{\"error\": \"empty or null bytes\"}").unwrap();
        }
        let slice = std::slice::from_raw_parts(bytes_ptr, len);
        let output_json = elmos_bytecode_scanner::scan_class_bytes_json(slice);
        CString::new(output_json).unwrap_or_else(|_| CString::new("{\"error\": \"allocation error\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P1.2b: Bytecode Scanner (directory walk)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_scan_bytecode_dir(dir_path_ptr: *const c_char) -> *mut c_char {
    let result = catch_unwind(|| {
        if dir_path_ptr.is_null() {
            return CString::new("{\"error\": \"null directory pointer\"}").unwrap();
        }
        let dir_str = match CStr::from_ptr(dir_path_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        let output_json = elmos_bytecode_scanner::scan_directory_json(dir_str);
        CString::new(output_json).unwrap_or_else(|_| CString::new("{\"error\": \"allocation error\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P1.2c: Shadow Traffic Diff Comparator
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_shadow_diff_compare(request_json_ptr: *const c_char) -> *mut c_char {
    let result = catch_unwind(|| {
        if request_json_ptr.is_null() {
            return CString::new("{\"error\": \"null request pointer\"}").unwrap();
        }
        let req_str = match CStr::from_ptr(request_json_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        let output_json = elmos_shadow_diff::compare_http_responses_json(req_str);
        CString::new(output_json).unwrap_or_else(|_| CString::new("{\"error\": \"allocation error\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

/// Free raw bytes allocated by this library.
#[no_mangle]
pub unsafe extern "C" fn elmos_free_bytes(ptr: *mut u8, len: usize) {
    if !ptr.is_null() && len > 0 {
        drop(Vec::from_raw_parts(ptr, len, len));
    }
}

// -------------------------------------------------------------
// P1+: Content Addressable Storage (CAS)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_cas_put_bytes(
    root_ptr: *const c_char,
    data_ptr: *const u8,
    data_len: usize,
    expected_ptr: *const c_char,
    kind_ptr: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if root_ptr.is_null() || data_ptr.is_null() {
            return CString::new("{\"error\": \"null pointer\"}").unwrap();
        }
        let root = match CStr::from_ptr(root_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };
        let expected = if expected_ptr.is_null() {
            None
        } else {
            CStr::from_ptr(expected_ptr).to_str().ok()
        };
        let kind = if kind_ptr.is_null() {
            None
        } else {
            CStr::from_ptr(kind_ptr).to_str().ok()
        };

        let data = std::slice::from_raw_parts(data_ptr, data_len);
        match elmos_cas_core::ContentAddressableStore::new(root, None, None) {
            Ok(cas) => match cas.put_bytes(data, expected, kind) {
                Ok(digest) => {
                    let json = serde_json::json!({"digest": digest});
                    CString::new(json.to_string()).unwrap()
                }
                Err(e) => {
                    let json = serde_json::json!({"error": e.to_string()});
                    CString::new(json.to_string()).unwrap()
                }
            },
            Err(e) => {
                let json = serde_json::json!({"error": e.to_string()});
                CString::new(json.to_string()).unwrap()
            }
        }
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn elmos_cas_get_bytes(
    root_ptr: *const c_char,
    digest_ptr: *const c_char,
    verify: i32,
    out_len: *mut usize,
) -> *mut u8 {
    let result = catch_unwind(|| {
        if root_ptr.is_null() || digest_ptr.is_null() || out_len.is_null() {
            return std::ptr::null_mut();
        }
        let root = match CStr::from_ptr(root_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return std::ptr::null_mut(),
        };
        let digest = match CStr::from_ptr(digest_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return std::ptr::null_mut(),
        };

        match elmos_cas_core::ContentAddressableStore::new(root, None, None) {
            Ok(cas) => match cas.get_bytes(digest, verify != 0) {
                Ok(data) => {
                    *out_len = data.len();
                    let mut mem = data.into_boxed_slice();
                    let ptr = mem.as_mut_ptr();
                    std::mem::forget(mem);
                    ptr
                }
                Err(_) => std::ptr::null_mut(),
            },
            Err(_) => std::ptr::null_mut(),
        }
    });

    match result {
        Ok(ptr) => ptr,
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn elmos_cas_contains(
    root_ptr: *const c_char,
    digest_ptr: *const c_char,
) -> i32 {
    let result = catch_unwind(|| {
        if root_ptr.is_null() || digest_ptr.is_null() {
            return 0;
        }
        let root = match CStr::from_ptr(root_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return 0,
        };
        let digest = match CStr::from_ptr(digest_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return 0,
        };

        if let Ok(cas) = elmos_cas_core::ContentAddressableStore::new(root, None, None) {
            if cas.contains(digest) {
                1
            } else {
                0
            }
        } else {
            0
        }
    });

    result.unwrap_or(0)
}

#[no_mangle]
pub unsafe extern "C" fn elmos_cas_is_quarantined(
    root_ptr: *const c_char,
    digest_ptr: *const c_char,
) -> i32 {
    let result = catch_unwind(|| {
        if root_ptr.is_null() || digest_ptr.is_null() {
            return 0;
        }
        let root = match CStr::from_ptr(root_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return 0,
        };
        let digest = match CStr::from_ptr(digest_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return 0,
        };

        if let Ok(cas) = elmos_cas_core::ContentAddressableStore::new(root, None, None) {
            if cas.is_quarantined(digest) {
                1
            } else {
                0
            }
        } else {
            0
        }
    });

    result.unwrap_or(0)
}

#[no_mangle]
pub unsafe extern "C" fn elmos_cas_quarantine(
    root_ptr: *const c_char,
    digest_ptr: *const c_char,
    reason_ptr: *const c_char,
) -> i32 {
    let result = catch_unwind(|| {
        if root_ptr.is_null() || digest_ptr.is_null() {
            return -1;
        }
        let root = match CStr::from_ptr(root_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return -1,
        };
        let digest = match CStr::from_ptr(digest_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return -1,
        };
        let reason = if reason_ptr.is_null() {
            "unspecified"
        } else {
            CStr::from_ptr(reason_ptr).to_str().unwrap_or("unspecified")
        };

        if let Ok(cas) = elmos_cas_core::ContentAddressableStore::new(root, None, None) {
            match cas.quarantine(digest, reason) {
                Ok(_) => 0,
                Err(_) => -1,
            }
        } else {
            -1
        }
    });

    result.unwrap_or(-1)
}

#[no_mangle]
pub unsafe extern "C" fn elmos_cas_info(
    root_ptr: *const c_char,
    digest_ptr: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if root_ptr.is_null() || digest_ptr.is_null() {
            return CString::new("{\"error\": \"null pointer\"}").unwrap();
        }
        let root = match CStr::from_ptr(root_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };
        let digest = match CStr::from_ptr(digest_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        match elmos_cas_core::ContentAddressableStore::new(root, None, None) {
            Ok(cas) => match cas.info(digest) {
                Ok(info) => {
                    let json = serde_json::to_string(&info).unwrap_or_else(|_| "{}".to_string());
                    CString::new(json).unwrap()
                }
                Err(e) => {
                    let json = serde_json::json!({"error": e.to_string()});
                    CString::new(json.to_string()).unwrap()
                }
            },
            Err(e) => {
                let json = serde_json::json!({"error": e.to_string()});
                CString::new(json.to_string()).unwrap()
            }
        }
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn elmos_cas_accounting(root_ptr: *const c_char) -> *mut c_char {
    let result = catch_unwind(|| {
        if root_ptr.is_null() {
            return CString::new("{\"error\": \"null pointer\"}").unwrap();
        }
        let root = match CStr::from_ptr(root_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        match elmos_cas_core::ContentAddressableStore::new(root, None, None) {
            Ok(cas) => match cas.accounting() {
                Ok(info) => {
                    let json = serde_json::to_string(&info).unwrap_or_else(|_| "{}".to_string());
                    CString::new(json).unwrap()
                }
                Err(e) => {
                    let json = serde_json::json!({"error": e.to_string()});
                    CString::new(json.to_string()).unwrap()
                }
            },
            Err(e) => {
                let json = serde_json::json!({"error": e.to_string()});
                CString::new(json.to_string()).unwrap()
            }
        }
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P2.1: Mutation Testing Engine
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_mutation_evaluate(source_ptr: *const c_char) -> *mut c_char {
    let result = catch_unwind(|| {
        if source_ptr.is_null() {
            return CString::new("{\"error\": \"null source pointer\"}").unwrap();
        }
        let source = match CStr::from_ptr(source_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        let report = elmos_mutation_core::MutationTestingEngine::evaluate_mutants(source);
        let json = serde_json::to_string(&report).unwrap_or_else(|_| "{}".to_string());
        CString::new(json).unwrap_or_else(|_| CString::new("{\"error\": \"allocation error\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P2.2: Java AST / CST Summary Extractor (j2p)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_j2p_parse_summary(source_ptr: *const c_char) -> *mut c_char {
    let result = catch_unwind(|| {
        if source_ptr.is_null() {
            return CString::new("{\"error\": \"null source pointer\"}").unwrap();
        }
        let source = match CStr::from_ptr(source_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        let summary = elmos_j2p_core::JavaAstExtractor::parse_summary(source);
        let json = serde_json::to_string(&summary).unwrap_or_else(|_| "{}".to_string());
        CString::new(json).unwrap_or_else(|_| CString::new("{\"error\": \"allocation error\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P2.3: Repository Snapshot Scanner (repo-scanner)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_snapshot_scan(
    root_ptr: *const c_char,
    max_files: u64,
    max_total_bytes: u64,
    max_file_bytes: u64,
    include_text: bool,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if root_ptr.is_null() {
            return CString::new("{\"ok\": false, \"error\": \"null root pointer\"}").unwrap();
        }
        let root = match CStr::from_ptr(root_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"ok\": false, \"error\": \"{}\"}}", e)).unwrap(),
        };

        let cfg = elmos_repo_scanner::ScannerConfig {
            max_files: if max_files == 0 { 50_000 } else { max_files as usize },
            max_total_bytes: if max_total_bytes == 0 { 512 * 1024 * 1024 } else { max_total_bytes },
            max_file_bytes: if max_file_bytes == 0 { 32 * 1024 * 1024 } else { max_file_bytes },
            exclusions: vec![
                ".git".to_string(),
                ".venv".to_string(),
                "node_modules".to_string(),
                "target".to_string(),
            ],
            include_text,
        };

        let scan_res = elmos_repo_scanner::scan_repository(root, &cfg);
        let json = serde_json::to_string(&scan_res).unwrap_or_else(|_| "{\"ok\": false}".to_string());
        CString::new(json).unwrap_or_else(|_| CString::new("{\"ok\": false, \"error\": \"alloc\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P3.1: Archive Safety & Merkle Guard (archive-guard)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_archive_inspect(
    path_ptr: *const c_char,
    max_entries: u64,
    max_uncompressed_bytes: u64,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if path_ptr.is_null() {
            return CString::new("{\"ok\": false, \"error\": \"null path pointer\"}").unwrap();
        }
        let path = match CStr::from_ptr(path_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"ok\": false, \"error\": \"{}\"}}", e)).unwrap(),
        };

        let limits = elmos_archive_guard::ArchiveLimits {
            max_entries: if max_entries == 0 { 50_000 } else { max_entries as usize },
            max_uncompressed_bytes: if max_uncompressed_bytes == 0 { 1024 * 1024 * 1024 } else { max_uncompressed_bytes },
            max_expansion_ratio: 100.0,
        };

        let inspect_res = elmos_archive_guard::inspect_archive(path, &limits);
        let json = serde_json::to_string(&inspect_res).unwrap_or_else(|_| "{\"ok\": false}".to_string());
        CString::new(json).unwrap_or_else(|_| CString::new("{\"ok\": false, \"error\": \"alloc\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P3.2: Foundry Skill Graph & Dependency Closure (foundry-graph)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_foundry_init_catalog(catalog_json_ptr: *const c_char) -> i32 {
    let result = catch_unwind(|| {
        if catalog_json_ptr.is_null() {
            return -1;
        }
        let json_str = match CStr::from_ptr(catalog_json_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return -2,
        };
        match elmos_foundry_graph::init_global_catalog(json_str) {
            Ok(count) => count as i32,
            Err(_) => -3,
        }
    });
    result.unwrap_or(-99)
}

#[no_mangle]
pub unsafe extern "C" fn elmos_foundry_resolve_dependencies(skill_name_ptr: *const c_char) -> *mut c_char {
    let result = catch_unwind(|| {
        if skill_name_ptr.is_null() {
            return CString::new("[]").unwrap();
        }
        let name = match CStr::from_ptr(skill_name_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return CString::new("[]").unwrap(),
        };

        let deps = elmos_foundry_graph::resolve_global_dependencies(name).unwrap_or_default();
        let json = serde_json::to_string(&deps).unwrap_or_else(|_| "[]".to_string());
        CString::new(json).unwrap_or_else(|_| CString::new("[]").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P3.3: API Contract Differ (contract-diff)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_contract_diff(
    source_json_ptr: *const c_char,
    target_json_ptr: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if source_json_ptr.is_null() || target_json_ptr.is_null() {
            return CString::new("{\"error\": \"null pointer\"}").unwrap();
        }
        let source_json = match CStr::from_ptr(source_json_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };
        let target_json = match CStr::from_ptr(target_json_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        match elmos_contract_diff::diff_specs_json(source_json, target_json) {
            Ok(report) => {
                let json = serde_json::to_string(&report).unwrap_or_else(|_| "{}".to_string());
                CString::new(json).unwrap_or_else(|_| CString::new("{\"error\": \"alloc\"}").unwrap())
            }
            Err(e) => CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        }
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P4.1: Architecture Blast Radius Graph Solver
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_blast_radius(
    changed_json_ptr: *const c_char,
    edges_json_ptr: *const c_char,
    max_nodes: u32,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if changed_json_ptr.is_null() || edges_json_ptr.is_null() {
            return CString::new("{\"error\": \"null pointer\"}").unwrap();
        }
        let changed_str = match CStr::from_ptr(changed_json_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };
        let edges_str = match CStr::from_ptr(edges_json_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        let output_json = elmos_blast_radius::compute_blast_radius_json(
            changed_str,
            edges_str,
            max_nodes as usize,
        );
        CString::new(output_json).unwrap_or_else(|_| CString::new("{\"error\": \"allocation error\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P4.2: Formal Attestation & Merkle Sealer
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_attestation_sign(
    payload_ptr: *const u8,
    payload_len: usize,
    secret_key_ptr: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if payload_ptr.is_null() || secret_key_ptr.is_null() {
            return CString::new("{\"error\": \"null pointer\"}").unwrap();
        }
        let payload_slice = std::slice::from_raw_parts(payload_ptr, payload_len);
        let secret_key = match CStr::from_ptr(secret_key_ptr).to_str() {
            Ok(s) => s,
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        let res = elmos_attestation_core::sign_attestation(payload_slice, secret_key);
        let json = serde_json::to_string(&res).unwrap_or_else(|_| "{}".to_string());
        CString::new(json).unwrap_or_else(|_| CString::new("{\"error\": \"allocation error\"}").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn elmos_merkle_root(digests_csv_ptr: *const c_char) -> *mut c_char {
    let result = catch_unwind(|| {
        if digests_csv_ptr.is_null() {
            return CString::new("").unwrap();
        }
        let csv_str = match CStr::from_ptr(digests_csv_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return CString::new("").unwrap(),
        };

        let leaves: Vec<String> = csv_str
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect();

        let root = elmos_attestation_core::merkle_root(&leaves);
        CString::new(root).unwrap_or_else(|_| CString::new("").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P5.1: Mainframe Core (EBCDIC & COMP-3 Packed Decimal)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_ebcdic_to_ascii(
    src_ptr: *const u8,
    len: usize,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if src_ptr.is_null() || len == 0 {
            return CString::new("").unwrap();
        }
        let slice = std::slice::from_raw_parts(src_ptr, len);
        let ascii_bytes = elmos_mainframe_core::ebcdic_to_ascii(slice);
        CString::new(ascii_bytes).unwrap_or_else(|_| CString::new("").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn elmos_comp3_decode(
    hex_ptr: *const c_char,
    scale: u32,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if hex_ptr.is_null() {
            return CString::new("{\"error\": \"null pointer\"}").unwrap();
        }
        let hex_str = match CStr::from_ptr(hex_ptr).to_str() {
            Ok(s) => s.trim(),
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        let bytes = match (0..hex_str.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex_str[i..i + 2], 16))
            .collect::<Result<Vec<u8>, _>>()
        {
            Ok(b) => b,
            Err(e) => return CString::new(format!("{{\"error\": \"hex decode: {}\"}}", e)).unwrap(),
        };

        match elmos_mainframe_core::decode_comp3(&bytes, scale) {
            Ok(val) => {
                let json = serde_json::json!({ "value": val, "scale": scale });
                CString::new(json.to_string()).unwrap()
            }
            Err(e) => {
                let json = serde_json::json!({ "error": e });
                CString::new(json.to_string()).unwrap()
            }
        }
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn elmos_comp3_encode(
    num_ptr: *const c_char,
    scale: u32,
    total_bytes: usize,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if num_ptr.is_null() {
            return CString::new("{\"error\": \"null pointer\"}").unwrap();
        }
        let num_str = match CStr::from_ptr(num_ptr).to_str() {
            Ok(s) => s.trim(),
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        match elmos_mainframe_core::encode_comp3(num_str, scale, total_bytes) {
            Ok(bytes) => {
                let hex_str = bytes.iter().map(|b| format!("{:02X}", b)).collect::<String>();
                let json = serde_json::json!({ "hex": hex_str, "bytes_length": bytes.len() });
                CString::new(json.to_string()).unwrap()
            }
            Err(e) => {
                let json = serde_json::json!({ "error": e });
                CString::new(json.to_string()).unwrap()
            }
        }
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P5.2: AI Vector Core (SIMD Cosine, Top-K, Token Sliding Window)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_vector_cosine(
    vec_a_ptr: *const f32,
    vec_b_ptr: *const f32,
    len: usize,
) -> f32 {
    let result = catch_unwind(|| {
        if vec_a_ptr.is_null() || vec_b_ptr.is_null() || len == 0 {
            return 0.0f32;
        }
        let a = std::slice::from_raw_parts(vec_a_ptr, len);
        let b = std::slice::from_raw_parts(vec_b_ptr, len);
        elmos_ai_vector_core::cosine_similarity(a, b)
    });

    result.unwrap_or(0.0f32)
}

#[no_mangle]
pub unsafe extern "C" fn elmos_vector_topk(
    query_ptr: *const f32,
    query_len: usize,
    candidates_json_ptr: *const c_char,
    k: usize,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if query_ptr.is_null() || candidates_json_ptr.is_null() || query_len == 0 {
            return CString::new("[]").unwrap();
        }
        let query = std::slice::from_raw_parts(query_ptr, query_len);
        let json_str = match CStr::from_ptr(candidates_json_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return CString::new("[]").unwrap(),
        };

        let candidates: Vec<elmos_ai_vector_core::VectorItem> = match serde_json::from_str(json_str) {
            Ok(c) => c,
            Err(_) => return CString::new("[]").unwrap(),
        };

        let topk = elmos_ai_vector_core::top_k_cosine(query, &candidates, k);
        let out_json = serde_json::to_string(&topk).unwrap_or_else(|_| "[]".to_string());
        CString::new(out_json).unwrap_or_else(|_| CString::new("[]").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn elmos_token_count_estimate(text_ptr: *const c_char) -> i32 {
    let result = catch_unwind(|| {
        if text_ptr.is_null() {
            return 0i32;
        }
        let text = match CStr::from_ptr(text_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return 0i32,
        };
        elmos_ai_vector_core::estimate_token_count(text) as i32
    });

    result.unwrap_or(0i32)
}

#[no_mangle]
pub unsafe extern "C" fn elmos_token_window_pack(
    text_ptr: *const c_char,
    max_tokens: usize,
    header_lines: usize,
    footer_lines: usize,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if text_ptr.is_null() {
            return CString::new("{\"text\":\"\",\"tokens\":0,\"truncated\":false}").unwrap();
        }
        let text = match CStr::from_ptr(text_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return CString::new("{\"text\":\"\",\"tokens\":0,\"truncated\":false}").unwrap(),
        };

        let (packed, tok, truncated) =
            elmos_ai_vector_core::sliding_window_pack(text, max_tokens, header_lines, footer_lines);

        let out = serde_json::json!({
            "text": packed,
            "tokens": tok,
            "truncated": truncated
        });
        CString::new(out.to_string()).unwrap()
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

// -------------------------------------------------------------
// P5.3: Industrial Core (Endianness & Modbus Register Decoding)
// -------------------------------------------------------------
#[no_mangle]
pub unsafe extern "C" fn elmos_industrial_swap_bytes(
    hex_ptr: *const c_char,
    endianness_ptr: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if hex_ptr.is_null() || endianness_ptr.is_null() {
            return CString::new("{\"error\": \"null pointer\"}").unwrap();
        }
        let hex_str = match CStr::from_ptr(hex_ptr).to_str() {
            Ok(s) => s.trim(),
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };
        let mode_str = match CStr::from_ptr(endianness_ptr).to_str() {
            Ok(s) => s.trim(),
            Err(e) => return CString::new(format!("{{\"error\": \"{}\"}}", e)).unwrap(),
        };

        let bytes = match (0..hex_str.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex_str[i..i + 2], 16))
            .collect::<Result<Vec<u8>, _>>()
        {
            Ok(b) if b.len() == 4 => [b[0], b[1], b[2], b[3]],
            _ => return CString::new("{\"error\": \"hex must be exactly 4 bytes (8 hex chars)\"}").unwrap(),
        };

        let mode = elmos_industrial_core::Endianness::from_str(mode_str);
        let swapped = elmos_industrial_core::swap_bytes_32(bytes, mode);
        let float_val = elmos_industrial_core::decode_float32(bytes, mode);
        let int_val = elmos_industrial_core::decode_int32(bytes, mode);

        let hex_out = swapped.iter().map(|b| format!("{:02X}", b)).collect::<String>();
        let json = serde_json::json!({
            "hex": hex_out,
            "float32": float_val,
            "int32": int_val,
            "mode": mode_str
        });
        CString::new(json.to_string()).unwrap()
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn elmos_industrial_decode_registers(
    registers_json_ptr: *const c_char,
    start_addr: u16,
    mappings_json_ptr: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(|| {
        if registers_json_ptr.is_null() || mappings_json_ptr.is_null() {
            return CString::new("[]").unwrap();
        }
        let reg_str = match CStr::from_ptr(registers_json_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return CString::new("[]").unwrap(),
        };
        let map_str = match CStr::from_ptr(mappings_json_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return CString::new("[]").unwrap(),
        };

        let registers: Vec<u16> = serde_json::from_str(reg_str).unwrap_or_default();
        let mappings: Vec<elmos_industrial_core::RegisterMapping> =
            serde_json::from_str(map_str).unwrap_or_default();

        let decoded = elmos_industrial_core::decode_modbus_block(&registers, start_addr, &mappings);
        let out_json = serde_json::to_string(&decoded).unwrap_or_else(|_| "[]".to_string());
        CString::new(out_json).unwrap_or_else(|_| CString::new("[]").unwrap())
    });

    match result {
        Ok(c_str) => c_str.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

