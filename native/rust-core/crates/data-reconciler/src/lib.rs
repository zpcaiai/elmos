use std::collections::{BTreeMap, BTreeSet, HashMap};
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub mod sha256 {
    pub fn digest(data: &[u8]) -> String {
        let mut h: [u32; 8] = [
            0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
            0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
        ];
        let k: [u32; 64] = [
            0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
            0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
            0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
            0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
            0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
            0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
            0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
            0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
        ];

        let mut msg = data.to_vec();
        let bit_len = (data.len() as u64) * 8;
        msg.push(0x80);
        while (msg.len() % 64) != 56 {
            msg.push(0);
        }
        msg.extend_from_slice(&bit_len.to_be_bytes());

        for chunk in msg.chunks(64) {
            let mut w = [0u32; 64];
            for (i, part) in chunk.chunks(4).enumerate() {
                w[i] = u32::from_be_bytes(part.try_into().unwrap());
            }
            for i in 16..64 {
                let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
                let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
                w[i] = w[i - 16].wrapping_add(s0).wrapping_add(w[i - 7]).wrapping_add(s1);
            }

            let mut a = h[0];
            let mut b = h[1];
            let mut c = h[2];
            let mut d = h[3];
            let mut e = h[4];
            let mut f = h[5];
            let mut g = h[6];
            let mut h_val = h[7];

            for i in 0..64 {
                let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
                let ch = (e & f) ^ ((!e) & g);
                let temp1 = h_val.wrapping_add(s1).wrapping_add(ch).wrapping_add(k[i]).wrapping_add(w[i]);
                let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
                let maj = (a & b) ^ (a & c) ^ (b & c);
                let temp2 = s0.wrapping_add(maj);

                h_val = g;
                g = f;
                f = e;
                e = d.wrapping_add(temp1);
                d = c;
                c = b;
                b = a;
                a = temp1.wrapping_add(temp2);
            }

            h[0] = h[0].wrapping_add(a);
            h[1] = h[1].wrapping_add(b);
            h[2] = h[2].wrapping_add(c);
            h[3] = h[3].wrapping_add(d);
            h[4] = h[4].wrapping_add(e);
            h[5] = h[5].wrapping_add(f);
            h[6] = h[6].wrapping_add(g);
            h[7] = h[7].wrapping_add(h_val);
        }

        let mut hex = String::with_capacity(64);
        for val in h {
            hex.push_str(&format!("{:08x}", val));
        }
        hex
    }
}

pub fn digest_object(domain: &str, value: &Value) -> String {
    let canonical_json = to_canonical_json(value);
    let payload = format!("{}:{}", domain, canonical_json);
    sha256::digest(payload.as_bytes())
}

