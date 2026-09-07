use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArchiveEntryInfo {
    pub path: String,
    pub compressed_bytes: u64,
    pub uncompressed_bytes: u64,
    pub is_dir: bool,
    pub is_symlink: bool,
    pub sha256: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArchiveInspectionResult {
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    pub container_format: String,
    pub entry_count: usize,
    pub total_compressed_bytes: u64,
    pub total_uncompressed_bytes: u64,
    pub compression_ratio: f64,
    pub merkle_root: String,
    pub entries: Vec<ArchiveEntryInfo>,
}

pub struct ArchiveLimits {
    pub max_entries: usize,
    pub max_uncompressed_bytes: u64,
    pub max_expansion_ratio: f64,
}

impl Default for ArchiveLimits {
    fn default() -> Self {
        Self {
            max_entries: 50_000,
            max_uncompressed_bytes: 1024 * 1024 * 1024, // 1 GB
            max_expansion_ratio: 100.0,
        }
    }
}

pub fn inspect_archive<P: AsRef<Path>>(path: P, limits: &ArchiveLimits) -> ArchiveInspectionResult {
    let mut file = match File::open(path.as_ref()) {
        Ok(f) => f,
        Err(e) => {
            return error_result("UNKNOWN", &format!("cannot open archive: {}", e));
        }
    };

    let total_size = match file.metadata() {
        Ok(m) => m.len(),
        Err(e) => {
            return error_result("UNKNOWN", &format!("cannot read file metadata: {}", e));
        }
    };

    if total_size < 4 {
        return error_result("UNKNOWN", "archive file too small");
    }

    let mut magic = [0u8; 4];
    if file.read_exact(&mut magic).is_err() {
        return error_result("UNKNOWN", "cannot read magic header");
    }

    if &magic[0..2] == b"PK" {
        inspect_zip(&mut file, total_size, limits)
    } else if &magic[0..2] == &[0x1f, 0x8b] {
        // Gzip / tar.gz
        error_result("TAR_GZ", "tar.gz streaming inspection supported via TAR mode")
    } else {
        // Check for tar
        let _ = file.seek(SeekFrom::Start(0));
        inspect_tar(&mut file, total_size, limits)
    }
}

fn error_result(fmt: &str, msg: &str) -> ArchiveInspectionResult {
    ArchiveInspectionResult {
        ok: false,
        error: Some(msg.to_string()),
        container_format: fmt.to_string(),
        entry_count: 0,
        total_compressed_bytes: 0,
        total_uncompressed_bytes: 0,
        compression_ratio: 0.0,
        merkle_root: "".to_string(),
        entries: Vec::new(),
    }
}

fn inspect_zip(file: &mut File, total_size: u64, limits: &ArchiveLimits) -> ArchiveInspectionResult {
    // Locate End of Central Directory (EOCD): signature 0x06054b50
    // EOCD is at least 22 bytes, at most 22 + 65535 bytes from the end.
    let max_search = std::cmp::min(total_size, 65535 + 22);
    let search_start = total_size - max_search;
    if file.seek(SeekFrom::Start(search_start)).is_err() {
        return error_result("ZIP", "failed to seek for EOCD");
    }

    let mut buf = vec![0u8; max_search as usize];
    if file.read_exact(&mut buf).is_err() {
        return error_result("ZIP", "failed to read EOCD buffer");
    }

    let eocd_sig = [0x50, 0x4b, 0x05, 0x06];
    let pos = match buf.windows(4).rposition(|w| w == eocd_sig) {
        Some(p) => p,
        None => return error_result("ZIP", "valid ZIP EOCD header not found"),
    };

    let eocd = &buf[pos..];
    if eocd.len() < 22 {
        return error_result("ZIP", "truncated EOCD record");
    }

    let total_entries = u16::from_le_bytes([eocd[10], eocd[11]]) as usize;
    let cd_size = u32::from_le_bytes([eocd[12], eocd[13], eocd[14], eocd[15]]) as u64;
    let cd_offset = u32::from_le_bytes([eocd[16], eocd[17], eocd[18], eocd[19]]) as u64;

    if total_entries > limits.max_entries {
        return error_result("ZIP", &format!("declared entry count {} exceeds limit {}", total_entries, limits.max_entries));
    }

    if file.seek(SeekFrom::Start(cd_offset)).is_err() {
        return error_result("ZIP", "failed to seek to central directory");
    }

    let mut cd_data = vec![0u8; cd_size as usize];
    if file.read_exact(&mut cd_data).is_err() {
        return error_result("ZIP", "failed to read central directory");
    }

    let mut entries = Vec::with_capacity(total_entries);
    let mut total_uncompressed = 0u64;
    let mut total_compressed = 0u64;
    let mut cursor = 0;

    let cf_sig = [0x50, 0x4b, 0x01, 0x02];
    while cursor + 46 <= cd_data.len() {
        if &cd_data[cursor..cursor + 4] != cf_sig {
            break;
        }

        let comp_size = u32::from_le_bytes([
            cd_data[cursor + 20], cd_data[cursor + 21], cd_data[cursor + 22], cd_data[cursor + 23],
        ]) as u64;
        let uncomp_size = u32::from_le_bytes([
            cd_data[cursor + 24], cd_data[cursor + 25], cd_data[cursor + 26], cd_data[cursor + 27],
        ]) as u64;
        let fname_len = u16::from_le_bytes([cd_data[cursor + 28], cd_data[cursor + 29]]) as usize;
        let extra_len = u16::from_le_bytes([cd_data[cursor + 30], cd_data[cursor + 31]]) as usize;
        let comment_len = u16::from_le_bytes([cd_data[cursor + 32], cd_data[cursor + 33]]) as usize;

        cursor += 46;
        if cursor + fname_len > cd_data.len() {
            return error_result("ZIP", "truncated filename in central directory");
        }

        let name_bytes = &cd_data[cursor..cursor + fname_len];
        let name = String::from_utf8_lossy(name_bytes).to_string();
        cursor += fname_len + extra_len + comment_len;

        // Path safety
        if name.starts_with('/') || name.starts_with('\\') || name.contains("../") || name.contains("..\\") {
            return error_result("ZIP", &format!("unsafe path detected: {}", name));
        }

        let is_dir = name.ends_with('/') || name.ends_with('\\');
        total_compressed += comp_size;
        total_uncompressed += uncomp_size;

        if total_uncompressed > limits.max_uncompressed_bytes {
            return error_result("ZIP", &format!("uncompressed size exceeds limit {}", limits.max_uncompressed_bytes));
        }

        entries.push(ArchiveEntryInfo {
            path: name,
            compressed_bytes: comp_size,
            uncompressed_bytes: uncomp_size,
            is_dir,
            is_symlink: false,
            sha256: None,
        });
    }

    let ratio = if total_compressed > 0 {
        total_uncompressed as f64 / total_compressed as f64
    } else {
        1.0
    };

    if ratio > limits.max_expansion_ratio {
        return error_result("ZIP", &format!("zip bomb detected: compression ratio {:.2} exceeds limit {:.2}", ratio, limits.max_expansion_ratio));
    }

    // Compute Merkle root of entries
    entries.sort_by(|a, b| a.path.cmp(&b.path));
    let mut root_hasher = elmos_repo_scanner::Sha256::new();
    for e in &entries {
        root_hasher.update(e.path.as_bytes());
        root_hasher.update(&e.uncompressed_bytes.to_be_bytes());
    }
    let merkle_root = "sha256:".to_string() + &hex_encode(&root_hasher.finalize());

    ArchiveInspectionResult {
        ok: true,
        error: None,
        container_format: "ZIP".to_string(),
        entry_count: entries.len(),
        total_compressed_bytes: total_compressed,
        total_uncompressed_bytes: total_uncompressed,
        compression_ratio: ratio,
        merkle_root,
        entries,
    }
}

fn inspect_tar(file: &mut File, total_size: u64, limits: &ArchiveLimits) -> ArchiveInspectionResult {
    let mut header = [0u8; 512];
    let mut entries = Vec::new();
    let mut total_uncompressed = 0u64;

    while let Ok(()) = file.read_exact(&mut header) {
        if header.iter().all(|&b| b == 0) {
            // Consecutive 0 blocks indicate end of tar
            break;
        }

        let name_raw = &header[0..100];
        let name_end = name_raw.iter().position(|&b| b == 0).unwrap_or(100);
        let name = String::from_utf8_lossy(&name_raw[..name_end]).to_string();

        if name.starts_with('/') || name.contains("../") {
            return error_result("TAR", &format!("unsafe tar path: {}", name));
        }

        let size_str = String::from_utf8_lossy(&header[124..136]);
        let size = parse_octal(size_str.trim().trim_matches('\0'));

        let typeflag = header[156];
        let is_dir = typeflag == b'5' || name.ends_with('/');
        let is_symlink = typeflag == b'2';

        total_uncompressed += size;
        if total_uncompressed > limits.max_uncompressed_bytes {
            return error_result("TAR", "uncompressed tar size exceeded limit");
        }

        entries.push(ArchiveEntryInfo {
            path: name,
            compressed_bytes: size,
            uncompressed_bytes: size,
            is_dir,
            is_symlink,
            sha256: None,
        });

        // Skip payload blocks (rounded to 512 bytes)
        let blocks = (size + 511) / 512;
        if file.seek(SeekFrom::Current((blocks * 512) as i64)).is_err() {
            break;
        }
    }

    entries.sort_by(|a, b| a.path.cmp(&b.path));
    let mut root_hasher = elmos_repo_scanner::Sha256::new();
    for e in &entries {
        root_hasher.update(e.path.as_bytes());
        root_hasher.update(&e.uncompressed_bytes.to_be_bytes());
    }
    let merkle_root = "sha256:".to_string() + &hex_encode(&root_hasher.finalize());

    ArchiveInspectionResult {
        ok: true,
        error: None,
        container_format: "TAR".to_string(),
        entry_count: entries.len(),
        total_compressed_bytes: total_size,
        total_uncompressed_bytes: total_uncompressed,
        compression_ratio: 1.0,
        merkle_root,
        entries,
    }
}

fn parse_octal(s: &str) -> u64 {
    u64::from_str_radix(s.trim(), 8).unwrap_or(0)
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

    #[test]
    fn test_error_result_on_nonexistent() {
        let limits = ArchiveLimits::default();
        let res = inspect_archive("/nonexistent-file.zip", &limits);
        assert!(!res.ok);
        assert!(res.error.is_some());
    }
}
