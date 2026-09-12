use crate::core::order::Order;
use crate::core::types::*;
use crate::auction::imbalance::{AuctionImbalance, ImbalanceSide};
use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PriceCandidateMetrics {
    pub price: Price,
    pub cumulative_buy: Quantity,
    pub cumulative_sell: Quantity,
    pub executable_volume: Quantity,
    pub imbalance_quantity: Quantity,
    pub imbalance_side: ImbalanceSide,
}

pub struct CallAuctionBook {
    pub instrument_id: InstrumentId,
    pub reference_price: Price,
    pub bids: BTreeMap<Price, Vec<Order>>, // Descending by Price
    pub asks: BTreeMap<Price, Vec<Order>>, // Ascending by Price
    pub market_bids: Vec<Order>,
    pub market_asks: Vec<Order>,
}

impl CallAuctionBook {
    pub fn new(instrument_id: InstrumentId, reference_price: Price) -> Self {
        CallAuctionBook {
            instrument_id,
            reference_price,
            bids: BTreeMap::new(),
            asks: BTreeMap::new(),
            market_bids: Vec::new(),
            market_asks: Vec::new(),
        }
    }

    pub fn insert_order(&mut self, order: Order) {
        match order.order_type {
            OrderType::Market => {
                if order.side.is_buy() {
                    self.market_bids.push(order);
                } else {
                    self.market_asks.push(order);
                }
            }
            _ => {
                if order.side.is_buy() {
                    self.bids.entry(order.price).or_default().push(order);
                } else {
                    self.asks.entry(order.price).or_default().push(order);
                }
            }
        }
    }

    pub fn cancel_order(&mut self, order_id: OrderId) -> Option<Order> {
        // Search market bids
        if let Some(pos) = self.market_bids.iter().position(|o| o.id == order_id) {
            return Some(self.market_bids.remove(pos));
        }
        // Search market asks
        if let Some(pos) = self.market_asks.iter().position(|o| o.id == order_id) {
            return Some(self.market_asks.remove(pos));
        }
        // Search limit bids
        for orders in self.bids.values_mut() {
            if let Some(pos) = orders.iter().position(|o| o.id == order_id) {
                return Some(orders.remove(pos));
            }
        }
        // Search limit asks
        for orders in self.asks.values_mut() {
            if let Some(pos) = orders.iter().position(|o| o.id == order_id) {
                return Some(orders.remove(pos));
            }
        }
        None
    }

    /// Computes candidate price metrics across all price points
    pub fn compute_price_metrics(&self) -> Vec<PriceCandidateMetrics> {
        // Collect all distinct prices
        let mut prices: Vec<Price> = self.bids.keys().chain(self.asks.keys()).copied().collect();
        prices.sort();
        prices.dedup();

        if prices.is_empty() {
            return Vec::new();
        }

        let total_market_bids: u64 = self.market_bids.iter().map(|o| o.remaining_quantity.raw()).sum();
        let total_market_asks: u64 = self.market_asks.iter().map(|o| o.remaining_quantity.raw()).sum();

        let mut metrics = Vec::with_capacity(prices.len());

        for &p in &prices {
            // Cumulative buy at price p = all market bids + all limit bids with price >= p
            let mut cum_buy = total_market_bids;
            for (&_bid_p, orders) in self.bids.range(p..) {
                let lvl_qty: u64 = orders.iter().map(|o| o.remaining_quantity.raw()).sum();
                cum_buy += lvl_qty;
            }

            // Cumulative sell at price p = all market asks + all limit asks with price <= p
            let mut cum_sell = total_market_asks;
            for (&_ask_p, orders) in self.asks.range(..=p) {
                let lvl_qty: u64 = orders.iter().map(|o| o.remaining_quantity.raw()).sum();
                cum_sell += lvl_qty;
            }

            let exec_vol = cum_buy.min(cum_sell);
            let (imb_qty, imb_side) = if cum_buy > cum_sell {
                (Quantity::from_raw(cum_buy - cum_sell), ImbalanceSide::Buy)
            } else if cum_sell > cum_buy {
                (Quantity::from_raw(cum_sell - cum_buy), ImbalanceSide::Sell)
            } else {
                (Quantity::ZERO, ImbalanceSide::Balanced)
            };

            metrics.push(PriceCandidateMetrics {
                price: p,
                cumulative_buy: Quantity::from_raw(cum_buy),
                cumulative_sell: Quantity::from_raw(cum_sell),
                executable_volume: Quantity::from_raw(exec_vol),
                imbalance_quantity: imb_qty,
                imbalance_side: imb_side,
            });
        }

        metrics
    }

