use crate::core::types::*;
use crate::core::order::Order;
use crate::risk::limits::{RiskLimitConfig, RiskAccountState};
use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq)]
pub enum RiskViolation {
    OrderQuantityExceeded { limit: Quantity, requested: Quantity },
    OrderValueExceeded { limit: Money, requested: Money },
    DailyNotionalExceeded { limit: Money, projected: Money },
    MaxOpenOrdersExceeded { limit: usize, current: usize },
    PriceCollarBreached { reference_price: Price, order_price: Price, max_deviation_pct: f64 },
    RateLimitExceeded { limit: usize, window_secs: u64 },
    TradingHalted { reason: String },
}

pub struct PreTradeRiskEngine {
    configs: HashMap<ParticipantId, RiskLimitConfig>,
    default_config: RiskLimitConfig,
    account_states: HashMap<ParticipantId, RiskAccountState>,
    reference_prices: HashMap<InstrumentId, Price>,
}

impl PreTradeRiskEngine {
    pub fn new(default_config: RiskLimitConfig) -> Self {
        PreTradeRiskEngine {
            configs: HashMap::new(),
            default_config,
            account_states: HashMap::new(),
            reference_prices: HashMap::new(),
        }
    }

    pub fn set_participant_config(&mut self, pid: ParticipantId, cfg: RiskLimitConfig) {
        self.configs.insert(pid, cfg);
    }

    pub fn update_reference_price(&mut self, instrument: InstrumentId, price: Price) {
        self.reference_prices.insert(instrument, price);
    }

    fn current_time_ns() -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64
    }

    pub fn validate_order(&mut self, order: &Order) -> Result<(), RiskViolation> {
        let pid = &order.participant_id;
        let config = self.configs.get(pid).unwrap_or(&self.default_config);
        let state = self.account_states.entry(pid.clone()).or_insert_with(RiskAccountState::new);

        let now_ns = Self::current_time_ns();
        let window_ns = config.rate_limit_window_secs * 1_000_000_000;
        state.prune_rate_limit_window(now_ns, window_ns);

        // 1. Rate Limiting Check
        if state.message_timestamps.len() >= config.max_orders_per_window {
            return Err(RiskViolation::RateLimitExceeded {
                limit: config.max_orders_per_window,
                window_secs: config.rate_limit_window_secs,
            });
        }

        // 2. Max Open Orders Check
        if state.open_orders_count >= config.max_open_orders {
            return Err(RiskViolation::MaxOpenOrdersExceeded {
                limit: config.max_open_orders,
                current: state.open_orders_count,
            });
        }

        // 3. Max Order Quantity Check
        if order.initial_quantity > config.max_order_quantity {
            return Err(RiskViolation::OrderQuantityExceeded {
                limit: config.max_order_quantity,
                requested: order.initial_quantity,
            });
        }

        // 4. Order Value Calculation & Check
        let order_val = match order.order_type {
            OrderType::Market => {
                // If market order, evaluate using reference price
                if let Some(&ref_p) = self.reference_prices.get(&order.instrument_id) {
                    Money::from_price_quantity(ref_p, order.initial_quantity)
                } else {
                    Money::ZERO
                }
            }
            _ => Money::from_price_quantity(order.price, order.initial_quantity),
        };

        if order_val > config.max_order_value {
            return Err(RiskViolation::OrderValueExceeded {
                limit: config.max_order_value,
                requested: order_val,
            });
        }

        // 5. Daily Notional Accumulation Check
        let projected_notional = Money(state.daily_accumulated_notional.0 + order_val.0);
        if projected_notional > config.max_daily_notional {
            return Err(RiskViolation::DailyNotionalExceeded {
                limit: config.max_daily_notional,
                projected: projected_notional,
            });
        }

        // 6. Fat-Finger Price Collar Check
        if matches!(order.order_type, OrderType::Limit | OrderType::PostOnly) {
            if let Some(&ref_p) = self.reference_prices.get(&order.instrument_id) {
                if ref_p.is_positive() {
                    let diff = order.price.abs_diff(ref_p).raw() as f64;
                    let deviation = diff / (ref_p.raw() as f64);
                    if deviation > config.price_collar_percentage {
                        return Err(RiskViolation::PriceCollarBreached {
                            reference_price: ref_p,
                            order_price: order.price,
                            max_deviation_pct: config.price_collar_percentage * 100.0,
                        });
                    }
                }
            }
        }

        // All pre-trade risk checks passed! Record order state
        state.record_order_submission(order_val, now_ns);
        Ok(())
    }

    pub fn on_order_closed(&mut self, pid: &ParticipantId) {
        if let Some(state) = self.account_states.get_mut(pid) {
            state.record_order_closed();
        }
    }
}
