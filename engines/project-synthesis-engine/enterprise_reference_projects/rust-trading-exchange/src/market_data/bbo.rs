use crate::core::types::*;
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BestBidOffer {
    pub instrument_id: InstrumentId,
    pub bid_price: Option<Price>,
    pub bid_quantity: Quantity,
    pub ask_price: Option<Price>,
    pub ask_quantity: Quantity,
    pub timestamp_ns: u64,
    pub sequence_number: u64,
}

impl BestBidOffer {
    pub fn spread(&self) -> Option<Price> {
        match (self.bid_price, self.ask_price) {
            (Some(bid), Some(ask)) if ask >= bid => Some(ask - bid),
            _ => None,
        }
    }

    pub fn mid_price(&self) -> Option<Price> {
        match (self.bid_price, self.ask_price) {
            (Some(bid), Some(ask)) => Some(Price::from_raw((bid.raw() + ask.raw()) / 2)),
            _ => None,
        }
    }

    pub fn is_crossed(&self) -> bool {
        match (self.bid_price, self.ask_price) {
            (Some(bid), Some(ask)) => bid > ask,
            _ => false,
        }
    }
}

impl fmt::Display for BestBidOffer {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let bid_str = self.bid_price.map_or("N/A".to_string(), |p| format!("{} x {}", p, self.bid_quantity));
        let ask_str = self.ask_price.map_or("N/A".to_string(), |p| format!("{} x {}", p, self.ask_quantity));
        write!(f, "BBO [{}] Bid: {} | Ask: {}", self.instrument_id, bid_str, ask_str)
    }
}
