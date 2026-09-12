use crate::core::types::*;
use std::collections::VecDeque;

/// A single price point on an order book containing orders queued in time priority.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PriceLevel {
    pub price: Price,
    pub total_volume: Quantity,
    pub visible_volume: Quantity,
    pub order_ids: VecDeque<OrderId>,
}

impl PriceLevel {
    pub fn new(price: Price) -> Self {
        PriceLevel {
            price,
            total_volume: Quantity::ZERO,
            visible_volume: Quantity::ZERO,
            order_ids: VecDeque::new(),
        }
    }

    #[inline]
    pub fn is_empty(&self) -> bool {
        self.order_ids.is_empty()
    }

    #[inline]
    pub fn order_count(&self) -> usize {
        self.order_ids.len()
    }

    #[inline]
    pub fn head_order_id(&self) -> Option<OrderId> {
        self.order_ids.front().copied()
    }

    pub fn push_order(&mut self, order_id: OrderId, total_qty: Quantity, visible_qty: Quantity) {
        self.order_ids.push_back(order_id);
        self.total_volume = self.total_volume + total_qty;
        self.visible_volume = self.visible_volume + visible_qty;
    }

    pub fn pop_head(&mut self) -> Option<OrderId> {
        self.order_ids.pop_front()
    }

    pub fn remove_order(&mut self, order_id: OrderId, total_qty: Quantity, visible_qty: Quantity) -> bool {
        if let Some(pos) = self.order_ids.iter().position(|&id| id == order_id) {
            self.order_ids.remove(pos);
            self.total_volume = self.total_volume.saturating_sub(total_qty);
            self.visible_volume = self.visible_volume.saturating_sub(visible_qty);
            true
        } else {
            false
        }
    }

    pub fn update_volumes_on_fill(&mut self, fill_qty: Quantity, visible_reduced: Quantity) {
        self.total_volume = self.total_volume.saturating_sub(fill_qty);
        self.visible_volume = self.visible_volume.saturating_sub(visible_reduced);
    }

    pub fn update_visible_replenish(&mut self, replenishment: Quantity) {
        self.visible_volume = self.visible_volume + replenishment;
    }
}
