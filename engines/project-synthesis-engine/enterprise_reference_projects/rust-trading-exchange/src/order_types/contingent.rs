use crate::core::order::Order;
use crate::core::types::*;
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContingentGroupType {
    OneCancelsOther, // OCO
    OneTriggersOther, // OTO
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OcoOrderGroup {
    pub group_id: String,
    pub leg_a: Order,
    pub leg_b: Order,
    pub active_leg: Option<OrderId>,
    pub is_resolved: bool,
}

impl OcoOrderGroup {
    pub fn new(group_id: impl Into<String>, leg_a: Order, leg_b: Order) -> Self {
        OcoOrderGroup {
            group_id: group_id.into(),
            leg_a,
            leg_b,
            active_leg: None,
            is_resolved: false,
        }
    }

    /// Handles fill event on one of the legs
    /// Returns the opposite leg's OrderId to be canceled if not already resolved
    pub fn on_leg_fill(&mut self, filled_order_id: OrderId) -> Option<OrderId> {
        if self.is_resolved {
            return None;
        }

        if self.leg_a.id == filled_order_id {
            self.active_leg = Some(filled_order_id);
            self.is_resolved = true;
            Some(self.leg_b.id)
        } else if self.leg_b.id == filled_order_id {
            self.active_leg = Some(filled_order_id);
            self.is_resolved = true;
            Some(self.leg_a.id)
        } else {
            None
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OtoOrderGroup {
    pub group_id: String,
    pub parent_order: Order,
    pub contingent_child: Order,
    pub is_triggered: bool,
}

impl OtoOrderGroup {
    pub fn new(group_id: impl Into<String>, parent_order: Order, contingent_child: Order) -> Self {
        OtoOrderGroup {
            group_id: group_id.into(),
            parent_order,
            contingent_child,
            is_triggered: false,
        }
    }

    /// When parent order is completely filled, release child order into the market
    pub fn on_parent_filled(&mut self, order_id: OrderId) -> Option<Order> {
        if !self.is_triggered && self.parent_order.id == order_id {
            self.is_triggered = true;
            Some(self.contingent_child.clone())
        } else {
            None
        }
    }
}

pub struct ContingentOrderManager {
    pub oco_groups: HashMap<String, OcoOrderGroup>,
    pub oto_groups: HashMap<String, OtoOrderGroup>,
    pub order_to_oco: HashMap<OrderId, String>,
    pub order_to_oto: HashMap<OrderId, String>,
}

impl ContingentOrderManager {
    pub fn new() -> Self {
        ContingentOrderManager {
            oco_groups: HashMap::new(),
            oto_groups: HashMap::new(),
            order_to_oco: HashMap::new(),
            order_to_oto: HashMap::new(),
        }
    }

    pub fn register_oco(&mut self, group: OcoOrderGroup) {
        let id_a = group.leg_a.id;
        let id_b = group.leg_b.id;
        let gid = group.group_id.clone();

        self.order_to_oco.insert(id_a, gid.clone());
        self.order_to_oco.insert(id_b, gid.clone());
        self.oco_groups.insert(gid, group);
    }

    pub fn register_oto(&mut self, group: OtoOrderGroup) {
        let pid = group.parent_order.id;
        let gid = group.group_id.clone();

        self.order_to_oto.insert(pid, gid.clone());
        self.oto_groups.insert(gid, group);
    }

    /// Processes trade/fill on an order, checking if it triggers OCO cancel or OTO release
    pub fn on_order_filled(&mut self, filled_order_id: OrderId) -> (Option<OrderId>, Option<Order>) {
        let mut oco_cancel_id = None;
        let mut oto_child_release = None;

        if let Some(gid) = self.order_to_oco.get(&filled_order_id) {
            if let Some(group) = self.oco_groups.get_mut(gid) {
                oco_cancel_id = group.on_leg_fill(filled_order_id);
            }
        }

        if let Some(gid) = self.order_to_oto.get(&filled_order_id) {
            if let Some(group) = self.oto_groups.get_mut(gid) {
                oto_child_release = group.on_parent_filled(filled_order_id);
            }
        }

        (oco_cancel_id, oto_child_release)
    }
}