pub fn to_canonical_json(val: &Value) -> String {
    match val {
        Value::Null => "null".to_string(),
        Value::Bool(b) => if *b { "true".to_string() } else { "false".to_string() },
        Value::Number(n) => n.to_string(),
        Value::String(s) => serde_json::to_string(s).unwrap(),
        Value::Array(arr) => {
            let items: Vec<String> = arr.iter().map(to_canonical_json).collect();
            format!("[{}]", items.join(","))
        }
        Value::Object(map) => {
            let mut sorted: Vec<(&String, &Value)> = map.iter().collect();
            sorted.sort_by_key(|(k, _)| *k);
            let entries: Vec<String> = sorted
                .iter()
                .map(|(k, v)| format!("{}:{}", serde_json::to_string(k).unwrap(), to_canonical_json(v)))
                .collect();
            format!("{{{}}}", entries.join(","))
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReconciliationResult {
    pub source_count: usize,
    pub target_count: usize,
    pub missing_row_digests: Vec<String>,
    pub unexpected_row_digests: Vec<String>,
    pub missing_key_digests: Vec<String>,
    pub unexpected_key_digests: Vec<String>,
    pub mismatched_key_digests: Vec<String>,
    pub duplicate_key_rows: DuplicateSummary,
    pub aggregate_deltas: BTreeMap<String, String>,
    pub equivalent: bool,
    pub reconciliation_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DuplicateSummary {
    pub source: usize,
    pub target: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExactDecimal {
    pub unscaled: i128,
    pub scale: u32,
}

impl ExactDecimal {
    pub fn parse(s: &str) -> Result<Self, String> {
        let trimmed = s.trim();
        if trimmed.is_empty() {
            return Err("empty decimal".to_string());
        }
        let parts: Vec<&str> = trimmed.split('.').collect();
        if parts.len() == 1 {
            let unscaled: i128 = parts[0].parse().map_err(|e| format!("{:?}", e))?;
            Ok(ExactDecimal { unscaled, scale: 0 })
        } else if parts.len() == 2 {
            let int_part = parts[0];
            let frac_part = parts[1];
            let scale = frac_part.len() as u32;
            let combined = format!("{}{}", int_part, frac_part);
            let unscaled: i128 = combined.parse().map_err(|e| format!("{:?}", e))?;
            Ok(ExactDecimal { unscaled, scale })
        } else {
            Err("invalid decimal".to_string())
        }
    }

    pub fn zero() -> Self {
        ExactDecimal { unscaled: 0, scale: 0 }
    }

    pub fn add(&self, other: &Self) -> Self {
        let max_scale = self.scale.max(other.scale);
        let s_val = self.unscaled * 10i128.pow(max_scale - self.scale);
        let o_val = other.unscaled * 10i128.pow(max_scale - other.scale);
        ExactDecimal {
            unscaled: s_val + o_val,
            scale: max_scale,
        }
    }

    pub fn sub(&self, other: &Self) -> Self {
        let max_scale = self.scale.max(other.scale);
        let s_val = self.unscaled * 10i128.pow(max_scale - self.scale);
        let o_val = other.unscaled * 10i128.pow(max_scale - other.scale);
        ExactDecimal {
            unscaled: s_val - o_val,
            scale: max_scale,
        }
    }

    pub fn to_string_repr(&self) -> String {
        if self.unscaled == 0 {
            return "0".to_string();
        }
        if self.scale == 0 {
            return self.unscaled.to_string();
        }
        let is_neg = self.unscaled < 0;
        let abs_val = self.unscaled.abs();
        let s = format!("{:0width$}", abs_val, width = (self.scale as usize) + 1);
        let split_idx = s.len() - (self.scale as usize);
        let int_part = &s[..split_idx];
        let frac_part = s[split_idx..].trim_end_matches('0');
        let prefix = if is_neg { "-" } else { "" };
        if frac_part.is_empty() {
            format!("{}{}", prefix, int_part)
        } else {
            format!("{}{}.{}", prefix, int_part, frac_part)
        }
    }
}

pub fn reconcile_rows(
    source_rows: &[Value],
    target_rows: &[Value],
    key_fields: &[String],
    decimal_fields: &[String],
) -> Result<ReconciliationResult, String> {
    if key_fields.is_empty() {
        return Err("key_fields must not be empty".to_string());
    }

    let analyze = |rows: &[Value], label: &str| -> Result<(HashMap<String, usize>, HashMap<String, usize>, HashMap<String, HashMap<String, usize>>, BTreeMap<String, ExactDecimal>), String> {
        let mut row_counter: HashMap<String, usize> = HashMap::new();
        let mut key_counter: HashMap<String, usize> = HashMap::new();
        let mut keyed_rows: HashMap<String, HashMap<String, usize>> = HashMap::new();
        let mut aggregates: BTreeMap<String, ExactDecimal> = BTreeMap::new();
        for dec in decimal_fields {
            aggregates.insert(dec.clone(), ExactDecimal::zero());
        }

        for (idx, row) in rows.iter().enumerate() {
            let map = row.as_object().ok_or_else(|| format!("{}[{}] is not an object", label, idx))?;
            for k in key_fields {
                if !map.contains_key(k) {
                    return Err(format!("{}[{}] lacks required key field {}", label, idx, k));
                }
            }
            for d in decimal_fields {
                if !map.contains_key(d) {
                    return Err(format!("{}[{}] lacks required decimal field {}", label, idx, d));
                }
            }

            let mut key_obj = serde_json::Map::new();
            for k in key_fields {
                key_obj.insert(k.clone(), map.get(k).unwrap().clone());
            }
            let key_digest = digest_object("local-reconciliation-key", &Value::Object(key_obj));
            let row_digest = digest_object("local-reconciliation-row", row);

            *key_counter.entry(key_digest.clone()).or_insert(0) += 1;
            *row_counter.entry(row_digest.clone()).or_insert(0) += 1;
            *keyed_rows.entry(key_digest).or_default().entry(row_digest).or_insert(0) += 1;

            for d in decimal_fields {
                let dec_str = match map.get(d).unwrap() {
                    Value::String(s) => s.clone(),
                    Value::Number(n) => n.to_string(),
                    _ => return Err(format!("{}[{}].{} is not decimal-compatible", label, idx, d)),
                };
                let parsed = ExactDecimal::parse(&dec_str)?;
                let curr = aggregates.get(d).unwrap();
                aggregates.insert(d.clone(), curr.add(&parsed));
            }
        }
        Ok((row_counter, key_counter, keyed_rows, aggregates))
    };

    let (source_counter, source_keys, source_keyed_rows, source_aggs) = analyze(source_rows, "source_rows")?;
    let (target_counter, target_keys, target_keyed_rows, target_aggs) = analyze(target_rows, "target_rows")?;

    let mut missing_row_digests = Vec::new();
    for (row, &src_count) in &source_counter {
        let tgt_count = target_counter.get(row).copied().unwrap_or(0);
        if src_count > tgt_count {
            for _ in 0..(src_count - tgt_count) {
                missing_row_digests.push(row.clone());
            }
        }
    }
    missing_row_digests.sort();

    let mut unexpected_row_digests = Vec::new();
    for (row, &tgt_count) in &target_counter {
        let src_count = source_counter.get(row).copied().unwrap_or(0);
        if tgt_count > src_count {
            for _ in 0..(tgt_count - src_count) {
                unexpected_row_digests.push(row.clone());
            }
        }
    }
    unexpected_row_digests.sort();

    let mut missing_key_digests = Vec::new();
    for (k, &src_count) in &source_keys {
        let tgt_count = target_keys.get(k).copied().unwrap_or(0);
        if src_count > tgt_count {
            for _ in 0..(src_count - tgt_count) {
                missing_key_digests.push(k.clone());
            }
        }
    }
    missing_key_digests.sort();

    let mut unexpected_key_digests = Vec::new();
    for (k, &tgt_count) in &target_keys {
        let src_count = source_keys.get(k).copied().unwrap_or(0);
        if tgt_count > src_count {
            for _ in 0..(tgt_count - src_count) {
                unexpected_key_digests.push(k.clone());
            }
        }
    }
    unexpected_key_digests.sort();

    let all_keys: BTreeSet<&String> = source_keyed_rows.keys().chain(target_keyed_rows.keys()).collect();
    let mut mismatched_key_digests = Vec::new();
    for k in all_keys {
        let empty_map = HashMap::new();
        let src_map = source_keyed_rows.get(k).unwrap_or(&empty_map);
        let tgt_map = target_keyed_rows.get(k).unwrap_or(&empty_map);
        if src_map != tgt_map {
            mismatched_key_digests.push(k.clone());
        }
    }
    mismatched_key_digests.sort();

    let mut aggregate_deltas = BTreeMap::new();
    for d in decimal_fields {
        let s_val = source_aggs.get(d).unwrap();
        let t_val = target_aggs.get(d).unwrap();
        let delta = t_val.sub(s_val);
        aggregate_deltas.insert(d.clone(), delta.to_string_repr());
    }

    let dup_source = source_keys.values().filter(|&&c| c > 1).map(|&c| c - 1).sum();
    let dup_target = target_keys.values().filter(|&&c| c > 1).map(|&c| c - 1).sum();

    let equivalent = missing_row_digests.is_empty()
        && unexpected_row_digests.is_empty()
        && aggregate_deltas.values().all(|v| v == "0");

    let digest_map = serde_json::json!({
        "missing": missing_row_digests,
        "unexpected": unexpected_row_digests,
        "missing_keys": missing_key_digests,
        "unexpected_keys": unexpected_key_digests,
        "mismatched_keys": mismatched_key_digests,
        "duplicates": { "source": dup_source, "target": dup_target },
        "aggregate_deltas": aggregate_deltas,
    });
    let reconciliation_digest = digest_object("local-reconciliation-run", &digest_map);

    Ok(ReconciliationResult {
        source_count: source_rows.len(),
        target_count: target_rows.len(),
        missing_row_digests,
        unexpected_row_digests,
        missing_key_digests,
        unexpected_key_digests,
        mismatched_key_digests,
        duplicate_key_rows: DuplicateSummary {
            source: dup_source,
            target: dup_target,
        },
        aggregate_deltas,
        equivalent,
        reconciliation_digest,
    })
}

#[derive(Debug, Deserialize)]
struct ReconcileInput {
    source_rows: Vec<Value>,
    target_rows: Vec<Value>,
    key_fields: Vec<String>,
    #[serde(default)]
    decimal_fields: Vec<String>,
}

pub fn reconcile_rows_json(input_json: &str) -> String {
    let input: ReconcileInput = match serde_json::from_str(input_json) {
        Ok(inp) => inp,
        Err(e) => {
            return serde_json::json!({
                "error": format!("Invalid JSON input: {}", e)
            }).to_string();
        }
    };

    match reconcile_rows(&input.source_rows, &input.target_rows, &input.key_fields, &input.decimal_fields) {
        Ok(res) => serde_json::to_string(&res).unwrap_or_else(|_| "{}".to_string()),
        Err(e) => serde_json::json!({"error": e}).to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_reconciliation_exact() {
        let rows = vec![
            json!({"id": 1, "amount": "100.50"}),
            json!({"id": 2, "amount": "200.25"}),
        ];
        let res = reconcile_rows(&rows, &rows, &["id".to_string()], &["amount".to_string()]).unwrap();
        assert!(res.equivalent);
        assert_eq!(res.source_count, 2);
        assert_eq!(res.target_count, 2);
        assert_eq!(res.aggregate_deltas.get("amount").unwrap(), "0");
    }

    #[test]
    fn test_reconciliation_mismatch() {
        let s_rows = vec![json!({"id": 1, "amount": "100.50"})];
        let t_rows = vec![json!({"id": 1, "amount": "100.75"})];
        let res = reconcile_rows(&s_rows, &t_rows, &["id".to_string()], &["amount".to_string()]).unwrap();
        assert!(!res.equivalent);
        assert_eq!(res.mismatched_key_digests.len(), 1);
        assert_eq!(res.aggregate_deltas.get("amount").unwrap(), "0.25");
    }
}
