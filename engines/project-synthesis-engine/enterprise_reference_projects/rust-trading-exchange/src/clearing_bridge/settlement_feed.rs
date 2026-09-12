use crate::clearing_bridge::batch_aggregator::ClearingBatchExport;

#[derive(Debug, Clone)]
pub struct SignedSettlementFeedEntry {
    pub sequence_number: u64,
    pub batch_id: String,
    pub checksum_crc32: u32,
    pub payload_csv: String,
}

pub struct SettlementFeedPublisher {
    current_sequence: u64,
}

impl SettlementFeedPublisher {
    pub fn new() -> Self {
        SettlementFeedPublisher { current_sequence: 1 }
    }

    /// Computes CRC32 checksum over raw bytes
    pub fn compute_crc32(data: &[u8]) -> u32 {
        let mut crc: u32 = 0xFFFF_FFFF;
        for &byte in data {
            crc ^= byte as u32;
            for _ in 0..8 {
                if (crc & 1) != 0 {
                    crc = (crc >> 1) ^ 0xEDB8_8320;
                } else {
                    crc >>= 1;
                }
            }
        }
        !crc
    }

    /// Converts batch export into a signed, formatted settlement feed entry
    pub fn publish_batch(&mut self, batch: &ClearingBatchExport) -> SignedSettlementFeedEntry {
        let mut csv = String::new();
        csv.push_str("BATCH_ID,PARTICIPANT_ID,INSTRUMENT_ID,NET_QTY,NET_CASH_CENTS,TRADE_COUNT\n");

        for s in &batch.member_summaries {
            csv.push_str(&format!(
                "{},{},{},{},{},{}\n",
                batch.batch_id,
                s.participant_id.as_str(),
                s.instrument_id.as_str(),
                s.net_quantity,
                s.net_cash_amount,
                s.trade_count
            ));
        }

        let checksum = Self::compute_crc32(csv.as_bytes());
        let seq = self.current_sequence;
        self.current_sequence += 1;

        SignedSettlementFeedEntry {
            sequence_number: seq,
            batch_id: batch.batch_id.clone(),
            checksum_crc32: checksum,
            payload_csv: csv,
        }
    }
}
