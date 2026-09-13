use crate::core::types::*;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MarketState {
    PreOpen,
    ContinuousTrading,
    VolatilityAuction,
    HaltedLevel1,
    HaltedLevel2,
    HaltedLevel3DayClose,
}

#[derive(Debug, Clone)]
pub struct CircuitBreakerConfig {
    pub level1_drop_pct: f64, // e.g. 0.07 (7% drop -> 15 min halt)
    pub level2_drop_pct: f64, // e.g. 0.13 (13% drop -> 15 min halt)
    pub level3_drop_pct: f64, // e.g. 0.20 (20% drop -> halt rest of day)
    pub halt_duration_secs: u64,
    pub luld_band_pct: f64,  // Limit-up / limit-down continuous band e.g. 5%
}

impl Default for CircuitBreakerConfig {
    fn default() -> Self {
        CircuitBreakerConfig {
            level1_drop_pct: 0.07,
            level2_drop_pct: 0.13,
            level3_drop_pct: 0.20,
            halt_duration_secs: 900, // 15 minutes
            luld_band_pct: 0.05,
        }
    }
}

pub struct CircuitBreaker {
    pub instrument_id: InstrumentId,
    pub config: CircuitBreakerConfig,
    pub baseline_price: Price,
    pub state: MarketState,
    pub halt_start_ns: u64,
    pub upper_price_band: Price,
    pub lower_price_band: Price,
}

impl CircuitBreaker {
    pub fn new(instrument_id: InstrumentId, baseline_price: Price, config: CircuitBreakerConfig) -> Self {
        let (lower, upper) = Self::compute_bands(baseline_price, config.luld_band_pct);
        CircuitBreaker {
            instrument_id,
            config,
            baseline_price,
            state: MarketState::ContinuousTrading,
            halt_start_ns: 0,
            upper_price_band: upper,
            lower_price_band: lower,
        }
    }

    fn compute_bands(center: Price, pct: f64) -> (Price, Price) {
        let delta = (center.raw() as f64 * pct).round() as i64;
        let lower = Price::from_raw((center.raw() - delta).max(1));
        let upper = Price::from_raw(center.raw() + delta);
        (lower, upper)
    }

    fn current_time_ns() -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64
    }

    /// Check if an incoming execution triggers volatility thresholds
    pub fn check_execution(&mut self, trade_price: Price) -> Option<MarketState> {
        if self.state == MarketState::HaltedLevel3DayClose {
            return Some(self.state);
        }

        let now_ns = Self::current_time_ns();

        // Check if currently halted and halt period expired
        if matches!(self.state, MarketState::HaltedLevel1 | MarketState::HaltedLevel2 | MarketState::VolatilityAuction) {
            let elapsed_secs = (now_ns.saturating_sub(self.halt_start_ns)) / 1_000_000_000;
            if elapsed_secs >= self.config.halt_duration_secs {
                self.state = MarketState::ContinuousTrading;
                // Re-anchor bands
                let (lower, upper) = Self::compute_bands(trade_price, self.config.luld_band_pct);
                self.lower_price_band = lower;
                self.upper_price_band = upper;
            } else {
                return Some(self.state);
            }
        }

        let baseline = self.baseline_price.raw() as f64;
        if baseline <= 0.0 {
            return None;
        }

        let current = trade_price.raw() as f64;
        let drop_pct = (baseline - current) / baseline;

        if drop_pct >= self.config.level3_drop_pct {
            self.state = MarketState::HaltedLevel3DayClose;
            self.halt_start_ns = now_ns;
            return Some(self.state);
        } else if drop_pct >= self.config.level2_drop_pct && self.state != MarketState::HaltedLevel2 {
            self.state = MarketState::HaltedLevel2;
            self.halt_start_ns = now_ns;
            return Some(self.state);
        } else if drop_pct >= self.config.level1_drop_pct && self.state != MarketState::HaltedLevel1 {
            self.state = MarketState::HaltedLevel1;
            self.halt_start_ns = now_ns;
            return Some(self.state);
        }

        // Limit-Up / Limit-Down check
        if trade_price < self.lower_price_band || trade_price > self.upper_price_band {
            self.state = MarketState::VolatilityAuction;
            self.halt_start_ns = now_ns;
            return Some(self.state);
        }

        None
    }

    pub fn is_trading_allowed(&self) -> bool {
        matches!(self.state, MarketState::ContinuousTrading)
    }
}
