use crate::core::types::*;
use crate::core::order::Order;
use crate::core::orderbook::OrderBook;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FillEvent {
    pub trade_id: TradeId,
    pub maker_order_id: OrderId,
    pub taker_order_id: OrderId,
    pub maker_participant_id: ParticipantId,
    pub taker_participant_id: ParticipantId,
    pub instrument_id: InstrumentId,
    pub side: Side, // Taker side
    pub price: Price,
    pub quantity: Quantity,
    pub gross_value: Money,
    pub timestamp_ns: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MatchResult {
    pub taker_order: Order,
    pub fills: Vec<FillEvent>,
    pub cancelled_orders: Vec<OrderId>,
    pub resting_added: bool,
}

#[derive(Debug, Clone)]
pub struct MatchingEngine {
    pub book: OrderBook,
    next_trade_id: u64,
}

impl MatchingEngine {
    pub fn new(instrument_id: InstrumentId) -> Self {
        MatchingEngine {
            book: OrderBook::new(instrument_id),
            next_trade_id: 1,
        }
    }

    pub fn from_book_and_trade_id(book: OrderBook, next_trade_id: u64) -> Self {
        MatchingEngine {
            book,
            next_trade_id,
        }
    }

    fn generate_trade_id(&mut self) -> TradeId {
        let tid = self.next_trade_id;
        self.next_trade_id += 1;
        TradeId(tid)
    }

    fn current_time_ns() -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64
    }

    /// Process an incoming taker order against the book
    pub fn submit_order(&mut self, mut taker: Order) -> Result<MatchResult, &'static str> {
        let mut fills = Vec::new();
        let mut cancelled_orders = Vec::new();
        let ts = Self::current_time_ns();

        // 1. Validate Post-Only constraint
        if taker.order_type == OrderType::PostOnly {
            let crosses = match taker.side {
                Side::Buy => self.book.best_ask().map_or(false, |(ask_p, _)| taker.price >= ask_p),
                Side::Sell => self.book.best_bid().map_or(false, |(bid_p, _)| taker.price <= bid_p),
            };
            if crosses {
                taker.reject("Post-only order would cross the spread");
                return Ok(MatchResult {
                    taker_order: taker,
                    fills,
                    cancelled_orders,
                    resting_added: false,
                });
            }
        }

        // 2. Validate FOK (Fill Or Kill) check: entire quantity must be immediately fillable
        if taker.time_in_force == TimeInForce::FillOrKill {
            if !self.can_fully_fill(&taker) {
                taker.cancel()?;
                return Ok(MatchResult {
                    taker_order: taker,
                    fills,
                    cancelled_orders,
                    resting_added: false,
                });
            }
        }

        // 3. Execution matching loop
        let is_buy = taker.side == Side::Buy;

        while !taker.is_filled() {
            // Find eligible resting price level
            let (best_price, can_match) = if is_buy {
                match self.book.asks.iter().next() {
                    Some((&ask_p, _)) => {
                        let matches = match taker.order_type {
                            OrderType::Market => true,
                            _ => taker.price >= ask_p,
                        };
                        (ask_p, matches)
                    }
                    None => break, // No liquidity left on asks
                }
            } else {
                match self.book.bids.iter().next_back() {
                    Some((&bid_p, _)) => {
                        let matches = match taker.order_type {
                            OrderType::Market => true,
                            _ => taker.price <= bid_p,
                        };
                        (bid_p, matches)
                    }
                    None => break, // No liquidity left on bids
                }
            };

            if !can_match {
                break;
            }

            // Extract candidate maker from front of queue at best_price
            let maker_id_opt = if is_buy {
                self.book.asks.get(&best_price).and_then(|lvl| lvl.head_order_id())
            } else {
                self.book.bids.get(&best_price).and_then(|lvl| lvl.head_order_id())
            };

            let maker_id = match maker_id_opt {
                Some(id) => id,
                None => break,
            };

            let maker_order = match self.book.get_order(&maker_id) {
                Some(o) => o.clone(),
                None => {
                    // Stale ID, remove and continue
                    let _ = self.book.cancel_order(maker_id);
                    continue;
                }
            };

            // 4. Self-Trade Prevention Check
            if maker_order.participant_id == taker.participant_id && taker.stp_mode != SelfTradePreventionMode::None {
                match taker.stp_mode {
                    SelfTradePreventionMode::CancelNewest => {
                        taker.cancel()?;
                        return Ok(MatchResult {
                            taker_order: taker,
                            fills,
                            cancelled_orders,
                            resting_added: false,
                        });
                    }
                    SelfTradePreventionMode::CancelOldest => {
                        let _ = self.book.cancel_order(maker_id);
                        cancelled_orders.push(maker_id);
                        continue;
                    }
                    SelfTradePreventionMode::CancelBoth => {
                        taker.cancel()?;
                        let _ = self.book.cancel_order(maker_id);
                        cancelled_orders.push(maker_id);
                        return Ok(MatchResult {
                            taker_order: taker,
                            fills,
                            cancelled_orders,
                            resting_added: false,
                        });
                    }
                    SelfTradePreventionMode::DecrementAndCancel => {
                        let match_qty = taker.remaining_quantity.raw().min(maker_order.remaining_quantity.raw());
                        taker.decrement_qty(Quantity::from_raw(match_qty));
                        let _ = self.book.cancel_order(maker_id);
                        cancelled_orders.push(maker_id);
                        if taker.is_filled() {
                            return Ok(MatchResult {
                                taker_order: taker,
                                fills,
                                cancelled_orders,
                                resting_added: false,
                            });
                        }
                        continue;
                    }
                    SelfTradePreventionMode::None => {}
                }
            }

            // 5. Match Quantity Calculation
            let match_qty = Quantity::from_raw(
                taker.remaining_quantity.raw().min(maker_order.visible_quantity.raw())
            );

            if match_qty.is_zero() {
                // If visible is 0, replenish or remove
                if maker_order.is_iceberg() && !maker_order.hidden_quantity.is_zero() {
                    if let Some(m) = self.book.get_order_mut(&maker_id) {
                        m.replenish_iceberg();
                    }
                    continue;
                } else {
                    let _ = self.book.cancel_order(maker_id);
                    continue;
                }
            }

            // Execute fill on both maker and taker
            let trade_id = self.generate_trade_id();
            let trade_value = Money::from_price_quantity(best_price, match_qty);

            taker.fill(match_qty, best_price)?;
            let _ = self.book.handle_resting_fill(maker_id, match_qty, best_price);

            fills.push(FillEvent {
                trade_id,
                maker_order_id: maker_id,
                taker_order_id: taker.id,
                maker_participant_id: maker_order.participant_id,
                taker_participant_id: taker.participant_id.clone(),
                instrument_id: self.book.instrument_id.clone(),
                side: taker.side,
                price: best_price,
                quantity: match_qty,
                gross_value: trade_value,
                timestamp_ns: ts,
            });
        }

        // 6. Post-match handling based on TimeInForce & remaining quantity
        let mut resting_added = false;
        if !taker.is_filled() {
            match taker.time_in_force {
                TimeInForce::ImmediateOrCancel | TimeInForce::FillOrKill => {
                    taker.cancel()?;
                }
                _ => {
                    if matches!(taker.order_type, OrderType::Market) {
                        // Unfilled market orders cancel
                        taker.cancel()?;
                    } else {
                        // Resting limit order added to book
                        self.book.add_resting_order(taker.clone())?;
                        resting_added = true;
                    }
                }
            }
        }

        Ok(MatchResult {
            taker_order: taker,
            fills,
            cancelled_orders,
            resting_added,
        })
    }

    /// Verify if book contains enough volume at acceptable prices to fully execute FOK order
    pub fn can_fully_fill(&self, order: &Order) -> bool {
        let is_buy = order.side == Side::Buy;
        let mut needed = order.remaining_quantity.raw();

        if is_buy {
            for (&ask_p, level) in self.book.asks.iter() {
                if matches!(order.order_type, OrderType::Limit) && ask_p > order.price {
                    break;
                }
                let available = level.visible_volume.raw();
                if available >= needed {
                    return true;
                }
                needed -= available;
            }
        } else {
            for (&bid_p, level) in self.book.bids.iter().rev() {
                if matches!(order.order_type, OrderType::Limit) && bid_p < order.price {
                    break;
                }
                let available = level.visible_volume.raw();
                if available >= needed {
                    return true;
                }
                needed -= available;
            }
        }

        false
    }
}
