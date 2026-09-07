use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::Read;
use std::path::Path;

use serde::{Deserialize, Serialize};

// Streaming SHA-256 (RFC 6234)
#[derive(Clone)]
pub struct Sha256 {
    state: [u32; 8],
    count: u64,
    buffer: [u8; 64],
}

impl Sha256 {
    pub fn new() -> Self {
        Self {
            state: [
                0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
            ],
            count: 0,
            buffer: [0u8; 64],
        }
    }

    pub fn update(&mut self, data: &[u8]) {
        let mut input = data;
        let buffer_len = (self.count % 64) as usize;
        self.count += input.len() as u64;

        if buffer_len > 0 {
            let needed = 64 - buffer_len;
            if input.len() >= needed {
                self.buffer[buffer_len..64].copy_from_slice(&input[..needed]);
                let block = self.buffer;
                self.process_block(&block);
                input = &input[needed..];
            } else {
                self.buffer[buffer_len..buffer_len + input.len()].copy_from_slice(input);
                return;
            }
        }

        while input.len() >= 64 {
            let mut block = [0u8; 64];
            block.copy_from_slice(&input[..64]);
            self.process_block(&block);
            input = &input[64..];
        }

        if !input.is_empty() {
            self.buffer[..input.len()].copy_from_slice(input);
        }
    }

    pub fn finalize(mut self) -> [u8; 32] {
        let bit_len = self.count * 8;
        let mut pad = [0u8; 128];
        pad[0] = 0x80;
        let buffer_len = (self.count % 64) as usize;
        let pad_len = if buffer_len < 56 {
            56 - buffer_len
        } else {
            120 - buffer_len
        };
        self.update(&pad[..pad_len]);
        let len_bytes = bit_len.to_be_bytes();
        self.update(&len_bytes);

        let mut out = [0u8; 32];
        for (i, val) in self.state.iter().enumerate() {
            out[i * 4..(i + 1) * 4].copy_from_slice(&val.to_be_bytes());
        }
        out
    }

    pub fn digest(data: &[u8]) -> [u8; 32] {
        let mut h = Self::new();
        h.update(data);
        h.finalize()
    }

    pub fn digest_hex(data: &[u8]) -> String {
        let d = Self::digest(data);
        let mut s = String::with_capacity(64);
        for b in d {
            s.push_str(&format!("{:02x}", b));
        }
        s
    }

    fn process_block(&mut self, block: &[u8; 64]) {
        const K: [u32; 64] = [
            0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
            0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
            0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
            0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
            0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
            0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
            0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
            0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
        ];

        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([
                block[i * 4], block[i * 4 + 1], block[i * 4 + 2], block[i * 4 + 3],
            ]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16].wrapping_add(s0).wrapping_add(w[i - 7]).wrapping_add(s1);
        }

        let mut a = self.state[0];
        let mut b = self.state[1];
        let mut c = self.state[2];
        let mut d = self.state[3];
        let mut e = self.state[4];
        let mut f = self.state[5];
        let mut g = self.state[6];
        let mut h = self.state[7];

        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let temp1 = h.wrapping_add(s1).wrapping_add(ch).wrapping_add(K[i]).wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(maj);

