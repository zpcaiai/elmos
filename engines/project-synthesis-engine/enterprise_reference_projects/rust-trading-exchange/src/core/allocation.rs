use crate::core::types::*;
use crate::core::order::Order;
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AllocationModel {
    Fifo,
    ProRata,
    ThresholdProRata { threshold_qty: Quantity },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AllocationShare {
    pub order_id: OrderId,
    pub allocated_quantity: Quantity,
}

pub trait Allocator {
    fn allocate(
        &self,
        order_ids: &[OrderId],
        orders: &HashMap<OrderId, Order>,
        available_demand_qty: Quantity,
    ) -> Vec<AllocationShare>;
}

/// FIFO: Allocate 100% in pure time-priority order until demand is satisfied
pub struct FifoAllocator;

impl Allocator for FifoAllocator {
    fn allocate(
        &self,
        order_ids: &[OrderId],
        orders: &HashMap<OrderId, Order>,
        available_demand_qty: Quantity,
    ) -> Vec<AllocationShare> {
        let mut allocations = Vec::new();
        let mut remaining_demand = available_demand_qty;

        for &oid in order_ids {
            if remaining_demand.is_zero() {
                break;
            }
            if let Some(order) = orders.get(&oid) {
                let fillable = Quantity::from_raw(order.visible_quantity.raw().min(remaining_demand.raw()));
                if !fillable.is_zero() {
                    allocations.push(AllocationShare {
                        order_id: oid,
                        allocated_quantity: fillable,
                    });
                    remaining_demand = remaining_demand - fillable;
                }
            }
        }

        allocations
    }
}

/// Pro-Rata: Distribute fill proportionally based on each resting order's share of total level depth
pub struct ProRataAllocator;

impl Allocator for ProRataAllocator {
    fn allocate(
        &self,
        order_ids: &[OrderId],
        orders: &HashMap<OrderId, Order>,
        available_demand_qty: Quantity,
    ) -> Vec<AllocationShare> {
        let mut allocations = Vec::new();
        if available_demand_qty.is_zero() || order_ids.is_empty() {
            return allocations;
        }

        let mut total_level_qty: u64 = 0;
        for &oid in order_ids {
            if let Some(order) = orders.get(&oid) {
                total_level_qty += order.visible_quantity.raw();
            }
        }

        if total_level_qty == 0 {
            return allocations;
        }

        // If demand exceeds total volume, everyone gets their full visible qty
        if available_demand_qty.raw() >= total_level_qty {
            for &oid in order_ids {
                if let Some(order) = orders.get(&oid) {
                    if !order.visible_quantity.is_zero() {
                        allocations.push(AllocationShare {
                            order_id: oid,
                            allocated_quantity: order.visible_quantity,
                        });
                    }
                }
            }
            return allocations;
        }

        // Proportional distribution with largest-remainder rounding
        let mut allocated_sum: u64 = 0;
        let mut fractions: Vec<(OrderId, u64, u64)> = Vec::new(); // (oid, integer_part, remainder)

        for &oid in order_ids {
            if let Some(order) = orders.get(&oid) {
                let q = order.visible_quantity.raw();
                let product = (available_demand_qty.raw() as u128) * (q as u128);
                let integer_share = (product / total_level_qty as u128) as u64;
                let remainder = (product % total_level_qty as u128) as u64;

                allocations.push(AllocationShare {
                    order_id: oid,
                    allocated_quantity: Quantity::from_raw(integer_share),
                });
                allocated_sum += integer_share;
                fractions.push((oid, integer_share, remainder));
            }
        }

        // Distribute remaining lots by largest remainder
        let mut remaining_lots = available_demand_qty.raw().saturating_sub(allocated_sum);
        fractions.sort_by(|a, b| b.2.cmp(&a.2));

        for (oid, _, _) in fractions {
            if remaining_lots == 0 {
                break;
            }
            if let Some(alloc) = allocations.iter_mut().find(|a| a.order_id == oid) {
                alloc.allocated_quantity = alloc.allocated_quantity + Quantity::from_raw(1);
                remaining_lots -= 1;
            }
        }

        allocations
    }
}
