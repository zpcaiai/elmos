//! Industrial Core: High-performance industrial byte-order transformations (ABCD, DCBA,
//! BADC, CDAB), IEEE 754 float reassembly, and Modbus/PLC register decoding.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Endianness {
    #[serde(rename = "ABCD")]
    BigEndian, // ABCD (Motorola)
    #[serde(rename = "DCBA")]
    LittleEndian, // DCBA (Intel)
    #[serde(rename = "BADC")]
    MidBigEndian, // BADC (Word-swapped)
    #[serde(rename = "CDAB")]
    MidLittleEndian, // CDAB (Byte-swapped)
}

impl Endianness {
    pub fn from_str(s: &str) -> Self {
        match s.trim().to_uppercase().as_str() {
            "DCBA" | "LITTLE" => Endianness::LittleEndian,
            "BADC" | "MID_BIG" => Endianness::MidBigEndian,
            "CDAB" | "MID_LITTLE" => Endianness::MidLittleEndian,
            _ => Endianness::BigEndian, // default ABCD
        }
    }
}

/// Swaps 4 bytes according to the specified industrial endianness to normalize to Big-Endian (ABCD)
#[inline]
pub fn swap_bytes_32(raw: [u8; 4], mode: Endianness) -> [u8; 4] {
    match mode {
        Endianness::BigEndian => raw,
        Endianness::LittleEndian => [raw[3], raw[2], raw[1], raw[0]],
        Endianness::MidBigEndian => [raw[1], raw[0], raw[3], raw[2]],
        Endianness::MidLittleEndian => [raw[2], raw[3], raw[0], raw[1]],
    }
}

/// Decodes an IEEE 754 32-bit float from 4 raw bytes under specified endianness
#[inline]
pub fn decode_float32(raw: [u8; 4], mode: Endianness) -> f32 {
    let be = swap_bytes_32(raw, mode);
    f32::from_be_bytes(be)
}

/// Decodes a signed 32-bit integer from 4 raw bytes under specified endianness
#[inline]
pub fn decode_int32(raw: [u8; 4], mode: Endianness) -> i32 {
    let be = swap_bytes_32(raw, mode);
    i32::from_be_bytes(be)
}

