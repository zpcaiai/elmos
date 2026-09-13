use crate::protocol::fix_message::FixMessage;
use crate::protocol::fix_tags::*;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FixDecodeError {
    EmptyMessage,
    InvalidTagFormat(String),
    MissingTagDelimiter,
    InvalidChecksum { expected: u32, actual: u32 },
    MissingChecksumTag,
}

pub struct FixDecoder;

impl FixDecoder {
    pub fn decode(bytes: &[u8]) -> Result<FixMessage, FixDecodeError> {
        if bytes.is_empty() {
            return Err(FixDecodeError::EmptyMessage);
        }

        // Verify Checksum if Tag 10 is present
        // Checksum tag is at end: "10=xyz\x01" (7 bytes)
        if bytes.len() >= 7 {
            let last_delimiter_idx = bytes.len() - 1;
            if bytes[last_delimiter_idx] == SOH {
                // Find start of Tag 10
                if let Some(tag10_pos) = bytes[..last_delimiter_idx].windows(3).rposition(|w| w == b"10=") {
                    let checksum_str = std::str::from_utf8(&bytes[tag10_pos + 3..last_delimiter_idx])
                        .map_err(|_| FixDecodeError::MissingChecksumTag)?;
                    if let Ok(expected_csum) = checksum_str.parse::<u32>() {
                        // Sum up all bytes before "10="
                        let calculated_csum: u32 = bytes[..tag10_pos].iter().map(|&b| b as u32).sum::<u32>() % 256;
                        if calculated_csum != expected_csum {
                            return Err(FixDecodeError::InvalidChecksum {
                                expected: expected_csum,
                                actual: calculated_csum,
                            });
                        }
                    }
                }
            }
        }

        let mut msg = FixMessage::new();
        let mut start = 0;

        for (idx, &b) in bytes.iter().enumerate() {
            if b == SOH {
                let segment = &bytes[start..idx];
                start = idx + 1;

                if segment.is_empty() {
                    continue;
                }

                if let Some(eq_pos) = segment.iter().position(|&x| x == b'=') {
                    let tag_str = std::str::from_utf8(&segment[..eq_pos])
                        .map_err(|_| FixDecodeError::InvalidTagFormat("Invalid tag utf8".into()))?;
                    let val_str = std::str::from_utf8(&segment[eq_pos + 1..])
                        .map_err(|_| FixDecodeError::InvalidTagFormat("Invalid val utf8".into()))?;

                    let tag = tag_str.parse::<u32>()
                        .map_err(|_| FixDecodeError::InvalidTagFormat(tag_str.into()))?;

                    msg.set_field(tag, val_str);
                } else {
                    return Err(FixDecodeError::MissingTagDelimiter);
                }
            }
        }

        Ok(msg)
    }
}
