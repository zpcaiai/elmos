use crate::core::types::*;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BookDeltaAction {
    Add,
    Modify,
    Delete,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DepthDelta {
    pub side: Side,
    pub price: Price,
    pub quantity: Quantity,
    pub action: BookDeltaAction,
    pub order_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IncrementalMarketDepthMessage {
    pub instrument_id: InstrumentId,
    pub sequence_number: u64,
    pub timestamp_ns: u64,
    pub updates: Vec<DepthDelta>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AggregatedLevel {
    pub price: Price,
    pub quantity: Quantity,
    pub orders: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MarketDepthSnapshot {
    pub instrument_id: InstrumentId,
    pub sequence_number: u64,
    pub timestamp_ns: u64,
    pub bids: Vec<AggregatedLevel>,
    pub asks: Vec<AggregatedLevel>,
}
