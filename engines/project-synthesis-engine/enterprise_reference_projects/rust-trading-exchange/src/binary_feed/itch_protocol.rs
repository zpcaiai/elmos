use crate::core::types::*;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ItchMessage {
    SystemEvent {
        timestamp_ns: u64,
        event_code: u8, // 'O' = Start of Messages, 'S' = Start of System Hours, 'Q' = Start of Market Hours, 'M' = End of Market Hours, 'E' = End of System Hours
    },
    AddOrder {
        timestamp_ns: u64,
        order_reference_number: u64,
        side: Side,
        shares: u32,
        stock_symbol: [u8; 8],
        price_ticks: u32,
    },
    OrderExecuted {
        timestamp_ns: u64,
        order_reference_number: u64,
        executed_shares: u32,
        match_number: u64,
    },
    OrderCancel {
        timestamp_ns: u64,
        order_reference_number: u64,
        canceled_shares: u32,
    },
    OrderDelete {
        timestamp_ns: u64,
        order_reference_number: u64,
    },
    TradeMessage {
        timestamp_ns: u64,
        order_reference_number: u64,
        side: Side,
        shares: u32,
        stock_symbol: [u8; 8],
        price_ticks: u32,
        match_number: u64,
    },
}

pub struct ItchCodec;

impl ItchCodec {
    /// Encodes an ITCH 5.0 message into binary buffer (Network Byte Order / Big-Endian)
    pub fn encode(msg: &ItchMessage, buf: &mut Vec<u8>) {
        match msg {
            ItchMessage::SystemEvent { timestamp_ns, event_code } => {
                buf.push(b'S');
                buf.extend_from_slice(&timestamp_ns.to_be_bytes()[2..8]); // 6-byte nanosecond timestamp
                buf.push(*event_code);
            }
            ItchMessage::AddOrder { timestamp_ns, order_reference_number, side, shares, stock_symbol, price_ticks } => {
                buf.push(b'A');
                buf.extend_from_slice(&timestamp_ns.to_be_bytes()[2..8]); // 6-byte timestamp
                buf.extend_from_slice(&order_reference_number.to_be_bytes()); // 8 bytes
                buf.push(if side.is_buy() { b'B' } else { b'S' }); // 1 byte
                buf.extend_from_slice(&shares.to_be_bytes()); // 4 bytes
                buf.extend_from_slice(stock_symbol); // 8 bytes
                buf.extend_from_slice(&price_ticks.to_be_bytes()); // 4 bytes
            }
            ItchMessage::OrderExecuted { timestamp_ns, order_reference_number, executed_shares, match_number } => {
                buf.push(b'E');
                buf.extend_from_slice(&timestamp_ns.to_be_bytes()[2..8]);
                buf.extend_from_slice(&order_reference_number.to_be_bytes());
                buf.extend_from_slice(&executed_shares.to_be_bytes());
                buf.extend_from_slice(&match_number.to_be_bytes());
            }
            ItchMessage::OrderCancel { timestamp_ns, order_reference_number, canceled_shares } => {
                buf.push(b'X');
                buf.extend_from_slice(&timestamp_ns.to_be_bytes()[2..8]);
                buf.extend_from_slice(&order_reference_number.to_be_bytes());
                buf.extend_from_slice(&canceled_shares.to_be_bytes());
            }
            ItchMessage::OrderDelete { timestamp_ns, order_reference_number } => {
                buf.push(b'D');
                buf.extend_from_slice(&timestamp_ns.to_be_bytes()[2..8]);
                buf.extend_from_slice(&order_reference_number.to_be_bytes());
            }
            ItchMessage::TradeMessage { timestamp_ns, order_reference_number, side, shares, stock_symbol, price_ticks, match_number } => {
                buf.push(b'P');
                buf.extend_from_slice(&timestamp_ns.to_be_bytes()[2..8]);
                buf.extend_from_slice(&order_reference_number.to_be_bytes());
                buf.push(if side.is_buy() { b'B' } else { b'S' });
                buf.extend_from_slice(&shares.to_be_bytes());
                buf.extend_from_slice(stock_symbol);
                buf.extend_from_slice(&price_ticks.to_be_bytes());
                buf.extend_from_slice(&match_number.to_be_bytes());
            }
        }
    }

