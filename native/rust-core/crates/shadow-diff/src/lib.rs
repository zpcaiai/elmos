use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, HashSet};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HttpResponse {
    pub status: u16,
    #[serde(default)]
    pub headers: BTreeMap<String, String>,
    #[serde(default)]
    pub body: String,
    #[serde(default)]
    pub latency_ms: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShadowDiffRequest {
    pub primary: HttpResponse,
    pub shadow: HttpResponse,
    #[serde(default)]
    pub ignored_headers: Vec<String>,
    #[serde(default)]
    pub ignored_body_fields: Vec<String>,
    #[serde(default)]
    pub float_tolerance: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HeaderMismatch {
    pub header_name: String,
    pub primary_value: Option<String>,
    pub shadow_value: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BodyMismatch {
    pub path: String,
    pub primary_value: Value,
    pub shadow_value: Value,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShadowDiffResult {
    pub is_match: bool,
    pub status_code_match: bool,
    pub primary_status: u16,
    pub shadow_status: u16,
    pub header_mismatches: Vec<HeaderMismatch>,
    pub body_mismatches: Vec<BodyMismatch>,
    pub latency_delta_ms: f64,
    pub summary: String,
}

const DEFAULT_IGNORED_HEADERS: &[&str] = &[
    "date",
    "x-request-id",
    "x-trace-id",
    "server",
    "keep-alive",
    "transfer-encoding",
    "content-length",
    "age",
    "etag",
    "set-cookie",
    "x-envoy-upstream-service-time",
];

const DEFAULT_IGNORED_FIELDS: &[&str] = &[
    "timestamp",
    "time",
    "traceid",
    "requestid",
    "spanid",
    "duration",
    "executiontimems",
];

pub fn compare_responses(req: &ShadowDiffRequest) -> ShadowDiffResult {
    let status_code_match = req.primary.status == req.shadow.status;

    // 1. Header comparison
    let mut ignored_hdr_set: HashSet<String> = DEFAULT_IGNORED_HEADERS
        .iter()
        .map(|s| s.to_ascii_lowercase())
        .collect();
    for h in &req.ignored_headers {
        ignored_hdr_set.insert(h.to_ascii_lowercase());
    }

    let mut header_mismatches = Vec::new();
    let norm_primary_headers = normalize_headers(&req.primary.headers, &ignored_hdr_set);
    let norm_shadow_headers = normalize_headers(&req.shadow.headers, &ignored_hdr_set);

    let mut all_hdr_keys: BTreeMap<String, ()> = BTreeMap::new();
    for k in norm_primary_headers.keys() {
        all_hdr_keys.insert(k.clone(), ());
    }
    for k in norm_shadow_headers.keys() {
        all_hdr_keys.insert(k.clone(), ());
    }

    for k in all_hdr_keys.keys() {
        let p_val = norm_primary_headers.get(k);
        let s_val = norm_shadow_headers.get(k);
        if p_val != s_val {
            header_mismatches.push(HeaderMismatch {
                header_name: k.clone(),
                primary_value: p_val.cloned(),
                shadow_value: s_val.cloned(),
            });
        }
    }

    // 2. Body comparison
    let mut ignored_fields: HashSet<String> = DEFAULT_IGNORED_FIELDS
        .iter()
        .map(|s| s.to_ascii_lowercase())
        .collect();
    for f in &req.ignored_body_fields {
        ignored_fields.insert(f.to_ascii_lowercase());
    }

    let tolerance = req.float_tolerance.unwrap_or(1e-6);
    let mut body_mismatches = Vec::new();

    // Try parsing both as JSON
    let p_json: Result<Value, _> = serde_json::from_str(&req.primary.body);
    let s_json: Result<Value, _> = serde_json::from_str(&req.shadow.body);

    match (p_json, s_json) {
        (Ok(p_val), Ok(s_val)) => {
            compare_json_values(
                "$",
                &p_val,
                &s_val,
                &ignored_fields,
                tolerance,
                &mut body_mismatches,
            );
        }
        _ => {
            // Raw text comparison
            if req.primary.body.trim() != req.shadow.body.trim() {
                body_mismatches.push(BodyMismatch {
                    path: "$".to_string(),
                    primary_value: Value::String(req.primary.body.clone()),
                    shadow_value: Value::String(req.shadow.body.clone()),
                    reason: "Text content differs".to_string(),
                });
            }
        }
    }

    let is_match = status_code_match && header_mismatches.is_empty() && body_mismatches.is_empty();
    let latency_delta_ms = req.shadow.latency_ms - req.primary.latency_ms;

    let summary = if is_match {
        format!(
            "IDENTICAL: Status={}, LatencyDelta={:.2}ms",
            req.primary.status, latency_delta_ms
        )
    } else {
        format!(
            "DIFF_DETECTED: StatusMatch={}, HeaderDiffs={}, BodyDiffs={}",
            status_code_match,
            header_mismatches.len(),
            body_mismatches.len()
        )
    };

    ShadowDiffResult {
        is_match,
        status_code_match,
        primary_status: req.primary.status,
        shadow_status: req.shadow.status,
        header_mismatches,
        body_mismatches,
        latency_delta_ms,
        summary,
    }
}

fn normalize_headers(
    headers: &BTreeMap<String, String>,
    ignored: &HashSet<String>,
) -> BTreeMap<String, String> {
    let mut map = BTreeMap::new();
    for (k, v) in headers {
        let lower = k.to_ascii_lowercase();
        if !ignored.contains(&lower) {
            map.insert(lower, v.trim().to_string());
        }
    }
    map
}

fn compare_json_values(
    path: &str,
    p: &Value,
    s: &Value,
    ignored_fields: &HashSet<String>,
    tolerance: f64,
    mismatches: &mut Vec<BodyMismatch>,
) {
    match (p, s) {
        (Value::Object(p_obj), Value::Object(s_obj)) => {
            let mut all_keys: BTreeMap<&str, ()> = BTreeMap::new();
            for k in p_obj.keys() {
                all_keys.insert(k.as_str(), ());
            }
            for k in s_obj.keys() {
                all_keys.insert(k.as_str(), ());
            }

            for key in all_keys.keys() {
                let lower_key = key.to_ascii_lowercase();
                if ignored_fields.contains(&lower_key) {
                    continue;
                }

                let sub_path = format!("{}.{}", path, key);
                match (p_obj.get(*key), s_obj.get(*key)) {
                    (Some(p_child), Some(s_child)) => {
                        compare_json_values(
                            &sub_path,
                            p_child,
                            s_child,
                            ignored_fields,
                            tolerance,
                            mismatches,
                        );
                    }
                    (Some(p_child), None) => {
                        mismatches.push(BodyMismatch {
                            path: sub_path,
                            primary_value: p_child.clone(),
                            shadow_value: Value::Null,
                            reason: "Field missing in shadow response".to_string(),
                        });
                    }
                    (None, Some(s_child)) => {
                        mismatches.push(BodyMismatch {
                            path: sub_path,
                            primary_value: Value::Null,
                            shadow_value: s_child.clone(),
                            reason: "Field unexpected in shadow response".to_string(),
                        });
                    }
                    (None, None) => {}
                }
            }
        }
        (Value::Array(p_arr), Value::Array(s_arr)) => {
            if p_arr.len() != s_arr.len() {
                mismatches.push(BodyMismatch {
                    path: path.to_string(),
                    primary_value: Value::from(p_arr.len() as u64),
                    shadow_value: Value::from(s_arr.len() as u64),
                    reason: format!(
                        "Array length mismatch: primary={}, shadow={}",
                        p_arr.len(),
                        s_arr.len()
                    ),
                });
                return;
            }
            for (idx, (p_item, s_item)) in p_arr.iter().zip(s_arr.iter()).enumerate() {
                let sub_path = format!("{}[{}]", path, idx);
                compare_json_values(
                    &sub_path,
                    p_item,
                    s_item,
                    ignored_fields,
                    tolerance,
                    mismatches,
                );
            }
        }
        (Value::Number(p_num), Value::Number(s_num)) => {
            if let (Some(p_f), Some(s_f)) = (p_num.as_f64(), s_num.as_f64()) {
                if (p_f - s_f).abs() > tolerance {
                    mismatches.push(BodyMismatch {
                        path: path.to_string(),
                        primary_value: p.clone(),
                        shadow_value: s.clone(),
                        reason: format!("Numeric difference exceeds tolerance {}", tolerance),
                    });
                }
            } else if p_num != s_num {
                mismatches.push(BodyMismatch {
                    path: path.to_string(),
                    primary_value: p.clone(),
                    shadow_value: s.clone(),
                    reason: "Integer value mismatch".to_string(),
                });
            }
        }
        (Value::String(p_s), Value::String(s_s)) => {
            if p_s != s_s {
                mismatches.push(BodyMismatch {
                    path: path.to_string(),
                    primary_value: p.clone(),
                    shadow_value: s.clone(),
                    reason: "String value mismatch".to_string(),
                });
            }
        }
        (Value::Bool(p_b), Value::Bool(s_b)) => {
            if p_b != s_b {
                mismatches.push(BodyMismatch {
                    path: path.to_string(),
                    primary_value: p.clone(),
                    shadow_value: s.clone(),
                    reason: "Boolean value mismatch".to_string(),
                });
            }
        }
        (Value::Null, Value::Null) => {}
        _ => {
            mismatches.push(BodyMismatch {
                path: path.to_string(),
                primary_value: p.clone(),
                shadow_value: s.clone(),
                reason: "Type mismatch".to_string(),
            });
        }
    }
}

pub fn compare_http_responses_json(payload_json: &str) -> String {
    let req: ShadowDiffRequest = match serde_json::from_str(payload_json) {
        Ok(r) => r,
        Err(e) => {
            let err_obj = serde_json::json!({
                "error": format!("Invalid JSON request: {}", e)
            });
            return err_obj.to_string();
        }
    };
    let result = compare_responses(&req);
    serde_json::to_string(&result).unwrap_or_else(|_| "{}".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_identical_json_responses_with_ignored_fields() {
        let mut p_headers = BTreeMap::new();
        p_headers.insert("content-type".to_string(), "application/json".to_string());
        p_headers.insert("x-request-id".to_string(), "req-111".to_string());

        let mut s_headers = BTreeMap::new();
        s_headers.insert("content-type".to_string(), "application/json".to_string());
        s_headers.insert("x-request-id".to_string(), "req-222".to_string());

        let p_body = r#"{"id": 42, "name": "Order #42", "timestamp": "2026-09-04T00:00:00Z"}"#;
        let s_body = r#"{"name": "Order #42", "id": 42, "timestamp": "2026-09-04T00:00:01Z"}"#;

        let req = ShadowDiffRequest {
            primary: HttpResponse {
                status: 200,
                headers: p_headers,
                body: p_body.to_string(),
                latency_ms: 12.5,
            },
            shadow: HttpResponse {
                status: 200,
                headers: s_headers,
                body: s_body.to_string(),
                latency_ms: 10.2,
            },
            ignored_headers: vec![],
            ignored_body_fields: vec![],
            float_tolerance: None,
        };

        let diff = compare_responses(&req);
        assert!(diff.is_match);
        assert!(diff.header_mismatches.is_empty());
        assert!(diff.body_mismatches.is_empty());
    }

    #[test]
    fn test_detected_body_difference() {
        let req = ShadowDiffRequest {
            primary: HttpResponse {
                status: 200,
                headers: BTreeMap::new(),
                body: r#"{"status": "OK", "code": 0}"#.to_string(),
                latency_ms: 5.0,
            },
            shadow: HttpResponse {
                status: 200,
                headers: BTreeMap::new(),
                body: r#"{"status": "ERROR", "code": 1}"#.to_string(),
                latency_ms: 5.0,
            },
            ignored_headers: vec![],
            ignored_body_fields: vec![],
            float_tolerance: None,
        };

        let diff = compare_responses(&req);
        assert!(!diff.is_match);
        assert_eq!(diff.body_mismatches.len(), 2);
    }
}
