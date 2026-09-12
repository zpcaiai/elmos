use crate::core::types::{InstrumentId, Price, Quantity, Side};
use std::collections::{HashMap, VecDeque};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum MmpBreachType {
    VolumeExceeded,
    TradeCountExceeded,
    DeltaExposureExceeded,
    VegaExposureExceeded,
    ManualEmergencyFreeze,
}

#[derive(Debug, Clone)]
pub struct MmpConfig {
    pub window_millis: u64,
    pub max_volume: Quantity,
    pub max_trade_count: u32,
    pub max_delta_lots: i64,
    pub auto_reset_millis: Option<u64>,
}

impl Default for MmpConfig {
    fn default() -> Self {
        Self {
            window_millis: 1000, // 1 second rolling window
            max_volume: Quantity::from_raw(5000),
            max_trade_count: 50,
            max_delta_lots: 2500,
            auto_reset_millis: None, // Requires manual explicit unfreeze
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MmpStatus {
    Active,
    Frozen {
        breach_type: MmpBreachType,
        triggered_at_nanos: u64,
        auto_reset_at_nanos: Option<u64>,
    },
}

#[derive(Debug, Clone)]
pub struct MmpExecutionRecord {
    pub timestamp_nanos: u64,
    pub instrument_id: InstrumentId,
    pub side: Side,
    pub quantity: Quantity,
    pub price: Price,
}

#[derive(Debug, Clone)]
pub struct MmpAccountState {
    pub account_id: u32,
    pub config: MmpConfig,
    pub status: MmpStatus,
    pub execution_window: VecDeque<MmpExecutionRecord>,
    pub total_lifetime_fills: u64,
    pub total_lifetime_breaches: u32,
}

impl MmpAccountState {
    pub fn new(account_id: u32, config: MmpConfig) -> Self {
        Self {
            account_id,
            config,
            status: MmpStatus::Active,
            execution_window: VecDeque::new(),
            total_lifetime_fills: 0,
            total_lifetime_breaches: 0,
        }
    }

    pub fn is_frozen(&self, current_time_nanos: u64) -> bool {
        match self.status {
            MmpStatus::Active => false,
            MmpStatus::Frozen { auto_reset_at_nanos, .. } => {
                if let Some(reset_time) = auto_reset_at_nanos {
                    current_time_nanos < reset_time
                } else {
                    true
                }
            }
        }
    }
}

/// Market Maker Protection (MMP) Guardian Engine.
/// Protects liquidity providers from toxic flow bursts and execution avalanche events.
pub struct MarketMakerProtectionEngine {
    accounts: HashMap<u32, MmpAccountState>,
}

impl Default for MarketMakerProtectionEngine {
    fn default() -> Self {
        Self::new()
    }
}

impl MarketMakerProtectionEngine {
    pub fn new() -> Self {
        Self {
            accounts: HashMap::new(),
        }
    }

    pub fn register_account(&mut self, account_id: u32, config: MmpConfig) {
        self.accounts.insert(account_id, MmpAccountState::new(account_id, config));
    }

    /// Ingests a new execution fill and evaluates rolling window limits.
    /// Returns Some(MmpBreachType) if a protection limit is tripped.
    pub fn on_execution(
        &mut self,
        account_id: u32,
        instrument_id: InstrumentId,
        side: Side,
        quantity: Quantity,
        price: Price,
        timestamp_nanos: u64,
    ) -> Option<MmpBreachType> {
        let state = self.accounts.get_mut(&account_id)?;

        let now = timestamp_nanos;

        // Check if already frozen
        if state.is_frozen(now) {
            return None;
        }

        // Evict expired executions older than rolling window
        let window_nanos = state.config.window_millis * 1_000_000;
        let cutoff = now.saturating_sub(window_nanos);

        while let Some(front) = state.execution_window.front() {
            if front.timestamp_nanos < cutoff {
                state.execution_window.pop_front();
            } else {
                break;
            }
        }

        // Record execution
        state.execution_window.push_back(MmpExecutionRecord {
            timestamp_nanos: now,
            instrument_id,
            side,
            quantity,
            price,
        });

        state.total_lifetime_fills += 1;

        // Compute rolling aggregates
        let mut total_vol = 0u64;
        let mut net_delta = 0i64;
        let trade_count = state.execution_window.len() as u32;

        for exec in &state.execution_window {
            total_vol += exec.quantity.raw();
            match exec.side {
                Side::Buy => net_delta += exec.quantity.raw() as i64,
                Side::Sell => net_delta -= exec.quantity.raw() as i64,
            }
        }

        // Evaluate limits
        let breach = if trade_count > state.config.max_trade_count {
            Some(MmpBreachType::TradeCountExceeded)
        } else if total_vol > state.config.max_volume.raw() {
            Some(MmpBreachType::VolumeExceeded)
        } else if net_delta.abs() > state.config.max_delta_lots {
            Some(MmpBreachType::DeltaExposureExceeded)
        } else {
            None
        };

        if let Some(b) = breach {
            state.total_lifetime_breaches += 1;
            let auto_reset = state.config.auto_reset_millis.map(|ms| now + ms * 1_000_000);
            state.status = MmpStatus::Frozen {
                breach_type: b,
                triggered_at_nanos: now,
                auto_reset_at_nanos: auto_reset,
            };
        }

        breach
    }

    /// Manually resets a frozen market maker account after re-quoting authorization.
    pub fn reset_protection(&mut self, account_id: u32) -> Result<(), &'static str> {
        let state = self.accounts.get_mut(&account_id).ok_or("Account not registered")?;
        state.status = MmpStatus::Active;
        state.execution_window.clear();
        Ok(())
    }

    /// Queries the current protection status of an account.
    pub fn get_status(&self, account_id: u32, current_time_nanos: u64) -> Option<MmpStatus> {
        self.accounts.get(&account_id).map(|s| {
            if s.is_frozen(current_time_nanos) {
                s.status
            } else {
                MmpStatus::Active
            }
        })
    }
}
