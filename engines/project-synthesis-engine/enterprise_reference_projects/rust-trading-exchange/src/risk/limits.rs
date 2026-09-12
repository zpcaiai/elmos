use crate::core::types::*;

#[derive(Debug, Clone)]
pub struct RiskLimitConfig {
    pub max_order_quantity: Quantity,
    pub max_order_value: Money,
    pub max_daily_notional: Money,
    pub max_open_orders: usize,
    pub price_collar_percentage: f64, // e.g. 0.05 for 5% deviation from reference
    pub rate_limit_window_secs: u64,
    pub max_orders_per_window: usize,
}

impl Default for RiskLimitConfig {
    fn default() -> Self {
        RiskLimitConfig {
            max_order_quantity: Quantity::from_raw(1_000_000), // 1M units
            max_order_value: Money(50_000_000_00),            // $50,000,000.00
            max_daily_notional: Money(500_000_000_00),        // $500,000,000.00
            max_open_orders: 10_000,
            price_collar_percentage: 0.05,                    // 5% price collar
            rate_limit_window_secs: 1,
            max_orders_per_window: 1_000,                     // 1,000 msg/sec
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct RiskAccountState {
    pub open_orders_count: usize,
    pub daily_accumulated_notional: Money,
    pub message_timestamps: Vec<u64>,
}

impl RiskAccountState {
    pub fn new() -> Self {
        RiskAccountState {
            open_orders_count: 0,
            daily_accumulated_notional: Money::ZERO,
            message_timestamps: Vec::new(),
        }
    }

    pub fn record_order_submission(&mut self, order_val: Money, timestamp_ns: u64) {
        self.open_orders_count += 1;
        self.daily_accumulated_notional = Money(self.daily_accumulated_notional.0 + order_val.0);
        self.message_timestamps.push(timestamp_ns);
    }

    pub fn record_order_closed(&mut self) {
        if self.open_orders_count > 0 {
            self.open_orders_count -= 1;
        }
    }

    pub fn prune_rate_limit_window(&mut self, current_time_ns: u64, window_duration_ns: u64) {
        let cutoff = current_time_ns.saturating_sub(window_duration_ns);
        self.message_timestamps.retain(|&t| t >= cutoff);
    }
}
