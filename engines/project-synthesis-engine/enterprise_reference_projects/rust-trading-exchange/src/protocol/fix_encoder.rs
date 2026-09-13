use crate::protocol::fix_message::FixMessage;
use crate::protocol::fix_tags::*;

pub struct FixEncoder;

impl FixEncoder {
    pub fn encode(msg: &FixMessage, begin_string: &str) -> Vec<u8> {
        let body_length = msg.calculate_body_length();

        // Estimate capacity: header (30) + body + trailer (10)
        let mut buffer = Vec::with_capacity(40 + body_length);

        // 1. Tag 8: BeginString
        buffer.extend_from_slice(b"8=");
        buffer.extend_from_slice(begin_string.as_bytes());
        buffer.push(SOH);

        // 2. Tag 9: BodyLength
        buffer.extend_from_slice(b"9=");
        buffer.extend_from_slice(body_length.to_string().as_bytes());
        buffer.push(SOH);

        // 3. Body fields (all except 8, 9, 10)
        for field in &msg.fields {
            if field.tag == BEGIN_STRING || field.tag == BODY_LENGTH || field.tag == CHECK_SUM {
                continue;
            }
            buffer.extend_from_slice(field.tag.to_string().as_bytes());
            buffer.push(b'=');
            buffer.extend_from_slice(field.value.as_bytes());
            buffer.push(SOH);
        }

        // 4. Compute Checksum: sum of all bytes in buffer modulo 256
        let checksum: u32 = buffer.iter().map(|&b| b as u32).sum::<u32>() % 256;

        // 5. Tag 10: CheckSum padded to 3 digits
        buffer.extend_from_slice(b"10=");
        buffer.extend_from_slice(format!("{:03}", checksum).as_bytes());
        buffer.push(SOH);

        buffer
    }
}
