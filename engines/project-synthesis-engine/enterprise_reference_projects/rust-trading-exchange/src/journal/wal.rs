use std::io::{self, Read, Write};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WalPayloadType {
    OrderSubmitted = 1,
    OrderCancelled = 2,
    TradeExecuted = 3,
    CircuitBreakerTriggered = 4,
}

impl WalPayloadType {
    pub fn from_u8(val: u8) -> Option<Self> {
        match val {
            1 => Some(WalPayloadType::OrderSubmitted),
            2 => Some(WalPayloadType::OrderCancelled),
            3 => Some(WalPayloadType::TradeExecuted),
            4 => Some(WalPayloadType::CircuitBreakerTriggered),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WalRecord {
    pub sequence: u64,
    pub timestamp_ns: u64,
    pub payload_type: WalPayloadType,
    pub payload: Vec<u8>,
    pub checksum: u32,
}

impl WalRecord {
    pub fn new(sequence: u64, timestamp_ns: u64, payload_type: WalPayloadType, payload: Vec<u8>) -> Self {
        let mut rec = WalRecord {
            sequence,
            timestamp_ns,
            payload_type,
            payload,
            checksum: 0,
        };
        rec.checksum = rec.compute_crc32();
        rec
    }

    pub fn compute_crc32(&self) -> u32 {
        let mut crc: u32 = 0xFFFF_FFFF;
        let bytes_to_hash = [
            &self.sequence.to_be_bytes()[..],
            &self.timestamp_ns.to_be_bytes()[..],
            &[self.payload_type.clone() as u8][..],
            &self.payload[..],
        ];

        for slice in &bytes_to_hash {
            for &byte in *slice {
                crc ^= byte as u32;
                for _ in 0..8 {
                    if crc & 1 != 0 {
                        crc = (crc >> 1) ^ 0xEDB8_8320;
                    } else {
                        crc >>= 1;
                    }
                }
            }
        }
        !crc
    }

    pub fn verify_checksum(&self) -> bool {
        self.compute_crc32() == self.checksum
    }

    pub fn encode(&self, writer: &mut impl Write) -> io::Result<()> {
        writer.write_all(&self.sequence.to_be_bytes())?;
        writer.write_all(&self.timestamp_ns.to_be_bytes())?;
        writer.write_all(&[self.payload_type.clone() as u8])?;
        writer.write_all(&(self.payload.len() as u32).to_be_bytes())?;
        writer.write_all(&self.payload)?;
        writer.write_all(&self.checksum.to_be_bytes())?;
        Ok(())
    }

    pub fn decode(reader: &mut impl Read) -> io::Result<Self> {
        let mut u64_buf = [0u8; 8];
        let mut u32_buf = [0u8; 4];
        let mut u8_buf = [0u8; 1];

        reader.read_exact(&mut u64_buf)?;
        let sequence = u64::from_be_bytes(u64_buf);

        reader.read_exact(&mut u64_buf)?;
        let timestamp_ns = u64::from_be_bytes(u64_buf);

        reader.read_exact(&mut u8_buf)?;
        let payload_type = WalPayloadType::from_u8(u8_buf[0])
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "Invalid WAL payload type"))?;

        reader.read_exact(&mut u32_buf)?;
        let payload_len = u32::from_be_bytes(u32_buf) as usize;

        let mut payload = vec![0u8; payload_len];
        reader.read_exact(&mut payload)?;

        reader.read_exact(&mut u32_buf)?;
        let checksum = u32::from_be_bytes(u32_buf);

        let rec = WalRecord {
            sequence,
            timestamp_ns,
            payload_type,
            payload,
            checksum,
        };

        if !rec.verify_checksum() {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "WAL Record CRC32 Checksum Mismatch"));
        }

        Ok(rec)
    }
}

pub struct WriteAheadLog {
    records: Vec<WalRecord>,
    last_sequence: u64,
}

impl WriteAheadLog {
    pub fn new() -> Self {
        WriteAheadLog {
            records: Vec::new(),
            last_sequence: 0,
        }
    }

    pub fn append(&mut self, payload_type: WalPayloadType, payload: Vec<u8>, timestamp_ns: u64) -> u64 {
        self.last_sequence += 1;
        let record = WalRecord::new(self.last_sequence, timestamp_ns, payload_type, payload);
        self.records.push(record);
        self.last_sequence
    }

    pub fn records_since(&self, sequence: u64) -> &[WalRecord] {
        let start_idx = self.records.iter().position(|r| r.sequence > sequence).unwrap_or(self.records.len());
        &self.records[start_idx..]
    }

    pub fn len(&self) -> usize {
        self.records.len()
    }

    pub fn is_empty(&self) -> bool {
        self.records.is_empty()
    }
}
