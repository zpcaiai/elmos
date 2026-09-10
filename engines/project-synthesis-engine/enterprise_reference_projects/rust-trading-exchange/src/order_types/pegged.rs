use crate::core::order::Order;
use crate::core::types::*;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PegType {
    Primary,  // Pegged to same-side BBO
    Market,   // Pegged to opposite-side BBO
    Midpoint, // Pegged to (Best Bid + Best Ask) / 2
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PeggedOrder {
    pub order: Order,
    pub peg_type: PegType,
    pub offset_ticks: i64,      // Signed offset from peg benchmark
    pub price_ceiling: Option<Price>, // Limit cap: Buy cannot peg above ceiling; Sell cannot peg below floor
    pub current_pegged_price: Price,
}

impl PeggedOrder {
    pub fn new(
        order: Order,
        peg_type: PegType,
        offset_ticks: i64,
        price_ceiling: Option<Price>,
        best_bid: Option<Price>,
        best_ask: Option<Price>,
    ) -> Option<Self> {
        let initial_price = Self::calculate_pegged_price(
            order.side,
            peg_type,
            offset_ticks,
            price_ceiling,
            best_bid,
            best_ask,
        )?;

        Some(PeggedOrder {
            order,
            peg_type,
            offset_ticks,
            price_ceiling,
            current_pegged_price: initial_price,
        })
    }

    /// Evaluates if BBO change requires repricing the pegged order
    pub fn on_bbo_update(
        &mut self,
        best_bid: Option<Price>,
        best_ask: Option<Price>,
    ) -> Option<Price> {
        let new_price = Self::calculate_pegged_price(
            self.order.side,
            self.peg_type,
            self.offset_ticks,
            self.price_ceiling,
            best_bid,
            best_ask,
        )?;

        if new_price != self.current_pegged_price {
            self.current_pegged_price = new_price;
            self.order.price = new_price;
            Some(new_price)
        } else {
            None
        }
    }

    /// Pure function computing target pegged price given current BBO
    pub fn calculate_pegged_price(
        side: Side,
        peg_type: PegType,
        offset_ticks: i64,
        price_ceiling: Option<Price>,
        best_bid: Option<Price>,
        best_ask: Option<Price>,
    ) -> Option<Price> {
        let base_price = match peg_type {
            PegType::Primary => {
                if side.is_buy() {
                    best_bid?
                } else {
                    best_ask?
                }
            }
            PegType::Market => {
                if side.is_buy() {
                    best_ask?
                } else {
                    best_bid?
                }
            }
            PegType::Midpoint => {
                let bid = best_bid?;
                let ask = best_ask?;
                let mid_raw = (bid.raw() + ask.raw()) / 2;
                Price::from_raw(mid_raw)
            }
        };

        let raw_with_offset = base_price.raw() + offset_ticks;
        let candidate_price = Price::from_raw(raw_with_offset);

        // Apply price ceiling / floor constraints
        if let Some(ceiling) = price_ceiling {
            if side.is_buy() && candidate_price > ceiling {
                return Some(ceiling);
            } else if side.is_sell() && candidate_price < ceiling {
                return Some(ceiling);
            }
        }

        Some(candidate_price)
    }
}
