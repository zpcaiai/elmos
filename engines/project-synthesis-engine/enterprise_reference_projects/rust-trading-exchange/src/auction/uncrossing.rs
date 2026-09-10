use crate::core::order::Order;
use crate::core::types::*;
use crate::auction::call_auction::CallAuctionBook;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuctionTradeRecord {
    pub trade_id: TradeId,
    pub instrument_id: InstrumentId,
    pub price: Price,
    pub quantity: Quantity,
    pub buy_order_id: OrderId,
    pub sell_order_id: OrderId,
    pub buy_participant_id: ParticipantId,
    pub sell_participant_id: ParticipantId,
    pub timestamp_ns: u64,
}

#[derive(Debug, Default)]
pub struct UncrossingResult {
    pub clearing_price: Price,
    pub total_matched_volume: Quantity,
    pub trades: Vec<AuctionTradeRecord>,
    pub remaining_bids: Vec<Order>,
    pub remaining_asks: Vec<Order>,
}

pub struct AuctionUncrossingEngine;

impl AuctionUncrossingEngine {
    pub fn uncross(
        mut book: CallAuctionBook,
        clearing_price: Price,
        mut next_trade_id: u64,
        timestamp_ns: u64,
    ) -> UncrossingResult {
        let mut result = UncrossingResult {
            clearing_price,
            total_matched_volume: Quantity::ZERO,
            trades: Vec::new(),
            remaining_bids: Vec::new(),
            remaining_asks: Vec::new(),
        };

        // Collect all eligible buy orders:
        // Priority 1: Market bids (FIFO)
        // Priority 2: Limit bids with price > clearing_price (descending price, then FIFO)
        // Priority 3: Limit bids with price == clearing_price (FIFO)
        let mut eligible_bids: Vec<Order> = Vec::new();
        eligible_bids.append(&mut book.market_bids);

        // Limit bids >= clearing_price in descending order
        let mut bid_prices: Vec<Price> = book.bids.keys().copied().filter(|&p| p >= clearing_price).collect();
        bid_prices.sort_by(|a, b| b.cmp(a)); // Descending

        for p in bid_prices {
            if let Some(mut orders) = book.bids.remove(&p) {
                eligible_bids.append(&mut orders);
            }
        }

        // Collect all eligible sell orders:
        // Priority 1: Market asks (FIFO)
        // Priority 2: Limit asks with price < clearing_price (ascending price, then FIFO)
        // Priority 3: Limit asks with price == clearing_price (FIFO)
        let mut eligible_asks: Vec<Order> = Vec::new();
        eligible_asks.append(&mut book.market_asks);

        let mut ask_prices: Vec<Price> = book.asks.keys().copied().filter(|&p| p <= clearing_price).collect();
        ask_prices.sort(); // Ascending

        for p in ask_prices {
            if let Some(mut orders) = book.asks.remove(&p) {
                eligible_asks.append(&mut orders);
            }
        }

        // Match eligible bids against eligible asks at the clearing price
        let mut bid_idx = 0;
        let mut ask_idx = 0;

        while bid_idx < eligible_bids.len() && ask_idx < eligible_asks.len() {
            let bid = &mut eligible_bids[bid_idx];
            let ask = &mut eligible_asks[ask_idx];

            let fill_qty = bid.remaining_quantity.raw().min(ask.remaining_quantity.raw());
            if fill_qty == 0 {
                if bid.remaining_quantity.is_zero() {
                    bid_idx += 1;
                }
                if ask.remaining_quantity.is_zero() {
                    ask_idx += 1;
                }
                continue;
            }

            let exec_qty = Quantity::from_raw(fill_qty);
            let _ = bid.fill(exec_qty, clearing_price);
            let _ = ask.fill(exec_qty, clearing_price);

            result.trades.push(AuctionTradeRecord {
                trade_id: TradeId(next_trade_id),
                instrument_id: book.instrument_id.clone(),
                price: clearing_price,
                quantity: exec_qty,
                buy_order_id: bid.id,
                sell_order_id: ask.id,
                buy_participant_id: bid.participant_id.clone(),
                sell_participant_id: ask.participant_id.clone(),
                timestamp_ns,
            });

            next_trade_id += 1;
            result.total_matched_volume = result.total_matched_volume + exec_qty;

            if bid.remaining_quantity.is_zero() {
                bid_idx += 1;
            }
            if ask.remaining_quantity.is_zero() {
                ask_idx += 1;
            }
        }

        // Retain partially filled or unexecuted eligible orders that remain
        while bid_idx < eligible_bids.len() {
            let bid = eligible_bids.remove(bid_idx);
            if !bid.remaining_quantity.is_zero() && !matches!(bid.order_type, OrderType::Market) {
                result.remaining_bids.push(bid);
            }
        }

        while ask_idx < eligible_asks.len() {
            let ask = eligible_asks.remove(ask_idx);
            if !ask.remaining_quantity.is_zero() && !matches!(ask.order_type, OrderType::Market) {
                result.remaining_asks.push(ask);
            }
        }

        // Add back non-participating limit bids (< clearing_price)
        for (_, orders) in book.bids {
            for order in orders {
                if !order.remaining_quantity.is_zero() {
                    result.remaining_bids.push(order);
                }
            }
        }

        // Add back non-participating limit asks (> clearing_price)
        for (_, orders) in book.asks {
            for order in orders {
                if !order.remaining_quantity.is_zero() {
                    result.remaining_asks.push(order);
                }
            }
        }

        result
    }
}
