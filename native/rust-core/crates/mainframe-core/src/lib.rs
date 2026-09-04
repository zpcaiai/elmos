//! Mainframe Core: High-performance EBCDIC transcoding, COMP-3 packed decimal arithmetic,
//! and fixed-width COBOL record layout parsing.

use serde::{Deserialize, Serialize};

/// 256-byte lookup table for IBM CP037 EBCDIC to ASCII conversion
pub static EBCDIC_TO_ASCII: [u8; 256] = [
    0x00, 0x01, 0x02, 0x03, 0x9C, 0x09, 0x86, 0x7F, 0x97, 0x8D, 0x8E, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
    0x10, 0x11, 0x12, 0x13, 0x9D, 0x85, 0x08, 0x87, 0x18, 0x19, 0x92, 0x8F, 0x1C, 0x1D, 0x1E, 0x1F,
    0x80, 0x81, 0x82, 0x83, 0x84, 0x0A, 0x17, 0x1B, 0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x05, 0x06, 0x07,
    0x90, 0x91, 0x16, 0x93, 0x94, 0x95, 0x96, 0x04, 0x98, 0x99, 0x9A, 0x9B, 0x14, 0x15, 0x9E, 0x1A,
    0x20, 0xA0, 0xE2, 0xE4, 0xE0, 0xE1, 0xE3, 0xE5, 0xE7, 0xF1, 0xA2, 0x2E, 0x3C, 0x28, 0x2B, 0x7C,
    0x26, 0xE9, 0xEA, 0xEB, 0xE8, 0xED, 0xEE, 0xEF, 0xEC, 0xDF, 0x21, 0x24, 0x2A, 0x29, 0x3B, 0x5E,
    0x2D, 0x2F, 0xC2, 0xC4, 0xC0, 0xC1, 0xC3, 0xC5, 0xC7, 0xD1, 0xA6, 0x2C, 0x25, 0x5F, 0x3E, 0x3F,
    0xF8, 0xC9, 0xCA, 0xCB, 0xC8, 0xCD, 0xCE, 0xCF, 0xCC, 0x60, 0x3A, 0x23, 0x40, 0x27, 0x3D, 0x22,
    0xD8, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0xAB, 0xBB, 0xF0, 0xFD, 0xFE, 0xB1,
    0xB0, 0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x6F, 0x70, 0x71, 0x72, 0xAA, 0xBA, 0xE6, 0xB8, 0xC6, 0xA4,
    0xB5, 0x7E, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0xA1, 0xBF, 0xD0, 0xDD, 0xDE, 0xAE,
    0xAC, 0xA3, 0xA5, 0xB7, 0xA9, 0xA7, 0xB6, 0xBC, 0xBD, 0xBE, 0x5B, 0x5D, 0xAF, 0xA8, 0xB4, 0xD7,
    0x7B, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0xAD, 0xF4, 0xF6, 0xF2, 0xF3, 0xF5,
    0x7D, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x50, 0x51, 0x52, 0xB9, 0xFB, 0xFC, 0xF9, 0xFA, 0xFF,
    0x5C, 0xF7, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0xB2, 0xD4, 0xD6, 0xD2, 0xD3, 0xD5,
    0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0xB3, 0xDB, 0xDC, 0xD9, 0xDA, 0x9F,
];

/// Computes the inverse ASCII to EBCDIC mapping table
pub fn build_ascii_to_ebcdic_table() -> [u8; 256] {
    let mut table = [0x40u8; 256]; // default to space
    for (ebcdic_idx, &ascii_val) in EBCDIC_TO_ASCII.iter().enumerate() {
        table[ascii_val as usize] = ebcdic_idx as u8;
    }
    table
}

/// Transcodes an EBCDIC byte slice to ASCII/UTF-8 in place or into a new Vec.
pub fn ebcdic_to_ascii(bytes: &[u8]) -> Vec<u8> {
    bytes.iter().map(|&b| EBCDIC_TO_ASCII[b as usize]).collect()
}

/// Transcodes an ASCII byte slice to EBCDIC.
pub fn ascii_to_ebcdic(bytes: &[u8]) -> Vec<u8> {
    let table = build_ascii_to_ebcdic_table();
    bytes.iter().map(|&b| table[b as usize]).collect()
}

/// Decodes COBOL COMP-3 (Packed Decimal) bytes into a signed decimal string representation.
/// `scale` indicates number of decimal places (e.g. scale=2 turns 12345C into "123.45").
pub fn decode_comp3(bytes: &[u8], scale: u32) -> Result<String, String> {
    if bytes.is_empty() {
        return Err("COMP-3 byte slice cannot be empty".to_string());
    }

    let mut digits = String::with_capacity(bytes.len() * 2);
    let mut is_negative = false;

    for (i, &byte) in bytes.iter().enumerate() {
        let hi = (byte >> 4) & 0x0F;
        let lo = byte & 0x0F;

        if i < bytes.len() - 1 {
            if hi > 9 || lo > 9 {
                return Err(format!("Invalid BCD digit 0x{:02X} in COMP-3 byte index {}", byte, i));
            }
            digits.push((b'0' + hi) as char);
            digits.push((b'0' + lo) as char);
        } else {
            // Last byte: hi is digit, lo is sign
            if hi > 9 {
                return Err(format!("Invalid BCD digit 0x{:X} in final COMP-3 byte", hi));
            }
            digits.push((b'0' + hi) as char);

            match lo {
                0x0C | 0x0A | 0x0E | 0x0F => is_negative = false,
                0x0D | 0x0B => is_negative = true,
                _ => return Err(format!("Invalid sign nibble 0x{:X} in COMP-3", lo)),
            }
        }
    }

    // Strip leading zeros but keep at least one digit
    let trimmed = digits.trim_start_matches('0');
    let mut core_digits = if trimmed.is_empty() { "0" } else { trimmed }.to_string();

    let result = if scale == 0 {
        core_digits
    } else {
        let s = scale as usize;
        while core_digits.len() <= s {
            core_digits.insert(0, '0');
        }
        let split_pos = core_digits.len() - s;
        format!("{}.{}", &core_digits[..split_pos], &core_digits[split_pos..])
    };

    if is_negative && result != "0" && !result.starts_with("0.0") {
        Ok(format!("-{}", result))
    } else {
        Ok(result)
    }
}

