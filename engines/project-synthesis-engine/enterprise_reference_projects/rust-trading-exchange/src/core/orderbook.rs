use crate::core::price_level::PriceLevel;
use crate::core::order::Order;
use crate::core::types::*;
use std::collections::{BTreeMap, HashMap};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct L2Level {
    pub price: Price,
    pub quantity: Quantity,
    pub order_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct L2Snapshot {
    pub instrument_id: InstrumentId,
    pub sequence_number: u64,
    pub timestamp_ns: u64,
    pub bids: Vec<L2Level>,
    pub asks: Vec<L2Level>,
}

#[derive(Debug, Clone)]
pub struct OrderBook {
    pub instrument_id: InstrumentId,
    pub bids: BTreeMap<Price, PriceLevel>,
    pub asks: BTreeMap<Price, PriceLevel>,
    pub orders: HashMap<OrderId, Order>,
    pub sequence_number: u64,
}

impl OrderBook {
    pub fn new(instrument_id: InstrumentId) -> Self {
        OrderBook {
            instrument_id,
            bids: BTreeMap::new(),
            asks: BTreeMap::new(),
            orders: HashMap::new(),
            sequence_number: 0,
        }
    }

    #[inline]
    pub fn next_sequence(&mut self) -> u64 {
        self.sequence_number += 1;
        self.sequence_number
    }

    #[inline]
    pub fn best_bid(&self) -> Option<(Price, Quantity)> {
        self.bids.iter().next_back().map(|(&p, level)| (p, level.visible_volume))
    }

    #[inline]
    pub fn best_ask(&self) -> Option<(Price, Quantity)> {
        self.asks.iter().next().map(|(&p, level)| (p, level.visible_volume))
    }

    #[inline]
    pub fn spread(&self) -> Option<Price> {
        match (self.best_bid(), self.best_ask()) {
            (Some((bid, _)), Some((ask, _))) if ask >= bid => Some(ask - bid),
            _ => None,
        }
    }

    #[inline]
    pub fn mid_price(&self) -> Option<Price> {
        match (self.best_bid(), self.best_ask()) {
            (Some((bid, _)), Some((ask, _))) => {
                let sum = bid.raw() + ask.raw();
                Some(Price::from_raw(sum / 2))
            }
            _ => None,
        }
    }

    /// Insert a resting limit order into the book
    pub fn add_resting_order(&mut self, order: Order) -> Result<(), &'static str> {
        let oid = order.id;
        let price = order.price;
        let side = order.side;
        let total_qty = order.remaining_quantity;
        let vis_qty = order.visible_quantity;

        if self.orders.contains_key(&oid) {
            return Err("Order ID already exists in book");
        }

        let level_map = match side {
            Side::Buy => &mut self.bids,
            Side::Sell => &mut self.asks,
        };

        level_map
            .entry(price)
            .or_insert_with(|| PriceLevel::new(price))
            .push_order(oid, total_qty, vis_qty);

        self.orders.insert(oid, order);
        self.next_sequence();
        Ok(())
    }

    /// Cancel and remove an order from the book
    pub fn cancel_order(&mut self, order_id: OrderId) -> Result<Order, &'static str> {
        let mut order = self.orders.remove(&order_id).ok_or("Order not found")?;
        let price = order.price;
        let side = order.side;
        let total_qty = order.remaining_quantity;
        let vis_qty = order.visible_quantity;

        let level_map = match side {
            Side::Buy => &mut self.bids,
            Side::Sell => &mut self.asks,
        };

        let mut remove_empty_level = false;
        if let Some(level) = level_map.get_mut(&price) {
            level.remove_order(order_id, total_qty, vis_qty);
            if level.is_empty() {
                remove_empty_level = true;
            }
        }

        if remove_empty_level {
            level_map.remove(&price);
        }

        order.cancel()?;
        self.next_sequence();
        Ok(order)
    }

    /// Update an order after a fill
    pub fn handle_resting_fill(&mut self, order_id: OrderId, fill_qty: Quantity, exec_price: Price) -> Result<bool, &'static str> {
        let order = self.orders.get_mut(&order_id).ok_or("Order not found")?;
        let side = order.side;
        let price = order.price;
        let prev_vis = order.visible_quantity;

        order.fill(fill_qty, exec_price)?;
        let is_now_filled = order.is_filled();
        let new_vis = order.visible_quantity;

        let level_map = match side {
            Side::Buy => &mut self.bids,
            Side::Sell => &mut self.asks,
        };

        let mut remove_level = false;
        if let Some(level) = level_map.get_mut(&price) {
            if is_now_filled {
                level.remove_order(order_id, fill_qty, prev_vis);
            } else {
                let vis_reduced = prev_vis.saturating_sub(new_vis);
                level.update_volumes_on_fill(fill_qty, vis_reduced);
            }

            if level.is_empty() {
                remove_level = true;
            }
        }

        if remove_level {
            level_map.remove(&price);
        }

        if is_now_filled {
            self.orders.remove(&order_id);
        }

        self.next_sequence();
        Ok(is_now_filled)
    }

    pub fn get_order(&self, order_id: &OrderId) -> Option<&Order> {
        self.orders.get(order_id)
    }

    pub fn get_order_mut(&mut self, order_id: &OrderId) -> Option<&mut Order> {
        self.orders.get_mut(order_id)
    }

    /// Extract L2 market depth snapshot
    pub fn get_l2_snapshot(&self, depth: usize) -> L2Snapshot {
        let bids: Vec<L2Level> = self.bids
            .iter()
            .rev()
            .take(depth)
            .map(|(&p, lvl)| L2Level {
                price: p,
                quantity: lvl.visible_volume,
                order_count: lvl.order_count(),
            })
            .collect();

        let asks: Vec<L2Level> = self.asks
            .iter()
            .take(depth)
            .map(|(&p, lvl)| L2Level {
                price: p,
                quantity: lvl.visible_volume,
                order_count: lvl.order_count(),
            })
            .collect();

        L2Snapshot {
            instrument_id: self.instrument_id.clone(),
            sequence_number: self.sequence_number,
            timestamp_ns: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos() as u64,
            bids,
            asks,
        }
    }
}
