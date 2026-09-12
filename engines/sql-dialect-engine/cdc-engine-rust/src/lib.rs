use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};

/// Normalize a single JSON value into a deterministic canonical string.
pub fn normalize_value(val: &Value) -> String {
    match val {
        Value::Null => "§NULL§".to_string(),
        Value::Bool(b) => if *b { "true".to_string() } else { "false".to_string() },
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i.to_string()
            } else if let Some(u) = n.as_u64() {
                u.to_string()
            } else if let Some(f) = n.as_f64() {
                // Remove trailing decimal zeroes from floats if integer equivalent
                if f.fract() == 0.0 {
                    format!("{:.0}", f)
                } else {
                    format!("{}", f)
                }
            } else {
                n.to_string()
            }
        }
        Value::String(s) => s.clone(),
        Value::Array(_) | Value::Object(_) => {
            // Canonical sorted representation for nested json
            val.to_string()
        }
    }
}

/// Normalize an entire row object into a deterministic canonical string.
pub fn normalize_row(row: &Value) -> String {
    if let Value::Object(map) = row {
        let mut keys: Vec<&String> = map.keys().collect();
        keys.sort();
        let parts: Vec<String> = keys
            .into_iter()
            .map(|k| format!("{}={}", k, normalize_value(&map[k])))
            .collect();
        parts.join("§")
    } else {
        normalize_value(row)
    }
}

/// Compute SHA-256 hex string over UTF-8 bytes.
pub fn sha256_hex(input: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    hex::encode(hasher.finalize())
}

