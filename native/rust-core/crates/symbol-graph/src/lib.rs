use std::collections::{BTreeSet, HashMap};
use std::path::Path;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProjectNode {
    pub relative_path: String,
    pub sha256: String,
    pub size_bytes: u64,
    pub role: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProjectEdge {
    pub source: String,
    pub target: String,
    pub kind: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProjectGraphResult {
    pub root: String,
    pub total_files: usize,
    pub total_bytes: u64,
    pub nodes: Vec<ProjectNode>,
    pub edges: Vec<ProjectEdge>,
    pub topological_order: Vec<String>,
    pub has_cycles: bool,
    pub repository_digest: String,
}

pub fn simple_sha256(data: &[u8]) -> String {
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

fn classify_role(path: &str) -> &'static str {
    let lower = path.to_ascii_lowercase();
    if lower.contains("test") || lower.ends_with("_test.py") || lower.ends_with(".test.ts") {
        "test"
    } else if lower.ends_with("pom.xml") || lower.ends_with("cargo.toml") || lower.ends_with("package.json") || lower.ends_with("pyproject.toml") {
        "build-descriptor"
    } else if lower.ends_with(".py") || lower.ends_with(".rs") || lower.ends_with(".java") || lower.ends_with(".ts") || lower.ends_with(".go") {
        "source"
    } else {
        "resource"
    }
}

pub fn scan_and_build_graph(root_path: &str, max_files: usize) -> Result<ProjectGraphResult, String> {
    let root = Path::new(root_path);
    if !root.exists() {
        return Err(format!("path does not exist: {}", root_path));
    }

    let mut nodes = Vec::new();
    let mut total_bytes = 0u64;

    fn visit_dirs(
        dir: &Path,
        root: &Path,
        nodes: &mut Vec<ProjectNode>,
        total_bytes: &mut u64,
        max_files: usize,
    ) -> Result<(), String> {
        if nodes.len() >= max_files {
            return Ok(());
        }
        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                let file_name = entry.file_name().to_string_lossy().to_string();
                if file_name.starts_with('.') || file_name == "node_modules" || file_name == "target" || file_name == "__pycache__" || file_name == "vendor" {
                    continue;
                }
                if path.is_dir() {
                    visit_dirs(&path, root, nodes, total_bytes, max_files)?;
                } else if path.is_file() {
                    if let Ok(meta) = entry.metadata() {
                        let size = meta.len();
                        *total_bytes += size;
                        let rel = path.strip_prefix(root).unwrap_or(&path).to_string_lossy().to_string();
                        let role = classify_role(&rel).to_string();
                        let content = std::fs::read(&path).unwrap_or_default();
                        let sha = simple_sha256(&content);
                        nodes.push(ProjectNode {
                            relative_path: rel,
                            sha256: sha,
                            size_bytes: size,
                            role,
                        });
                    }
                }
            }
        }
        Ok(())
    }

    visit_dirs(root, root, &mut nodes, &mut total_bytes, max_files)?;
    nodes.sort_by(|a, b| a.relative_path.cmp(&b.relative_path));

    let mut edges = Vec::new();
    let node_paths: BTreeSet<String> = nodes.iter().map(|n| n.relative_path.clone()).collect();

    // Naive import edge synthesis for test/source relations
    for node in &nodes {
        if node.role == "test" {
            let src_candidate = node.relative_path.replace("tests/test_", "src/").replace("_test.py", ".py");
            if node_paths.contains(&src_candidate) {
                edges.push(ProjectEdge {
                    source: node.relative_path.clone(),
                    target: src_candidate,
                    kind: "test".to_string(),
                });
            }
        }
    }

    // Topological sort & cycle detection (Kahn's algorithm)
    let mut in_degree: HashMap<String, usize> = HashMap::new();
    let mut adj: HashMap<String, Vec<String>> = HashMap::new();
    for p in &node_paths {
        in_degree.insert(p.clone(), 0);
        adj.insert(p.clone(), Vec::new());
    }
    for e in &edges {
        if in_degree.contains_key(&e.target) {
            *in_degree.get_mut(&e.target).unwrap() += 1;
            adj.get_mut(&e.source).unwrap().push(e.target.clone());
        }
    }

    let mut queue: std::collections::VecDeque<String> = in_degree
        .iter()
        .filter(|(_, &deg)| deg == 0)
        .map(|(k, _)| k.clone())
        .collect();

    let mut topo_order = Vec::new();
    while let Some(u) = queue.pop_front() {
        topo_order.push(u.clone());
        if let Some(neighbors) = adj.get(&u) {
            for v in neighbors {
                let deg = in_degree.get_mut(v).unwrap();
                *deg -= 1;
                if *deg == 0 {
                    queue.push_back(v.clone());
                }
            }
        }
    }

    let has_cycles = topo_order.len() < node_paths.len();

    let mut repo_summary = Vec::new();
    for n in &nodes {
        repo_summary.push(format!("{}:{}", n.relative_path, n.sha256));
    }
    let repository_digest = simple_sha256(repo_summary.join("\n").as_bytes());

    Ok(ProjectGraphResult {
        root: root_path.to_string(),
        total_files: nodes.len(),
        total_bytes,
        nodes,
        edges,
        topological_order: topo_order,
        has_cycles,
        repository_digest,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_scan_graph() {
        let res = scan_and_build_graph(".", 100).unwrap();
        assert!(res.total_files > 0);
    }
}