/// Decodes an unsigned 32-bit integer from 4 raw bytes under specified endianness
#[inline]
pub fn decode_uint32(raw: [u8; 4], mode: Endianness) -> u32 {
    let be = swap_bytes_32(raw, mode);
    u32::from_be_bytes(be)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegisterMapping {
    pub register_address: u16,
    pub tag_name: String,
    pub data_type: String, // FLOAT32, INT32, UINT32, INT16, UINT16
    pub endianness: Option<String>,
    pub scale: Option<f64>,
    pub offset: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecodedTagValue {
    pub tag_name: String,
    pub raw_value: f64,
    pub engineering_value: f64,
    pub quality: String,
}

/// Decodes a continuous block of 16-bit Modbus holding registers into engineering tag values
pub fn decode_modbus_block(
    registers: &[u16],
    start_address: u16,
    mappings: &[RegisterMapping],
) -> Vec<DecodedTagValue> {
    let mut results = Vec::with_capacity(mappings.len());

    for m in mappings {
        if m.register_address < start_address {
            continue;
        }
        let offset = (m.register_address - start_address) as usize;
        let mode = Endianness::from_str(m.endianness.as_deref().unwrap_or("ABCD"));

        let dt = m.data_type.to_uppercase();
        let (raw, ok) = if dt.contains("FLOAT32") || dt.contains("INT32") || dt.contains("UINT32") {
            if offset + 1 < registers.len() {
                let r0 = registers[offset];
                let r1 = registers[offset + 1];
                let raw_bytes = [(r0 >> 8) as u8, (r0 & 0xFF) as u8, (r1 >> 8) as u8, (r1 & 0xFF) as u8];
                if dt.contains("FLOAT32") {
                    (decode_float32(raw_bytes, mode) as f64, true)
                } else if dt.contains("INT32") {
                    (decode_int32(raw_bytes, mode) as f64, true)
                } else {
                    (decode_uint32(raw_bytes, mode) as f64, true)
                }
            } else {
                (0.0, false)
            }
        } else if dt.contains("INT16") {
            if offset < registers.len() {
                (registers[offset] as i16 as f64, true)
            } else {
                (0.0, false)
            }
        } else {
            // Default UINT16
            if offset < registers.len() {
                (registers[offset] as f64, true)
            } else {
                (0.0, false)
            }
        };

        if ok {
            let scale = m.scale.unwrap_or(1.0);
            let off = m.offset.unwrap_or(0.0);
            let eng = raw * scale + off;
            results.push(DecodedTagValue {
                tag_name: m.tag_name.clone(),
                raw_value: raw,
                engineering_value: eng,
                quality: "GOOD".to_string(),
            });
        } else {
            results.push(DecodedTagValue {
                tag_name: m.tag_name.clone(),
                raw_value: 0.0,
                engineering_value: 0.0,
                quality: "BAD_OUT_OF_BOUNDS".to_string(),
            });
        }
    }

    results
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_float32_endianness() {
        // IEEE 754 representation of 12.34f32 in Big-Endian is [0x41, 0x45, 0x70, 0xA4]
        let original = 12.34f32;
        let be_bytes = original.to_be_bytes();

        // 1. ABCD
        assert!((decode_float32(be_bytes, Endianness::BigEndian) - original).abs() < 1e-5);

        // 2. DCBA (Little Endian)
        let le_bytes = [be_bytes[3], be_bytes[2], be_bytes[1], be_bytes[0]];
        assert!((decode_float32(le_bytes, Endianness::LittleEndian) - original).abs() < 1e-5);

        // 3. CDAB (Mid-Little / Word-swapped)
        let mid_bytes = [be_bytes[2], be_bytes[3], be_bytes[0], be_bytes[1]];
        assert!((decode_float32(mid_bytes, Endianness::MidLittleEndian) - original).abs() < 1e-5);

        // 4. BADC (Byte-swapped)
        let badc_bytes = [be_bytes[1], be_bytes[0], be_bytes[3], be_bytes[2]];
        assert!((decode_float32(badc_bytes, Endianness::MidBigEndian) - original).abs() < 1e-5);
    }

    #[test]
    fn test_modbus_block_decoding() {
        // Register 40001 (offset 0): Float32 50.5 (0x424A 0x0000 in Big-Endian)
        let f_val = 50.5f32;
        let f_bytes = f_val.to_be_bytes();
        let r0 = ((f_bytes[0] as u16) << 8) | (f_bytes[1] as u16);
        let r1 = ((f_bytes[2] as u16) << 8) | (f_bytes[3] as u16);
        let r2 = 1200u16; // RPM uint16

        let registers = vec![r0, r1, r2];

        let mappings = vec![
            RegisterMapping {
                register_address: 40001,
                tag_name: "MotorTemp".to_string(),
                data_type: "FLOAT32".to_string(),
                endianness: Some("ABCD".to_string()),
                scale: Some(1.0),
                offset: Some(0.0),
            },
            RegisterMapping {
                register_address: 40003,
                tag_name: "RPM".to_string(),
                data_type: "UINT16".to_string(),
                endianness: None,
                scale: Some(0.1), // scale 1200 -> 120.0
                offset: Some(5.0),  // 125.0
            },
        ];

        let results = decode_modbus_block(&registers, 40001, &mappings);
        assert_eq!(results.len(), 2);
        assert_eq!(results[0].tag_name, "MotorTemp");
        assert!((results[0].engineering_value - 50.5).abs() < 1e-4);

        assert_eq!(results[1].tag_name, "RPM");
        assert!((results[1].engineering_value - 125.0).abs() < 1e-4);
    }
}
