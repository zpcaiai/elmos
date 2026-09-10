use crate::core::types::*;
use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ImbalanceSide {
    Buy,
    Sell,
    Balanced,
}

impl ImbalanceSide {
    pub fn as_str(&self) -> &'static str {
        match self {
            ImbalanceSide::Buy => "BUY_IMBALANCE",
            ImbalanceSide::Sell => "SELL_IMBALANCE",
            ImbalanceSide::Balanced => "NO_IMBALANCE",
        }
    }
}

impl fmt::Display for ImbalanceSide {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

/// Regulatory / Market Data Auction Imbalance Indicator (NOII - Net Order Imbalance Indicator)
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuctionImbalance {
    pub instrument_id: InstrumentId,
    pub auction_epoch_ns: u64,
    pub indicative_clearing_price: Option<Price>,
    pub paired_quantity: Quantity,
    pub total_imbalance_quantity: Quantity,
    pub imbalance_side: ImbalanceSide,
    pub market_order_imbalance_quantity: Quantity,
    pub far_clearing_price: Option<Price>,  // Price based only on auction eligible orders
    pub near_clearing_price: Option<Price>, // Price incorporating continuous book depth
    pub reference_price: Price,
}

impl AuctionImbalance {
    pub fn new(
        instrument_id: InstrumentId,
        auction_epoch_ns: u64,
        indicative_clearing_price: Option<Price>,
        paired_quantity: Quantity,
        total_imbalance_quantity: Quantity,
        imbalance_side: ImbalanceSide,
        reference_price: Price,
    ) -> Self {
        AuctionImbalance {
            instrument_id,
            auction_epoch_ns,
            indicative_clearing_price,
            paired_quantity,
            total_imbalance_quantity,
            imbalance_side,
            market_order_imbalance_quantity: Quantity::ZERO,
            far_clearing_price: indicative_clearing_price,
            near_clearing_price: indicative_clearing_price,
            reference_price,
        }
    }

    #[inline]
    pub fn has_equilibrium(&self) -> bool {
        self.indicative_clearing_price.is_some() && !self.paired_quantity.is_zero()
    }
}
