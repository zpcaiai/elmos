use crate::core::types::*;
use crate::core::order::Order;
use crate::core::orderbook::OrderBook;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EngineSnapshot {
    pub instrument_id: InstrumentId,
    pub snapshot_sequence: u64,
    pub timestamp_ns: u64,
    pub active_orders: Vec<Order>,
}

impl EngineSnapshot {
    pub fn capture(book: &OrderBook) -> Self {
        let ts = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64;

        let active_orders: Vec<Order> = book.orders.values().cloned().collect();

        EngineSnapshot {
            instrument_id: book.instrument_id.clone(),
            snapshot_sequence: book.sequence_number,
            timestamp_ns: ts,
            active_orders,
        }
    }

    pub fn restore(&self) -> Result<OrderBook, &'static str> {
        let mut book = OrderBook::new(self.instrument_id.clone());
        book.sequence_number = self.snapshot_sequence;

        for order in &self.active_orders {
            book.add_resting_order(order.clone())?;
        }

        Ok(book)
    }
}
