use crate::core::order::Order;
use crate::core::types::*;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TrailingStopOrder {
    pub parent_order: Order,
    pub trailing_delta: Price,
    pub high_water_mark: Price,
    pub low_water_mark: Price,
    pub current_stop_price: Price,
    pub is_triggered: bool,
    pub triggered_at_price: Option<Price>,
    pub triggered_at_epoch_ns: Option<u64>,
}

impl TrailingStopOrder {
    pub fn new(parent_order: Order, trailing_delta: Price, initial_market_price: Price) -> Self {
        let (hwm, lwm, stop_price) = if parent_order.side.is_sell() {
            // Sell Trailing Stop: trails below market price. Stop price = HWM - delta
            let hwm = initial_market_price;
            let stop = hwm - trailing_delta;
            (hwm, initial_market_price, stop)
        } else {
            // Buy Trailing Stop: trails above market price. Stop price = LWM + delta
            let lwm = initial_market_price;
            let stop = lwm + trailing_delta;
            (initial_market_price, lwm, stop)
        };

        TrailingStopOrder {
            parent_order,
            trailing_delta,
            high_water_mark: hwm,
            low_water_mark: lwm,
            current_stop_price: stop_price,
            is_triggered: false,
            triggered_at_price: None,
            triggered_at_epoch_ns: None,
        }
    }

    /// Evaluates incoming trade tick against trailing stop boundaries
    /// Returns Some(triggered_order) if stop is breached
    pub fn on_market_trade(&mut self, trade_price: Price, epoch_ns: u64) -> Option<Order> {
        if self.is_triggered {
            return None;
        }

        if self.parent_order.side.is_sell() {
            // Sell trailing stop:
            // 1. If trade_price is higher than HWM, ratchet up HWM and Stop Price
            if trade_price > self.high_water_mark {
                self.high_water_mark = trade_price;
                self.current_stop_price = trade_price - self.trailing_delta;
            } else if trade_price <= self.current_stop_price {
                // 2. If trade_price falls to or below stop price, trigger!
                self.is_triggered = true;
                self.triggered_at_price = Some(trade_price);
                self.triggered_at_epoch_ns = Some(epoch_ns);

                let mut triggered = self.parent_order.clone();
                triggered.order_type = OrderType::Market;
                triggered.price = self.current_stop_price;
                return Some(triggered);
            }
        } else {
            // Buy trailing stop:
            // 1. If trade_price is lower than LWM, ratchet down LWM and Stop Price
            if trade_price < self.low_water_mark {
                self.low_water_mark = trade_price;
                self.current_stop_price = trade_price + self.trailing_delta;
            } else if trade_price >= self.current_stop_price {
                // 2. If trade_price rises to or above stop price, trigger!
                self.is_triggered = true;
                self.triggered_at_price = Some(trade_price);
                self.triggered_at_epoch_ns = Some(epoch_ns);

                let mut triggered = self.parent_order.clone();
                triggered.order_type = OrderType::Market;
                triggered.price = self.current_stop_price;
                return Some(triggered);
            }
        }

        None
    }
}
