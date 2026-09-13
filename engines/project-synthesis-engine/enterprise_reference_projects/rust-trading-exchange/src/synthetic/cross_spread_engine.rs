use crate::core::types::{InstrumentId, Price, Quantity, Side};
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SpreadType {
    CalendarSpread,       // Front Month vs Back Month (1 : -1)
    InterCommoditySpread, // Crack / Spark Spread (e.g., 3:2:1 or Power/Gas)
    TriangularFxRing,     // Currencies A/B, B/C, A/C
}

#[derive(Debug, Clone)]
pub struct SyntheticSpreadDefinition {
    pub spread_instrument_id: InstrumentId,
    pub leg1_instrument_id: InstrumentId,
    pub leg2_instrument_id: InstrumentId,
    pub leg1_ratio: i32, // Positive = Buy leg when buying spread
    pub leg2_ratio: i32, // Negative = Sell leg when buying spread
    pub spread_type: SpreadType,
    pub min_tick_size: Price,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LegQuote {
    pub bid_price: Option<Price>,
    pub bid_qty: Quantity,
    pub ask_price: Option<Price>,
    pub ask_qty: Quantity,
}

impl Default for LegQuote {
    fn default() -> Self {
        Self {
            bid_price: None,
            bid_qty: Quantity::ZERO,
            ask_price: None,
            ask_qty: Quantity::ZERO,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ImpliedSpreadQuote {
    pub spread_instrument_id: InstrumentId,
    pub implied_bid_price: Option<Price>,
    pub implied_bid_quantity: Quantity,
    pub implied_ask_price: Option<Price>,
    pub implied_ask_quantity: Quantity,
}

#[derive(Debug, Clone)]
pub struct LeggingExecutionResult {
    pub spread_instrument_id: InstrumentId,
    pub leg1_executed_qty: Quantity,
    pub leg1_executed_price: Price,
    pub leg2_executed_qty: Quantity,
    pub leg2_executed_price: Price,
    pub legging_risk_unhedged_qty: Quantity,
    pub net_spread_price_realized: Price,
}

/// CME / Eurex Style Synthetic Cross-Spread &amp; Implied Matching Engine.
pub struct CrossSpreadEngine {
    spreads: HashMap<InstrumentId, SyntheticSpreadDefinition>,
    leg_quotes: HashMap<InstrumentId, LegQuote>,
}

impl Default for CrossSpreadEngine {
    fn default() -> Self {
        Self::new()
    }
}

impl CrossSpreadEngine {
    pub fn new() -> Self {
        Self {
            spreads: HashMap::new(),
            leg_quotes: HashMap::new(),
        }
    }

    pub fn register_spread(&mut self, spread: SyntheticSpreadDefinition) {
        self.spreads.insert(spread.spread_instrument_id.clone(), spread);
    }

    pub fn update_leg_bbo(&mut self, instrument_id: InstrumentId, quote: LegQuote) {
        self.leg_quotes.insert(instrument_id, quote);
    }

    /// Computes Implied-IN Spread BBO:
    /// Implied Spread Bid = Leg 1 Best Bid - Leg 2 Best Ask
    /// Implied Spread Ask = Leg 1 Best Ask - Leg 2 Best Bid
    pub fn calculate_implied_spread_quote(&self, spread_instrument_id: &InstrumentId) -> Option<ImpliedSpreadQuote> {
        let def = self.spreads.get(spread_instrument_id)?;
        let leg1 = self.leg_quotes.get(&def.leg1_instrument_id)?;
        let leg2 = self.leg_quotes.get(&def.leg2_instrument_id)?;

        let mut implied_bid_price = None;
        let mut implied_bid_qty = Quantity::ZERO;

        // Implied Bid: Buy Leg1 at Bid, Sell Leg2 at Ask
        if let (Some(l1_bid), Some(l2_ask)) = (leg1.bid_price, leg2.ask_price) {
            let diff_raw = l1_bid.raw() * def.leg1_ratio as i64 + l2_ask.raw() * def.leg2_ratio as i64;
            implied_bid_price = Some(Price::from_raw(diff_raw));
            implied_bid_qty = Quantity::from_raw(std::cmp::min(leg1.bid_qty.raw(), leg2.ask_qty.raw()));
        }

        let mut implied_ask_price = None;
        let mut implied_ask_qty = Quantity::ZERO;

        // Implied Ask: Sell Leg1 at Ask, Buy Leg2 at Bid
        if let (Some(l1_ask), Some(l2_bid)) = (leg1.ask_price, leg2.bid_price) {
            let diff_raw = l1_ask.raw() * def.leg1_ratio as i64 + l2_bid.raw() * def.leg2_ratio as i64;
            implied_ask_price = Some(Price::from_raw(diff_raw));
            implied_ask_qty = Quantity::from_raw(std::cmp::min(leg1.ask_qty.raw(), leg2.bid_qty.raw()));
        }

        Some(ImpliedSpreadQuote {
            spread_instrument_id: spread_instrument_id.clone(),
            implied_bid_price,
            implied_bid_quantity: implied_bid_qty,
            implied_ask_price,
            implied_ask_quantity: implied_ask_qty,
        })
    }

    /// Simulates simultaneous dual-leg execution with legging-risk detection.
    pub fn execute_spread_order(
        &self,
        spread_instrument_id: &InstrumentId,
        _side: Side,
        quantity: Quantity,
        limit_spread_price: Price,
    ) -> Result<LeggingExecutionResult, &'static str> {
        let def = self.spreads.get(spread_instrument_id).ok_or("Spread not registered")?;
        let leg1 = self.leg_quotes.get(&def.leg1_instrument_id).ok_or("Leg1 market data missing")?;
        let leg2 = self.leg_quotes.get(&def.leg2_instrument_id).ok_or("Leg2 market data missing")?;

        let (p1, p2) = match _side {
            Side::Buy => {
                let l1 = leg1.ask_price.ok_or("No Leg1 offer to buy")?;
                let l2 = leg2.bid_price.ok_or("No Leg2 bid to sell")?;
                (l1, l2)
            }
            Side::Sell => {
                let l1 = leg1.bid_price.ok_or("No Leg1 bid to sell")?;
                let l2 = leg2.ask_price.ok_or("No Leg2 offer to buy")?;
                (l1, l2)
            }
        };

        let realized_spread = Price::from_raw(p1.raw() * def.leg1_ratio as i64 + p2.raw() * def.leg2_ratio as i64);

        // Limit price verification
        match _side {
            Side::Buy => {
                if realized_spread > limit_spread_price {
                    return Err("Spread price exceeds buyer limit");
                }
            }
            Side::Sell => {
                if realized_spread < limit_spread_price {
                    return Err("Spread price below seller limit");
                }
            }
        }

        // Available quantity is bounded by leg liquidity
        let available_qty = std::cmp::min(quantity, std::cmp::min(leg1.ask_qty, leg2.bid_qty));
        let unhedged = quantity.saturating_sub(available_qty);

        Ok(LeggingExecutionResult {
            spread_instrument_id: spread_instrument_id.clone(),
            leg1_executed_qty: available_qty,
            leg1_executed_price: p1,
            leg2_executed_qty: available_qty,
            leg2_executed_price: p2,
            legging_risk_unhedged_qty: unhedged,
            net_spread_price_realized: realized_spread,
        })
    }
}
