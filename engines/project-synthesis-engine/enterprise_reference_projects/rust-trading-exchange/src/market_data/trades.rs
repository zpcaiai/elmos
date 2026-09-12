use crate::core::types::*;
use std::collections::VecDeque;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TradeTick {
    pub trade_id: TradeId,
    pub instrument_id: InstrumentId,
    pub price: Price,
    pub quantity: Quantity,
    pub aggressor_side: Side,
    pub timestamp_ns: u64,
}

pub struct TradeTape {
    history: VecDeque<TradeTick>,
    max_capacity: usize,
    total_volume: Quantity,
    total_turnover: Money,
}

impl TradeTape {
    pub fn new(max_capacity: usize) -> Self {
        TradeTape {
            history: VecDeque::with_capacity(max_capacity),
            max_capacity,
            total_volume: Quantity::ZERO,
            total_turnover: Money::ZERO,
        }
    }

    pub fn record_trade(&mut self, trade: TradeTick) {
        let value = Money::from_price_quantity(trade.price, trade.quantity);
        self.total_volume = self.total_volume + trade.quantity;
        self.total_turnover = Money(self.total_turnover.0 + value.0);

        if self.history.len() >= self.max_capacity {
            self.history.pop_front();
        }
        self.history.push_back(trade);
    }

    pub fn last_trade(&self) -> Option<&TradeTick> {
        self.history.back()
    }

    pub fn recent_trades(&self, limit: usize) -> Vec<TradeTick> {
        self.history.iter().rev().take(limit).cloned().collect()
    }

    pub fn total_volume(&self) -> Quantity {
        self.total_volume
    }

    pub fn total_turnover(&self) -> Money {
        self.total_turnover
    }
}
