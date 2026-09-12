/// Simple Binary Encoding (SBE) Packet Envelope
/// Follows the FIX Simple Binary Encoding (SBE) specification for ultra-low latency serializations.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SbeHeader {
    pub block_length: u16,
    pub template_id: u16,
    pub schema_id: u16,
    pub version: u16,
}

impl SbeHeader {
    pub const HEADER_SIZE: usize = 8;

    pub fn new(block_length: u16, template_id: u16, schema_id: u16, version: u16) -> Self {
        SbeHeader {
            block_length,
            template_id,
            schema_id,
            version,
        }
    }

    pub fn encode_to(&self, buf: &mut Vec<u8>) {
        buf.extend_from_slice(&self.block_length.to_le_bytes()); // SBE uses Little-Endian for x86/ARM efficiency
        buf.extend_from_slice(&self.template_id.to_le_bytes());
        buf.extend_from_slice(&self.schema_id.to_le_bytes());
        buf.extend_from_slice(&self.version.to_le_bytes());
    }

    pub fn decode_from(slice: &[u8]) -> Result<Self, &'static str> {
        if slice.len() < Self::HEADER_SIZE {
            return Err("Slice too short for SBE header");
        }

        let mut b_len = [0u8; 2];
        b_len.copy_from_slice(&slice[0..2]);
        let block_length = u16::from_le_bytes(b_len);

        let mut t_id = [0u8; 2];
        t_id.copy_from_slice(&slice[2..4]);
        let template_id = u16::from_le_bytes(t_id);

        let mut s_id = [0u8; 2];
        s_id.copy_from_slice(&slice[4..6]);
        let schema_id = u16::from_le_bytes(s_id);

        let mut v = [0u8; 2];
        v.copy_from_slice(&slice[6..8]);
        let version = u16::from_le_bytes(v);

        Ok(SbeHeader {
            block_length,
            template_id,
            schema_id,
            version,
        })
    }
}