            h = g;
            g = f;
            f = e;
            e = d.wrapping_add(temp1);
            d = c;
            c = b;
            b = a;
            a = temp1.wrapping_add(temp2);
        }

        self.state[0] = self.state[0].wrapping_add(a);
        self.state[1] = self.state[1].wrapping_add(b);
        self.state[2] = self.state[2].wrapping_add(c);
        self.state[3] = self.state[3].wrapping_add(d);
        self.state[4] = self.state[4].wrapping_add(e);
        self.state[5] = self.state[5].wrapping_add(f);
        self.state[6] = self.state[6].wrapping_add(g);
        self.state[7] = self.state[7].wrapping_add(h);
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecretFingerprint {
    pub kind: String,
    pub fingerprint: String,
    pub occurrences: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScannedEntry {
    pub path: String,
    pub kind: String, // "file" | "symlink"
    pub size_bytes: u64,
    pub sha256: String,
    pub secret_fingerprints: Vec<SecretFingerprint>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanResult {
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    pub file_count: usize,
    pub symlink_count: usize,
    pub total_bytes: u64,
    pub snapshot_digest: String,
    pub entries: Vec<ScannedEntry>,
}

pub struct ScannerConfig {
    pub max_files: usize,
    pub max_total_bytes: u64,
    pub max_file_bytes: u64,
    pub exclusions: Vec<String>,
    pub include_text: bool,
}

impl Default for ScannerConfig {
    fn default() -> Self {
        Self {
            max_files: 50_000,
            max_total_bytes: 512 * 1024 * 1024,
            max_file_bytes: 32 * 1024 * 1024,
            exclusions: vec![
                ".git".to_string(),
                ".venv".to_string(),
                "node_modules".to_string(),
                "target".to_string(),
            ],
            include_text: false,
        }
    }
}

pub fn scan_repository<P: AsRef<Path>>(root: P, config: &ScannerConfig) -> ScanResult {
    let root_path = root.as_ref();
    if !root_path.is_dir() {
        return ScanResult {
            ok: false,
            error: Some("repository root must be a directory".to_string()),
            file_count: 0,
            symlink_count: 0,
            total_bytes: 0,
            snapshot_digest: "".to_string(),
            entries: Vec::new(),
        };
    }

    let mut entries = Vec::new();
    let mut total_bytes = 0u64;
    let mut file_count = 0usize;
    let mut symlink_count = 0usize;

    let mut dirs_to_visit = vec![root_path.to_path_buf()];

    while let Some(current_dir) = dirs_to_visit.pop() {
        let read_dir = match fs::read_dir(&current_dir) {
            Ok(rd) => rd,
            Err(e) => {
                return ScanResult {
                    ok: false,
                    error: Some(format!("failed to read directory {}: {}", current_dir.display(), e)),
                    file_count,
                    symlink_count,
                    total_bytes,
                    snapshot_digest: "".to_string(),
                    entries,
                };
            }
        };

        for dir_entry in read_dir {
            let entry = match dir_entry {
                Ok(e) => e,
                Err(_) => continue,
            };

            let path = entry.path();
            let file_type = match entry.file_type() {
                Ok(ft) => ft,
                Err(_) => continue,
            };

            let rel_path = match path.strip_prefix(root_path) {
                Ok(p) => p.to_string_lossy().replace('\\', "/"),
                Err(_) => continue,
            };

            // Check exclusions
            if is_excluded(&rel_path, &config.exclusions) {
                continue;
            }

            if file_type.is_dir() {
                dirs_to_visit.push(path);
            } else if file_type.is_symlink() {
                symlink_count += 1;
                let target = fs::read_link(&path).ok().map(|p| p.to_string_lossy().to_string());
                entries.push(ScannedEntry {
                    path: rel_path,
                    kind: "symlink".to_string(),
                    size_bytes: 0,
                    sha256: "sha256:".to_string() + &"0".repeat(64),
                    secret_fingerprints: Vec::new(),
                    text: None,
                    target_path: target,
                });
            } else if file_type.is_file() {
                file_count += 1;
                if file_count > config.max_files {
                    return ScanResult {
                        ok: false,
                        error: Some("file limit exceeded".to_string()),
                        file_count,
                        symlink_count,
                        total_bytes,
                        snapshot_digest: "".to_string(),
                        entries,
                    };
                }

                let meta = match entry.metadata() {
                    Ok(m) => m,
                    Err(_) => continue,
                };
                let size = meta.len();
                if size > config.max_file_bytes {
                    return ScanResult {
                        ok: false,
                        error: Some(format!("file size limit exceeded: {} > {}", size, config.max_file_bytes)),
                        file_count,
                        symlink_count,
                        total_bytes,
                        snapshot_digest: "".to_string(),
                        entries,
                    };
                }

                total_bytes += size;
                if total_bytes > config.max_total_bytes {
                    return ScanResult {
                        ok: false,
                        error: Some("total repository byte limit exceeded".to_string()),
                        file_count,
                        symlink_count,
                        total_bytes,
                        snapshot_digest: "".to_string(),
                        entries,
                    };
                }

                // Read file bytes
                let mut data = Vec::with_capacity(size as usize);
                if let Ok(mut f) = File::open(&path) {
                    let _ = f.read_to_end(&mut data);
                }

                let sha = "sha256:".to_string() + &Sha256::digest_hex(&data);
                let secrets = scan_secrets(&data);

                let text = if config.include_text {
                    if memchr::memchr(0, &data).is_none() {
                        String::from_utf8(data).ok()
                    } else {
                        None
                    }
                } else {
                    None
                };

                entries.push(ScannedEntry {
                    path: rel_path,
                    kind: "file".to_string(),
                    size_bytes: size,
                    sha256: sha,
                    secret_fingerprints: secrets,
                    text,
                    target_path: None,
                });
            }
        }
    }

    entries.sort_by(|a, b| a.path.cmp(&b.path));

    // Compute deterministic snapshot digest from sorted entries
    let mut manifest_hasher = Sha256::new();
    for e in &entries {
        manifest_hasher.update(e.path.as_bytes());
        manifest_hasher.update(b"\0");
        manifest_hasher.update(e.kind.as_bytes());
        manifest_hasher.update(b"\0");
        manifest_hasher.update(e.sha256.as_bytes());
        manifest_hasher.update(b"\0");
    }
    let snapshot_digest = "sha256:".to_string() + &hex_encode(&manifest_hasher.finalize());

    ScanResult {
        ok: true,
        error: None,
        file_count,
        symlink_count,
        total_bytes,
        snapshot_digest,
        entries,
    }
}

fn is_excluded(rel_path: &str, exclusions: &[String]) -> bool {
    let parts: Vec<&str> = rel_path.split('/').collect();
    for excl in exclusions {
        for part in &parts {
            if part == excl {
                return true;
            }
        }
    }
    false
}

fn scan_secrets(data: &[u8]) -> Vec<SecretFingerprint> {
    let mut findings: BTreeMap<(String, String), usize> = BTreeMap::new();

    // 1. AWS Access Key (AKIA or ASIA followed by 16 alphanumerics)
    scan_aws_keys(data, &mut findings);

    // 2. GitHub Token (ghp_, gho_, ghu_, ghs_, ghr_, github_pat_)
    scan_github_tokens(data, &mut findings);

    // 3. Private Key Marker
    scan_private_keys(data, &mut findings);

    // 4. Credential Assignment (password=..., secret=...)
    scan_credentials(data, &mut findings);

    findings
        .into_iter()
        .map(|((kind, fingerprint), occurrences)| SecretFingerprint {
            kind,
            fingerprint,
            occurrences,
        })
        .collect()
}

fn domain_fingerprint(kind: &str, secret: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(b"elmos.project-intelligence.secret-fingerprint.v1\0");
    h.update(kind.as_bytes());
    h.update(b"\0");
    h.update(secret);
    "sha256:".to_string() + &hex_encode(&h.finalize())
}

fn scan_aws_keys(data: &[u8], findings: &mut BTreeMap<(String, String), usize>) {
    let len = data.len();
    if len < 20 {
        return;
    }
    for i in 0..=len - 20 {
        if &data[i..i + 4] == b"AKIA" || &data[i..i + 4] == b"ASIA" {
            let mut valid = true;
            for b in &data[i + 4..i + 20] {
                if !b.is_ascii_uppercase() && !b.is_ascii_digit() {
                    valid = false;
                    break;
                }
            }
            if valid {
                let prev_ok = i == 0 || !data[i - 1].is_ascii_alphanumeric();
                let next_ok = i + 20 == len || !data[i + 20].is_ascii_alphanumeric();
                if prev_ok && next_ok {
                    let fp = domain_fingerprint("aws-access-key", &data[i..i + 20]);
                    *findings.entry(("aws-access-key".to_string(), fp)).or_insert(0) += 1;
                }
            }
        }
    }
}

fn scan_github_tokens(data: &[u8], findings: &mut BTreeMap<(String, String), usize>) {
    let prefixes: [&[u8]; 6] = [b"ghp_", b"gho_", b"ghu_", b"ghs_", b"ghr_", b"github_pat_"];
    let len = data.len();

    for p in prefixes {
        let plen = p.len();
        if len < plen + 20 {
            continue;
        }
        for i in 0..=len - (plen + 20) {
            if &data[i..i + plen] == p {
                let mut end = i + plen;
                while end < len && (data[end].is_ascii_alphanumeric() || data[end] == b'_') {
                    end += 1;
                }
                let token_len = end - i;
                if token_len >= plen + 20 && token_len <= 255 {
                    let prev_ok = i == 0 || !data[i - 1].is_ascii_alphanumeric();
                    if prev_ok {
                        let fp = domain_fingerprint("github-token", &data[i..end]);
                        *findings.entry(("github-token".to_string(), fp)).or_insert(0) += 1;
                    }
                }
            }
        }
    }
}

fn scan_private_keys(data: &[u8], findings: &mut BTreeMap<(String, String), usize>) {
    let marker = b"-----BEGIN ";
    let private_suffix = b"PRIVATE KEY-----";
    let len = data.len();

    if len < 30 {
        return;
    }
    let mut i = 0;
    while i <= len - 30 {
        if let Some(pos) = find_subsequence(&data[i..], marker) {
            let start = i + pos;
            let check_slice = &data[start..std::cmp::min(start + 64, len)];
            if let Some(end_pos) = find_subsequence(check_slice, private_suffix) {
                let match_end = start + end_pos + private_suffix.len();
                let fp = domain_fingerprint("private-key-marker", &data[start..match_end]);
                *findings.entry(("private-key-marker".to_string(), fp)).or_insert(0) += 1;
                i = match_end;
                continue;
            }
            i = start + marker.len();
        } else {
            break;
        }
    }
}

fn scan_credentials(data: &[u8], findings: &mut BTreeMap<(String, String), usize>) {
    let keywords: [&[u8]; 7] = [b"password", b"passwd", b"secret", b"client_secret", b"api_key", b"access_token", b"auth_token"];
    let len = data.len();

    for kw in keywords {
        let klen = kw.len();
        if len < klen + 10 {
            continue;
        }
        for i in 0..=len - (klen + 10) {
            if data[i..i + klen].eq_ignore_ascii_case(kw) {
                // Check word boundary
                let prev_ok = i == 0 || !data[i - 1].is_ascii_alphanumeric();
                if !prev_ok {
                    continue;
                }
                let mut cursor = i + klen;
                while cursor < len && (data[cursor] == b' ' || data[cursor] == b'\t') {
                    cursor += 1;
                }
                if cursor < len && (data[cursor] == b'=' || data[cursor] == b':') {
                    cursor += 1;
                    while cursor < len && (data[cursor] == b' ' || data[cursor] == b'\t' || data[cursor] == b'"' || data[cursor] == b'\'') {
                        cursor += 1;
                    }
                    let val_start = cursor;
                    while cursor < len && !is_terminator(data[cursor]) {
                        cursor += 1;
                    }
                    let val_len = cursor - val_start;
                    if val_len >= 8 && val_len <= 512 {
                        let fp = domain_fingerprint("credential-assignment", &data[val_start..cursor]);
                        *findings.entry(("credential-assignment".to_string(), fp)).or_insert(0) += 1;
                    }
                }
            }
        }
    }
}

fn is_terminator(b: u8) -> bool {
    b == b'\r' || b == b'\n' || b == b'"' || b == b'\'' || b == b';' || b == b',' || b == b' ' || b == b'\t'
}

fn find_subsequence(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|window| window == needle)
}

fn hex_encode(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push_str(&format!("{:02x}", b));
    }
    s
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn test_secret_patterns() {
        let content = b"export AWS_KEY=\"AKIA1234567890ABCDEF\"\npassword = \"SuperSecret123!\"\n";
        let findings = scan_secrets(content);
        assert!(findings.iter().any(|f| f.kind == "aws-access-key"));
        assert!(findings.iter().any(|f| f.kind == "credential-assignment"));
    }

    #[test]
    fn test_scan_repository() {
        let temp = std::env::temp_dir().join("elmos_repo_scan_test");
        let _ = fs::remove_dir_all(&temp);
        fs::create_dir_all(&temp).unwrap();

        let file1 = temp.join("main.py");
        let mut f = File::create(&file1).unwrap();
        f.write_all(b"print('Hello, world!')\npassword='VerySecurePassword123'").unwrap();

        let cfg = ScannerConfig::default();
        let res = scan_repository(&temp, &cfg);
        assert!(res.ok);
        assert_eq!(res.file_count, 1);
        assert!(res.entries[0].secret_fingerprints.len() >= 1);
        assert!(res.snapshot_digest.starts_with("sha256:"));

        let _ = fs::remove_dir_all(&temp);
    }
}
