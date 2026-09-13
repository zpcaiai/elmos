use crate::core::types::*;
use crate::market_data::trades::TradeTick;

#[derive(Debug, Clone, Default)]
pub struct VwapAccumulator {
    total_volume: u64,
    total_price_volume_product: u128,
}

impl VwapAccumulator {
    pub fn new() -> Self {
        VwapAccumulator::default()
    }

    pub fn on_trade(&mut self, trade: &TradeTick) {
        let q = trade.quantity.raw();
        let p = trade.price.raw() as u128;
        self.total_volume += q;
        self.total_price_volume_product += p * (q as u128);
    }

    pub fn current_vwap(&self) -> Option<Price> {
        if self.total_volume == 0 {
            None
        } else {
            let raw_vwap = (self.total_price_volume_product / (self.total_volume as u128)) as i64;
            Some(Price::from_raw(raw_vwap))
        }
    }

    pub fn total_volume(&self) -> Quantity {
        Quantity::from_raw(self.total_volume)
    }

    pub fn reset(&mut self) {
        self.total_volume = 0;
        self.total_price_volume_product = 0;
    }
}
