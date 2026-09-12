use crate::core::types::{InstrumentId, OrderId, Price, Quantity, Side};
use std::collections::VecDeque;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CrossingBenchmark {
    ContinuousMidpoint,
    VolumeWeightedAveragePrice,
    ClosingCrossEquilibrium,
}

#[derive(Debug, Clone)]
pub struct CrossingOrder {
    pub order_id: OrderId,
    pub instrument_id: InstrumentId,
    pub side: Side,
    pub quantity: Quantity,
    pub min_execution_quantity: Quantity,
    pub benchmark: CrossingBenchmark,
    pub max_slippage_ticks: i64,
    pub client_id: u32,
    pub timestamp_nanos: u64,
}

#[derive(Debug, Clone)]
pub struct CrossingExecutionMatch {
    pub match_id: u64,
    pub instrument_id: InstrumentId,
    pub buy_order_id: OrderId,
    pub sell_order_id: OrderId,
    pub execution_price: Price,
    pub execution_quantity: Quantity,
    pub timestamp_nanos: u64,
    pub benchmark_applied: CrossingBenchmark,
}

/// Dark Liquidity Non-Display Block Trade Crossing Engine.
pub struct VolumeWeightedCrossingEngine {
    buy_pool: VecDeque<CrossingOrder>,
    sell_pool: VecDeque<CrossingOrder>,
    next_match_id: u64,
    block_threshold_quantity: Quantity,
}

impl VolumeWeightedCrossingEngine {
    pub fn new(block_threshold_quantity: Quantity) -> Self {
        Self {
            buy_pool: VecDeque::new(),
            sell_pool: VecDeque::new(),
            next_match_id: 1,
            block_threshold_quantity,
        }
    }

    pub fn submit_crossing_order(&mut self, order: CrossingOrder) -> Result<(), &'static str> {
        // Enforce block threshold
        if order.quantity < self.block_threshold_quantity {
            return Err("Order quantity below institutional block trade threshold");
        }

        match order.side {
            Side::Buy => self.buy_pool.push_back(order),
            Side::Sell => self.sell_pool.push_back(order),
        }
        Ok(())
    }

    /// Attempts to execute crossing matches at the referenced benchmark price.
    pub fn execute_crossing_round(
        &mut self,
        benchmark_price: Price,
        timestamp_nanos: u64,
    ) -> Vec<CrossingExecutionMatch> {
        let mut matches = Vec::new();

        let mut remaining_buys = VecDeque::new();

        while let Some(mut buy) = self.buy_pool.pop_front() {
            let mut remaining_sells = VecDeque::new();
            let mut filled_buy = false;

            while let Some(mut sell) = self.sell_pool.pop_front() {
                if buy.instrument_id == sell.instrument_id && buy.client_id != sell.client_id {
                    // Matchable pair
                    let matchable_qty = std::cmp::min(buy.quantity, sell.quantity);

                    // Check min quantity constraints for both participants
                    if matchable_qty >= buy.min_execution_quantity && matchable_qty >= sell.min_execution_quantity {
                        let mid = self.next_match_id;
                        self.next_match_id += 1;

                        matches.push(CrossingExecutionMatch {
                            match_id: mid,
                            instrument_id: buy.instrument_id.clone(),
                            buy_order_id: buy.order_id,
                            sell_order_id: sell.order_id,
                            execution_price: benchmark_price,
                            execution_quantity: matchable_qty,
                            timestamp_nanos,
                            benchmark_applied: buy.benchmark,
                        });

                        buy.quantity = buy.quantity.saturating_sub(matchable_qty);
                        sell.quantity = sell.quantity.saturating_sub(matchable_qty);

                        if buy.quantity.is_zero() {
                            filled_buy = true;
                        }

                        if !sell.quantity.is_zero() {
                            remaining_sells.push_back(sell);
                        }

                        if filled_buy {
                            break;
                        }
                    } else {
                        remaining_sells.push_back(sell);
                    }
                } else {
                    remaining_sells.push_back(sell);
                }
            }

            // Restore unexhausted sells back into sell_pool
            while let Some(s) = remaining_sells.pop_front() {
                self.sell_pool.push_back(s);
            }

            if !filled_buy && !buy.quantity.is_zero() {
                remaining_buys.push_back(buy);
            }
        }

        self.buy_pool = remaining_buys;
        matches
    }
}