/// Encodes a decimal number string into COMP-3 bytes.
pub fn encode_comp3(number_str: &str, scale: u32, total_bytes: usize) -> Result<Vec<u8>, String> {
    let clean = number_str.trim();
    let is_negative = clean.starts_with('-');
    let abs_str = clean.trim_start_matches('-').trim_start_matches('+');

    let (int_part, frac_part) = match abs_str.split_once('.') {
        Some((i, f)) => (i, f),
        None => (abs_str, ""),
    };

    let mut combined_digits = int_part.to_string();
    let frac_len = frac_part.len();
    if (scale as usize) >= frac_len {
        combined_digits.push_str(frac_part);
        combined_digits.push_str(&"0".repeat((scale as usize) - frac_len));
    } else {
        combined_digits.push_str(&frac_part[..(scale as usize)]);
    }

    let required_digits = total_bytes * 2 - 1;
    if combined_digits.len() > required_digits {
        return Err(format!(
            "Number has {} digits, exceeding maximum {} for {} bytes COMP-3",
            combined_digits.len(),
            required_digits,
            total_bytes
        ));
    }

    // Pad with leading zeros
    while combined_digits.len() < required_digits {
        combined_digits.insert(0, '0');
    }

    let mut result = Vec::with_capacity(total_bytes);
    let chars: Vec<char> = combined_digits.chars().collect();
    let mut c_idx = 0;

    for i in 0..total_bytes {
        if i < total_bytes - 1 {
            let d1 = chars[c_idx].to_digit(10).ok_or("non-digit character")? as u8;
            let d2 = chars[c_idx + 1].to_digit(10).ok_or("non-digit character")? as u8;
            result.push((d1 << 4) | d2);
            c_idx += 2;
        } else {
            let d = chars[c_idx].to_digit(10).ok_or("non-digit character")? as u8;
            let sign: u8 = if is_negative { 0x0D } else { 0x0C };
            result.push((d << 4) | sign);
        }
    }

    Ok(result)
}

/// Field specification in fixed-width COBOL record
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FieldSpec {
    pub name: String,
    pub offset: usize,
    pub length: usize,
    pub is_ebcdic: bool,
}

/// Slices a fixed-width COBOL record buffer and extracts fields as key-value pairs
pub fn slice_record(raw: &[u8], fields: &[FieldSpec]) -> Vec<(String, String)> {
    let mut results = Vec::with_capacity(fields.len());
    for f in fields {
        if f.offset >= raw.len() {
            results.push((f.name.clone(), String::new()));
            continue;
        }
        let end = (f.offset + f.length).min(raw.len());
        let slice = &raw[f.offset..end];
        let val = if f.is_ebcdic {
            let ascii_bytes = ebcdic_to_ascii(slice);
            String::from_utf8_lossy(&ascii_bytes).trim().to_string()
        } else {
            String::from_utf8_lossy(slice).trim().to_string()
        };
        results.push((f.name.clone(), val));
    }
    results
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ebcdic_ascii_roundtrip() {
        let original = b"HELLO MAINFRAME COBOL 2026";
        let ebcdic = ascii_to_ebcdic(original);
        assert_eq!(ebcdic[0], 0xC8); // 'H' in EBCDIC CP037
        assert_eq!(ebcdic[1], 0xC5); // 'E' in EBCDIC CP037

        let roundtrip = ebcdic_to_ascii(&ebcdic);
        assert_eq!(roundtrip, original);
    }

    #[test]
    fn test_comp3_decode() {
        // 0x12 0x34 0x5C -> +12345 (scale 2 -> 123.45)
        let bytes_pos = [0x12, 0x34, 0x5C];
        assert_eq!(decode_comp3(&bytes_pos, 2).unwrap(), "123.45");

        // 0x06 0x78 0x9D -> -6789 (scale 0 -> -6789)
        let bytes_neg = [0x06, 0x78, 0x9D];
        assert_eq!(decode_comp3(&bytes_neg, 0).unwrap(), "-6789");
    }

    #[test]
    fn test_comp3_encode() {
        let encoded = encode_comp3("123.45", 2, 3).unwrap();
        assert_eq!(encoded, vec![0x12, 0x34, 0x5C]);

        let encoded_neg = encode_comp3("-6789", 0, 3).unwrap();
        assert_eq!(encoded_neg, vec![0x06, 0x78, 0x9D]);
    }

    #[test]
    fn test_record_slicing() {
        let ascii_data = b"ACCT001   99882200";
        let ebcdic = ascii_to_ebcdic(ascii_data);

        let fields = vec![
            FieldSpec { name: "ACCOUNT_ID".to_string(), offset: 0, length: 10, is_ebcdic: true },
            FieldSpec { name: "BALANCE".to_string(), offset: 10, length: 8, is_ebcdic: true },
        ];

        let extracted = slice_record(&ebcdic, &fields);
        assert_eq!(extracted[0].0, "ACCOUNT_ID");
        assert_eq!(extracted[0].1, "ACCT001");
        assert_eq!(extracted[1].0, "BALANCE");
        assert_eq!(extracted[1].1, "99882200");
    }
}