    /// Evaluates the equilibrium clearing price according to standard exchange tie-breaking rules
    pub fn determine_clearing_price(&self) -> Option<Price> {
        let metrics = self.compute_price_metrics();
        if metrics.is_empty() {
            return None;
        }

        // Criterion 1: Maximize executable volume
        let max_vol = metrics.iter().map(|m| m.executable_volume.raw()).max().unwrap_or(0);
        if max_vol == 0 {
            return None;
        }

        let max_vol_candidates: Vec<&PriceCandidateMetrics> = metrics
            .iter()
            .filter(|m| m.executable_volume.raw() == max_vol)
            .collect();

        if max_vol_candidates.len() == 1 {
            return Some(max_vol_candidates[0].price);
        }

        // Criterion 2: Minimize order imbalance
        let min_imbalance = max_vol_candidates
            .iter()
            .map(|m| m.imbalance_quantity.raw())
            .min()
            .unwrap_or(0);

        let min_imb_candidates: Vec<&PriceCandidateMetrics> = max_vol_candidates
            .into_iter()
            .filter(|m| m.imbalance_quantity.raw() == min_imbalance)
            .collect();

        if min_imb_candidates.len() == 1 {
            return Some(min_imb_candidates[0].price);
        }

        // Criterion 3: Market pressure / Reference price proximity
        // Check if all candidates share the same directional pressure
        let first_side = min_imb_candidates[0].imbalance_side;
        let all_same_side = min_imb_candidates.iter().all(|c| c.imbalance_side == first_side);

        if all_same_side && first_side == ImbalanceSide::Buy {
            // Excess buy pressure drives price higher: pick highest price
            return min_imb_candidates.iter().map(|c| c.price).max();
        } else if all_same_side && first_side == ImbalanceSide::Sell {
            // Excess sell pressure drives price lower: pick lowest price
            return min_imb_candidates.iter().map(|c| c.price).min();
        }

        // Criterion 4: Choose candidate price closest to reference price
        let mut best_price = min_imb_candidates[0].price;
        let mut min_distance = (best_price.raw() - self.reference_price.raw()).abs();

        for candidate in &min_imb_candidates[1..] {
            let dist = (candidate.price.raw() - self.reference_price.raw()).abs();
            if dist < min_distance {
                min_distance = dist;
                best_price = candidate.price;
            }
        }

        Some(best_price)
    }

    /// Publishes current auction imbalance telemetry (NOII)
    pub fn calculate_imbalance(&self, epoch_ns: u64) -> AuctionImbalance {
        let clearing_price = self.determine_clearing_price();
        let metrics = self.compute_price_metrics();

        if let Some(cp) = clearing_price {
            if let Some(m) = metrics.iter().find(|m| m.price == cp) {
                return AuctionImbalance::new(
                    self.instrument_id.clone(),
                    epoch_ns,
                    Some(cp),
                    m.executable_volume,
                    m.imbalance_quantity,
                    m.imbalance_side,
                    self.reference_price,
                );
            }
        }

        // No uncrossing possible
        let total_bids: u64 = self.bids.values().flat_map(|v| v.iter()).map(|o| o.remaining_quantity.raw()).sum();
        let total_asks: u64 = self.asks.values().flat_map(|v| v.iter()).map(|o| o.remaining_quantity.raw()).sum();
        let (imb_q, imb_s) = if total_bids > total_asks {
            (Quantity::from_raw(total_bids - total_asks), ImbalanceSide::Buy)
        } else if total_asks > total_bids {
            (Quantity::from_raw(total_asks - total_bids), ImbalanceSide::Sell)
        } else {
            (Quantity::ZERO, ImbalanceSide::Balanced)
        };

        AuctionImbalance::new(
            self.instrument_id.clone(),
            epoch_ns,
            None,
            Quantity::ZERO,
            imb_q,
            imb_s,
            self.reference_price,
        )
    }
}
