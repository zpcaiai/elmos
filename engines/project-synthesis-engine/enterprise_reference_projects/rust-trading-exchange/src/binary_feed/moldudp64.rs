/// MoldUDP64 Transport Protocol Framer
/// Used by institutional stock exchanges to broadcast downstream market data over UDP multicast.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MoldPacketHeader {
    pub session: [u8; 10],
    pub sequence_number: u64,
    pub message_count: u16,
}

pub struct MoldUdp64Framer;

impl MoldUdp64Framer {
    pub const HEADER_LEN: usize = 20;

    /// Encodes a MoldUDP64 packet header
    pub fn encode_header(header: &MoldPacketHeader, out: &mut Vec<u8>) {
        out.extend_from_slice(&header.session);
        out.extend_from_slice(&header.sequence_number.to_be_bytes());
        out.extend_from_slice(&header.message_count.to_be_bytes());
    }

    /// Appends a single message block (2-byte length prefix + payload)
    pub fn append_message_block(payload: &[u8], out: &mut Vec<u8>) {
        let len = payload.len() as u16;
        out.extend_from_slice(&len.to_be_bytes());
        out.extend_from_slice(payload);
    }

    /// Decodes header from packet
    pub fn decode_header(packet: &[u8]) -> Result<MoldPacketHeader, &'static str> {
        if packet.len() < Self::HEADER_LEN {
            return Err("Packet too short for MoldUDP64 header");
        }

        let mut session = [0u8; 10];
        session.copy_from_slice(&packet[0..10]);

        let mut seq_buf = [0u8; 8];
        seq_buf.copy_from_slice(&packet[10..18]);
        let sequence_number = u64::from_be_bytes(seq_buf);

        let mut cnt_buf = [0u8; 2];
        cnt_buf.copy_from_slice(&packet[18..20]);
        let message_count = u16::from_be_bytes(cnt_buf);

        Ok(MoldPacketHeader {
            session,
            sequence_number,
            message_count,
        })
    }

    /// Slices messages out of a MoldUDP64 packet payload
    pub fn extract_message_payloads<'a>(packet: &'a [u8]) -> Result<Vec<&'a [u8]>, &'static str> {
        let header = Self::decode_header(packet)?;
        let mut offset = Self::HEADER_LEN;
        let mut messages = Vec::with_capacity(header.message_count as usize);

        for _ in 0..header.message_count {
            if offset + 2 > packet.len() {
                return Err("Malformed message length prefix");
            }
            let mut len_buf = [0u8; 2];
            len_buf.copy_from_slice(&packet[offset..offset + 2]);
            let msg_len = u16::from_be_bytes(len_buf) as usize;
            offset += 2;

            if offset + msg_len > packet.len() {
                return Err("Message block overflows packet buffer");
            }

            messages.push(&packet[offset..offset + msg_len]);
            offset += msg_len;
        }

        Ok(messages)
    }
}