    /// Decodes an ITCH 5.0 message from a byte slice
    pub fn decode(slice: &[u8]) -> Result<ItchMessage, &'static str> {
        if slice.is_empty() {
            return Err("Empty slice");
        }

        let msg_type = slice[0];
        match msg_type {
            b'S' => {
                if slice.len() < 8 { return Err("Invalid SystemEvent length"); }
                let mut ts_buf = [0u8; 8];
                ts_buf[2..8].copy_from_slice(&slice[1..7]);
                let ts = u64::from_be_bytes(ts_buf);
                let code = slice[7];
                Ok(ItchMessage::SystemEvent { timestamp_ns: ts, event_code: code })
            }
            b'A' => {
                if slice.len() < 32 { return Err("Invalid AddOrder length"); }
                let mut ts_buf = [0u8; 8];
                ts_buf[2..8].copy_from_slice(&slice[1..7]);
                let ts = u64::from_be_bytes(ts_buf);

                let mut ord_buf = [0u8; 8];
                ord_buf.copy_from_slice(&slice[7..15]);
                let order_ref = u64::from_be_bytes(ord_buf);

                let side = if slice[15] == b'B' { Side::Buy } else { Side::Sell };

                let mut sh_buf = [0u8; 4];
                sh_buf.copy_from_slice(&slice[16..20]);
                let shares = u32::from_be_bytes(sh_buf);

                let mut sym_buf = [0u8; 8];
                sym_buf.copy_from_slice(&slice[20..28]);

                let mut px_buf = [0u8; 4];
                px_buf.copy_from_slice(&slice[28..32]);
                let px = u32::from_be_bytes(px_buf);

                Ok(ItchMessage::AddOrder {
                    timestamp_ns: ts,
                    order_reference_number: order_ref,
                    side,
                    shares,
                    stock_symbol: sym_buf,
                    price_ticks: px,
                })
            }
            b'E' => {
                if slice.len() < 27 { return Err("Invalid OrderExecuted length"); }
                let mut ts_buf = [0u8; 8];
                ts_buf[2..8].copy_from_slice(&slice[1..7]);
                let ts = u64::from_be_bytes(ts_buf);

                let mut ord_buf = [0u8; 8];
                ord_buf.copy_from_slice(&slice[7..15]);
                let order_ref = u64::from_be_bytes(ord_buf);

                let mut sh_buf = [0u8; 4];
                sh_buf.copy_from_slice(&slice[15..19]);
                let executed = u32::from_be_bytes(sh_buf);

                let mut match_buf = [0u8; 8];
                match_buf.copy_from_slice(&slice[19..27]);
                let match_num = u64::from_be_bytes(match_buf);

                Ok(ItchMessage::OrderExecuted {
                    timestamp_ns: ts,
                    order_reference_number: order_ref,
                    executed_shares: executed,
                    match_number: match_num,
                })
            }
            b'D' => {
                if slice.len() < 15 { return Err("Invalid OrderDelete length"); }
                let mut ts_buf = [0u8; 8];
                ts_buf[2..8].copy_from_slice(&slice[1..7]);
                let ts = u64::from_be_bytes(ts_buf);

                let mut ord_buf = [0u8; 8];
                ord_buf.copy_from_slice(&slice[7..15]);
                let order_ref = u64::from_be_bytes(ord_buf);

                Ok(ItchMessage::OrderDelete {
                    timestamp_ns: ts,
                    order_reference_number: order_ref,
                })
            }
            _ => Err("Unsupported or unknown ITCH message type"),
        }
    }

    /// Helper to convert ASCII symbol string into 8-byte padded array
    pub fn symbol_to_bytes(sym: &str) -> [u8; 8] {
        let mut buf = [b' '; 8];
        let bytes = sym.as_bytes();
        let len = bytes.len().min(8);
        buf[..len].copy_from_slice(&bytes[..len]);
        buf
    }
}