/// Compute aggregated SHA-256 digest for a chunk of rows.
pub fn hash_chunk(rows: &[Value]) -> String {
    if rows.is_empty() {
        return sha256_hex("§EMPTY§");
    }
    let row_hashes: Vec<String> = rows
        .par_iter()
        .map(|r| sha256_hex(&normalize_row(r)))
        .collect();

    let combined = row_hashes.join("\n");
    sha256_hex(&combined)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChunkDiffResult {
    pub start_pk: Value,
    pub end_pk: Value,
    pub matched: bool,
    pub source_row_count: usize,
    pub target_row_count: usize,
    pub source_hash: String,
    pub target_hash: String,
    pub mismatched_pks: Vec<Value>,
}

/// Parallel diff of source vs target row sets in a chunk.
pub fn compare_chunks(
    source_rows: &[Value],
    target_rows: &[Value],
    pk_col: &str,
) -> ChunkDiffResult {
    let source_hash = hash_chunk(source_rows);
    let target_hash = hash_chunk(target_rows);

    let start_pk = source_rows
        .first()
        .and_then(|r| r.get(pk_col))
        .or_else(|| target_rows.first().and_then(|r| r.get(pk_col)))
        .cloned()
        .unwrap_or(Value::Null);

    let end_pk = source_rows
        .last()
        .and_then(|r| r.get(pk_col))
        .or_else(|| target_rows.last().and_then(|r| r.get(pk_col)))
        .cloned()
        .unwrap_or(Value::Null);

    if source_hash == target_hash {
        return ChunkDiffResult {
            start_pk,
            end_pk,
            matched: true,
            source_row_count: source_rows.len(),
            target_row_count: target_rows.len(),
            source_hash,
            target_hash,
            mismatched_pks: vec![],
        };
    }

    // Build PK index for granular diff
    let mut src_map: HashMap<String, (&Value, String)> = HashMap::new();
    for r in source_rows {
        if let Some(pk) = r.get(pk_col) {
            src_map.insert(pk.to_string(), (pk, normalize_row(r)));
        }
    }

    let mut tgt_map: HashMap<String, (&Value, String)> = HashMap::new();
    for r in target_rows {
        if let Some(pk) = r.get(pk_col) {
            tgt_map.insert(pk.to_string(), (pk, normalize_row(r)));
        }
    }

    let all_keys: HashSet<String> = src_map.keys().chain(tgt_map.keys()).cloned().collect();
    let mut mismatched_pks: Vec<Value> = Vec::new();

    for key in all_keys {
        match (src_map.get(&key), tgt_map.get(&key)) {
            (Some((pk, s_norm)), Some((_, t_norm))) => {
                if s_norm != t_norm {
                    mismatched_pks.push((*pk).clone());
                }
            }
            (Some((pk, _)), None) => {
                mismatched_pks.push((*pk).clone());
            }
            (None, Some((pk, _))) => {
                mismatched_pks.push((*pk).clone());
            }
            (None, None) => {}
        }
    }

    ChunkDiffResult {
        start_pk,
        end_pk,
        matched: false,
        source_row_count: source_rows.len(),
        target_row_count: target_rows.len(),
        source_hash,
        target_hash,
        mismatched_pks,
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventAnomaly {
    pub anomaly_type: String,
    pub event_id: String,
    pub lsn: i64,
    pub details: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventStreamResult {
    pub total_events: usize,
    pub inserts: usize,
    pub updates: usize,
    pub deletes: usize,
    pub out_of_order_count: usize,
    pub duplicate_count: usize,
    pub state_consistent: bool,
    pub mismatched_pks: Vec<Value>,
    pub anomalies: Vec<EventAnomaly>,
}

/// Replay incremental CDC event stream onto baseline state and verify target state.
pub fn compare_event_stream(
    events: &[Value],
    initial_state: &[Value],
    final_target_state: &[Value],
    pk_col: &str,
) -> EventStreamResult {
    let mut current_state: HashMap<String, (Value, Value)> = HashMap::new();
    for r in initial_state {
        if let Some(pk) = r.get(pk_col) {
            current_state.insert(pk.to_string(), (pk.clone(), r.clone()));
        }
    }

    let mut seen_ids = HashSet::new();
    let mut highest_lsn = -1i64;
    let mut anomalies = Vec::new();
    let mut out_of_order_count = 0;
    let mut duplicate_count = 0;
    let mut inserts = 0;
    let mut updates = 0;
    let mut deletes = 0;

    for ev in events {
        let ev_id = ev
            .get("eventId")
            .or_else(|| ev.get("event_id"))
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let lsn = ev.get("lsn").and_then(|v| v.as_i64()).unwrap_or(0);
        let op = ev.get("op").and_then(|v| v.as_str()).unwrap_or("");
        let pk = ev
            .get("primaryKey")
            .or_else(|| ev.get("primary_key"))
            .cloned()
            .unwrap_or(Value::Null);

        match op {
            "INSERT" => inserts += 1,
            "UPDATE" => updates += 1,
            "DELETE" => deletes += 1,
            _ => {}
        }

        if seen_ids.contains(ev_id) {
            duplicate_count += 1;
            anomalies.push(EventAnomaly {
                anomaly_type: "DUPLICATE_EVENT".to_string(),
                event_id: ev_id.to_string(),
                lsn,
                details: format!("Event ID {} occurred multiple times", ev_id),
            });
        } else {
            seen_ids.insert(ev_id.to_string());
        }

        if lsn <= highest_lsn {
            out_of_order_count += 1;
            anomalies.push(EventAnomaly {
                anomaly_type: "OUT_OF_ORDER".to_string(),
                event_id: ev_id.to_string(),
                lsn,
                details: format!("LSN {} out of order after {}", lsn, highest_lsn),
            });
        } else {
            highest_lsn = lsn;
        }

        let pk_str = pk.to_string();
        if op == "INSERT" || op == "UPDATE" {
            if let Some(after) = ev.get("after") {
                current_state.insert(pk_str, (pk, after.clone()));
            }
        } else if op == "DELETE" {
            current_state.remove(&pk_str);
        }
    }

    let mut target_state: HashMap<String, (Value, Value)> = HashMap::new();
    for r in final_target_state {
        if let Some(pk) = r.get(pk_col) {
            target_state.insert(pk.to_string(), (pk.clone(), r.clone()));
        }
    }

    let (state_consistent, mismatched_pks) = if final_target_state.is_empty() {
        (out_of_order_count == 0 && duplicate_count == 0, Vec::new())
    } else {
        let mut mismatches = Vec::new();
        let all_keys: HashSet<String> = current_state.keys().chain(target_state.keys()).cloned().collect();

        for k in all_keys {
            match (current_state.get(&k), target_state.get(&k)) {
                (Some((pk, s_val)), Some((_, t_val))) => {
                    if normalize_row(s_val) != normalize_row(t_val) {
                        mismatches.push(pk.clone());
                    }
                }
                (Some((pk, _)), None) => mismatches.push(pk.clone()),
                (None, Some((pk, _))) => mismatches.push(pk.clone()),
                (None, None) => {}
            }
        }
        (mismatches.is_empty(), mismatches)
    };

    EventStreamResult {
        total_events: events.len(),
        inserts,
        updates,
        deletes,
        out_of_order_count,
        duplicate_count,
        state_consistent,
        mismatched_pks,
        anomalies,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_row_normalization() {
        let r1 = json!({"id": 1, "name": "Alice", "amount": 100.5});
        let r2 = json!({"amount": 100.5, "name": "Alice", "id": 1});
        assert_eq!(normalize_row(&r1), normalize_row(&r2));
        assert_eq!(normalize_row(&r1), "amount=100.5§id=1§name=Alice");
    }

    #[test]
    fn test_chunk_hashing_identical() {
        let chunk1 = vec![
            json!({"id": 1, "val": "A"}),
            json!({"id": 2, "val": "B"}),
        ];
        let chunk2 = vec![
            json!({"val": "A", "id": 1}),
            json!({"val": "B", "id": 2}),
        ];
        assert_eq!(hash_chunk(&chunk1), hash_chunk(&chunk2));
    }

    #[test]
    fn test_compare_chunks_difference() {
        let s = vec![
            json!({"id": 1, "val": "A"}),
            json!({"id": 2, "val": "B"}),
        ];
        let t = vec![
            json!({"id": 1, "val": "A"}),
            json!({"id": 2, "val": "C"}), // divergence
        ];
        let diff = compare_chunks(&s, &t, "id");
        assert!(!diff.matched);
        assert_eq!(diff.mismatched_pks, vec![json!(2)]);
    }

    #[test]
    fn test_event_stream_replay() {
        let initial = vec![json!({"id": 1, "status": "PENDING"})];
        let events = vec![
            json!({
                "eventId": "e1",
                "lsn": 100,
                "op": "UPDATE",
                "primaryKey": 1,
                "after": {"id": 1, "status": "COMPLETED"}
            }),
            json!({
                "eventId": "e2",
                "lsn": 101,
                "op": "INSERT",
                "primaryKey": 2,
                "after": {"id": 2, "status": "NEW"}
            }),
        ];
        let target = vec![
            json!({"id": 1, "status": "COMPLETED"}),
            json!({"id": 2, "status": "NEW"}),
        ];
        let res = compare_event_stream(&events, &initial, &target, "id");
        assert!(res.state_consistent);
        assert_eq!(res.out_of_order_count, 0);
        assert_eq!(res.inserts, 1);
        assert_eq!(res.updates, 1);
    }
}
