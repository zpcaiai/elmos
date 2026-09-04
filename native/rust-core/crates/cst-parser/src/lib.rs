use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AstSpan {
    pub start_row: usize,
    pub start_col: usize,
    pub end_row: usize,
    pub end_col: usize,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct IncrementalAstNode {
    pub id: String,
    pub node_type: String,
    pub span: AstSpan,
    pub text_snippet: String,
    pub is_modified: bool,
    pub digest: String,
    pub children: Vec<IncrementalAstNode>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct IncrementalAstTree {
    pub root: Option<IncrementalAstNode>,
    pub total_nodes: usize,
    pub language: String,
    pub tree_digest: Option<String>,
    pub parse_duration_ms: f64,
    pub status: String,
    pub source_digest: Option<String>,
    pub provider: Option<String>,
    pub reason: Option<String>,
}

pub fn simple_sha256(data: &[u8]) -> String {
    // Re-use standard sha256 or basic hasher
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

pub fn parse_code_cst(source: &str, lang: &str) -> IncrementalAstTree {
    let start_time = std::time::Instant::now();
    let src_digest = simple_sha256(source.as_bytes());

    let lines: Vec<&str> = source.lines().collect();
    let total_lines = lines.len();
    let last_col = lines.last().map(|l| l.len()).unwrap_or(0);

    let mut children = Vec::new();
    let mut node_count = 1;

    for (row_idx, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if !trimmed.is_empty() {
            let node_digest = simple_sha256(trimmed.as_bytes());
            children.push(IncrementalAstNode {
                id: format!("node_{}", node_count),
                node_type: "statement".to_string(),
                span: AstSpan {
                    start_row: row_idx,
                    start_col: line.find(trimmed).unwrap_or(0),
                    end_row: row_idx,
                    end_col: line.len(),
                },
                text_snippet: if trimmed.len() > 64 {
                    format!("{}...", &trimmed[..60])
                } else {
                    trimmed.to_string()
                },
                is_modified: false,
                digest: node_digest,
                children: Vec::new(),
            });
            node_count += 1;
        }
    }

    let root_node = IncrementalAstNode {
        id: "node_0".to_string(),
        node_type: "module".to_string(),
        span: AstSpan {
            start_row: 0,
            start_col: 0,
            end_row: total_lines.saturating_sub(1),
            end_col: last_col,
        },
        text_snippet: if source.len() > 64 {
            format!("{}...", &source[..60])
        } else {
            source.to_string()
        },
        is_modified: false,
        digest: src_digest.clone(),
        children,
    };

    let elapsed = start_time.elapsed().as_secs_f64() * 1000.0;

    IncrementalAstTree {
        root: Some(root_node),
        total_nodes: node_count,
        language: lang.to_string(),
        tree_digest: Some(src_digest.clone()),
        parse_duration_ms: elapsed,
        status: "LOCAL_EXECUTED".to_string(),
        source_digest: Some(src_digest),
        provider: Some("native-rust-cst".to_string()),
        reason: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cst_parse_basic() {
        let code = "def hello():\n    print('world')\n";
        let tree = parse_code_cst(code, "python");
        assert_eq!(tree.language, "python");
        assert_eq!(tree.status, "LOCAL_EXECUTED");
        assert!(tree.total_nodes >= 2);
    }
}
