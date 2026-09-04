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

