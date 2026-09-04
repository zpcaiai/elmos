use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;

use serde::{Deserialize, Serialize};

pub const DIGEST_PREFIX: &str = "sha256:";
pub const BLOB_MODE: u32 = 0o444;

static COUNTER: AtomicU64 = AtomicU64::new(1);

// Fast streaming SHA-256 implementation
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
        self.update(&bit_len.to_be_bytes());

        let mut out = [0u8; 32];
        for (i, &val) in self.state.iter().enumerate() {
            out[i * 4..(i + 1) * 4].copy_from_slice(&val.to_be_bytes());
        }
        out
    }

    pub fn digest_hex(data: &[u8]) -> String {
        let mut hasher = Self::new();
        hasher.update(data);
        let hash = hasher.finalize();
        let mut hex = String::with_capacity(64);
        for b in hash {
            hex.push_str(&format!("{:02x}", b));
        }
        hex
    }

    pub fn digest_canonical(data: &[u8]) -> String {
        format!("{}{}", DIGEST_PREFIX, Self::digest_hex(data))
    }

    fn process_block(&mut self, block: &[u8; 64]) {
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

        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes(block[i * 4..(i + 1) * 4].try_into().unwrap());
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
            let temp1 = h.wrapping_add(s1).wrapping_add(ch).wrapping_add(k[i]).wrapping_add(w[i]);
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
pub struct ObjectInfo {
    pub digest: String,
    pub size: u64,
    pub stored_size: u64,
    pub compression: String,
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SidecarMetadata {
    pub digest: String,
    pub size: u64,
    pub compression: String,
    pub artifact_kind: String,
    pub hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccountingInfo {
    pub object_count: usize,
    pub stored_bytes: u64,
    pub logical_bytes: u64,
    pub quarantined_count: usize,
}

pub struct ContentAddressableStore {
    pub root: PathBuf,
    pub objects_root: PathBuf,
    pub quarantine_root: PathBuf,
    pub compression: String,
    pub max_bytes: Option<u64>,
}

impl ContentAddressableStore {
    pub fn new<P: AsRef<Path>>(root: P, compression: Option<&str>, max_bytes: Option<u64>) -> io::Result<Self> {
        let root = root.as_ref().to_path_buf();
        let objects_root = root.join("cas");
        let quarantine_root = root.join("quarantine");

        fs::create_dir_all(&objects_root)?;
        fs::create_dir_all(&quarantine_root)?;

        Ok(Self {
            root,
            objects_root,
            quarantine_root,
            compression: compression.unwrap_or("none").to_string(),
            max_bytes,
        })
    }

    pub fn digest_hex_of(digest: &str) -> io::Result<&str> {
        if let Some(stripped) = digest.strip_prefix(DIGEST_PREFIX) {
            if stripped.len() == 64 && stripped.chars().all(|c| c.is_ascii_hexdigit()) {
                return Ok(stripped);
            }
        }
        Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("Invalid digest format: {}", digest),
        ))
    }

    pub fn shard_path(&self, digest: &str) -> io::Result<PathBuf> {
        let hex = Self::digest_hex_of(digest)?;
        Ok(self.objects_root.join("sha256").join(&hex[0..2]).join(&hex[2..4]))
    }

    pub fn path_for(&self, digest: &str) -> io::Result<PathBuf> {
        let hex = Self::digest_hex_of(digest)?;
        let shard = self.shard_path(digest)?;
        Ok(shard.join(format!("{}.blob", hex)))
    }

    pub fn sidecar_path(&self, digest: &str) -> io::Result<PathBuf> {
        let hex = Self::digest_hex_of(digest)?;
        let shard = self.shard_path(digest)?;
        Ok(shard.join(format!("{}.json", hex)))
    }

    pub fn quarantine_path(&self, digest: &str) -> io::Result<PathBuf> {
        let hex = Self::digest_hex_of(digest)?;
        Ok(self.quarantine_root.join(format!("{}.blob", hex)))
    }

    pub fn quarantine_reason_path(&self, digest: &str) -> io::Result<PathBuf> {
        let hex = Self::digest_hex_of(digest)?;
        Ok(self.quarantine_root.join(format!("{}.reason.json", hex)))
    }

    pub fn contains(&self, digest: &str) -> bool {
        if let Ok(path) = self.path_for(digest) {
            path.exists() && !self.is_quarantined(digest)
        } else {
            false
        }
    }

    pub fn is_quarantined(&self, digest: &str) -> bool {
        if let Ok(qpath) = self.quarantine_path(digest) {
            qpath.exists()
        } else {
            false
        }
    }

    pub fn info(&self, digest: &str) -> io::Result<ObjectInfo> {
        if self.is_quarantined(digest) {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "object is quarantined"));
        }
        let path = self.path_for(digest)?;
        if !path.exists() {
            return Err(io::Error::new(io::ErrorKind::NotFound, "object is not present in local CAS"));
        }
        let stored_size = fs::metadata(&path)?.len();
        let (size, compression) = self.read_sidecar(digest).unwrap_or((stored_size, "none".to_string()));

        Ok(ObjectInfo {
            digest: digest.to_string(),
            size,
            stored_size,
            compression,
            path: path.to_string_lossy().to_string(),
        })
    }

    fn read_sidecar(&self, digest: &str) -> Option<(u64, String)> {
        let sidecar = self.sidecar_path(digest).ok()?;
        if sidecar.exists() {
            if let Ok(content) = fs::read_to_string(&sidecar) {
                if let Ok(meta) = serde_json::from_str::<SidecarMetadata>(&content) {
                    return Some((meta.size, meta.compression));
                }
            }
        }
        None
    }

    pub fn put_bytes(
        &self,
        data: &[u8],
        expected_digest: Option<&str>,
        artifact_kind: Option<&str>,
    ) -> io::Result<String> {
        let digest = Sha256::digest_canonical(data);
        if let Some(expected) = expected_digest {
            if expected != digest {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("digest mismatch: expected {}, got {}", expected, digest),
                ));
            }
        }

        if self.contains(&digest) {
            return Ok(digest);
        }

        if let Some(max) = self.max_bytes {
            if data.len() as u64 > max {
                return Err(io::Error::new(io::ErrorKind::Other, "QuotaExceeded"));
            }
        }

        let destination = self.path_for(&digest)?;
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent)?;
        }

        self.commit_atomic(&destination, data)?;
        self.write_sidecar(&digest, data.len() as u64, "none", artifact_kind.unwrap_or("blob"))?;

        Ok(digest)
    }

    fn commit_atomic(&self, destination: &Path, payload: &[u8]) -> io::Result<()> {
        let parent = destination.parent().ok_or_else(|| {
            io::Error::new(io::ErrorKind::NotFound, "Parent directory missing")
        })?;

        let seq = COUNTER.fetch_add(1, Ordering::Relaxed);
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let temp_name = format!(".elmos-cas-{}-{}-{}", std::process::id(), now, seq);
        let temp_path = parent.join(temp_name);

        {
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&temp_path)?;
            file.write_all(payload)?;
            file.flush()?;
            file.sync_all()?;
        }

        #[cfg(unix)]
        {
            let _ = fs::set_permissions(&temp_path, fs::Permissions::from_mode(BLOB_MODE));
        }

        // Try hardlink first (atomic create-if-absent)
        match fs::hard_link(&temp_path, destination) {
            Ok(_) => {
                let _ = fs::remove_file(&temp_path);
            }
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {
                // Concurrent writer won race: converged
                let _ = fs::remove_file(&temp_path);
            }
            Err(_) => {
                // Filesystem doesn't support hard links or cross-device: fallback to rename
                match fs::rename(&temp_path, destination) {
                    Ok(_) => {}
                    Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {
                        let _ = fs::remove_file(&temp_path);
                    }
                    Err(err) => {
                        let _ = fs::remove_file(&temp_path);
                        return Err(err);
                    }
                }
            }
        }

        Ok(())
    }

    fn write_sidecar(
        &self,
        digest: &str,
        size: u64,
        compression: &str,
        artifact_kind: &str,
    ) -> io::Result<()> {
        let sidecar = self.sidecar_path(digest)?;
        if sidecar.exists() {
            return Ok(());
        }

        let meta = SidecarMetadata {
            digest: digest.to_string(),
            size,
            compression: compression.to_string(),
            artifact_kind: artifact_kind.to_string(),
            hash: "sha256".to_string(),
        };

        let mut payload = serde_json::to_string(&meta)?;
        payload.push('\n');

        let parent = sidecar.parent().unwrap();
        let seq = COUNTER.fetch_add(1, Ordering::Relaxed);
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let temp_path = parent.join(format!(".elmos-side-{}-{}-{}", std::process::id(), now, seq));

        {
            let mut file = File::create(&temp_path)?;
            file.write_all(payload.as_bytes())?;
            file.flush()?;
            file.sync_all()?;
        }

        let _ = fs::rename(&temp_path, &sidecar);
        let _ = fs::remove_file(&temp_path);
        Ok(())
    }

    pub fn get_bytes(&self, digest: &str, verify: bool) -> io::Result<Vec<u8>> {
        let _info = self.info(digest)?;
        let path = self.path_for(digest)?;
        let mut data = Vec::new();
        File::open(&path)?.read_to_end(&mut data)?;

        if verify {
            let actual = Sha256::digest_canonical(&data);
            if actual != digest {
                let _ = self.quarantine(digest, &format!("digest mismatch on read: {}", actual));
                return Err(io::Error::new(io::ErrorKind::InvalidData, "CorruptObject"));
            }
        }
        Ok(data)
    }

    pub fn quarantine(&self, digest: &str, reason: &str) -> io::Result<PathBuf> {
        let source = self.path_for(digest)?;
        let target = self.quarantine_path(digest)?;
        fs::create_dir_all(&self.quarantine_root)?;

        if source.exists() {
            match fs::rename(&source, &target) {
                Ok(_) => {}
                Err(_) => {
                    fs::copy(&source, &target)?;
                    let _ = fs::remove_file(&source);
                }
            }
        } else {
            File::create(&target)?;
        }

        let reason_path = self.quarantine_reason_path(digest)?;
        let reason_json = serde_json::json!({
            "digest": digest,
            "reason": reason,
        });
        fs::write(&reason_path, format!("{}\n", reason_json))?;
        Ok(target)
    }

    pub fn verify(&self, digest: &str) -> bool {
        match self.get_bytes(digest, true) {
            Ok(_) => true,
            Err(_) => false,
        }
    }

    pub fn accounting(&self) -> io::Result<AccountingInfo> {
        let mut object_count = 0;
        let mut stored_bytes = 0;
        let mut logical_bytes = 0;

        self.walk_blobs(&self.objects_root, &mut |path| {
            if let Ok(meta) = fs::metadata(path) {
                object_count += 1;
                stored_bytes += meta.len();
                if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                    let digest = format!("{}{}", DIGEST_PREFIX, stem);
                    if let Ok(info) = self.info(&digest) {
                        logical_bytes += info.size;
                    }
                }
            }
        })?;

        let mut quarantined_count = 0;
        if self.quarantine_root.exists() {
            for entry in fs::read_dir(&self.quarantine_root)? {
                if let Ok(entry) = entry {
                    let p = entry.path();
                    if p.extension().map_or(false, |ext| ext == "blob") {
                        quarantined_count += 1;
                    }
                }
            }
        }

        Ok(AccountingInfo {
            object_count,
            stored_bytes,
            logical_bytes,
            quarantined_count,
        })
    }

    fn walk_blobs<F>(&self, dir: &Path, callback: &mut F) -> io::Result<()>
    where
        F: FnMut(&Path),
    {
        if !dir.exists() {
            return Ok(());
        }
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let p = entry.path();
            if p.is_dir() {
                self.walk_blobs(&p, callback)?;
            } else if p.extension().map_or(false, |ext| ext == "blob") {
                callback(&p);
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sha256_known_vector() {
        let hash = Sha256::digest_hex(b"hello world");
        assert_eq!(hash, "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9");
        let digest = Sha256::digest_canonical(b"hello world");
        assert_eq!(digest, "sha256:b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9");
    }

    #[test]
    fn test_cas_put_get_contains() {
        let temp = tempfile_dir("test_cas_put_get");
        let cas = ContentAddressableStore::new(&temp, None, None).unwrap();

        let payload = b"elmos content-addressable storage fast test";
        let digest = cas.put_bytes(payload, None, None).unwrap();
        assert!(cas.contains(&digest));

        let retrieved = cas.get_bytes(&digest, true).unwrap();
        assert_eq!(retrieved, payload);

        let info = cas.info(&digest).unwrap();
        assert_eq!(info.size, payload.len() as u64);
        assert_eq!(info.stored_size, payload.len() as u64);

        let acct = cas.accounting().unwrap();
        assert_eq!(acct.object_count, 1);
        assert_eq!(acct.logical_bytes, payload.len() as u64);

        let _ = fs::remove_dir_all(&temp);
    }

    #[test]
    fn test_cas_quarantine() {
        let temp = tempfile_dir("test_cas_quarantine");
        let cas = ContentAddressableStore::new(&temp, None, None).unwrap();

        let payload = b"data to corrupt";
        let digest = cas.put_bytes(payload, None, None).unwrap();
        assert!(cas.contains(&digest));

        cas.quarantine(&digest, "bit rot simulation").unwrap();
        assert!(!cas.contains(&digest));
        assert!(cas.is_quarantined(&digest));

        let _ = fs::remove_dir_all(&temp);
    }

    fn tempfile_dir(prefix: &str) -> PathBuf {
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let path = std::env::temp_dir().join(format!("{}-{}-{}", prefix, std::process::id(), now));
        fs::create_dir_all(&path).unwrap();
        path
    }
}
