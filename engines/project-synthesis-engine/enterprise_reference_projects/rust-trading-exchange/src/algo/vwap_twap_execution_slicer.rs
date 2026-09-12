use crate::core::types::{InstrumentId, OrderId, Price, Quantity, Side};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutionStrategy {
    Vwap,
    Twap,
    PercentOfVolume { participation_rate_bps: u32 }, // e.g. 1000 = 10%
    ImplementationShortfall,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutionUrgency {
    Passive,    // Post inside spread (at best bid/ask)
    Neutral,    // Peg to midpoint
    Aggressive, // Take liquidity / cross the spread
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SliceStatus {
    Pending,
    Active,
    Filled,
    PartiallyFilled,
    Cancelled,
    CollarHalted,
}

#[derive(Debug, Clone)]
pub struct ChildOrderSlice {
    pub slice_id: OrderId,
    pub bucket_index: usize,
    pub target_quantity: Quantity,
    pub filled_quantity: Quantity,
    pub limit_price: Price,
    pub filled_notional: f64,
    pub status: SliceStatus,
}

impl ChildOrderSlice {
    pub fn new(slice_id: OrderId, bucket_index: usize, target_quantity: Quantity, limit_price: Price) -> Self {
        Self {
            slice_id,
            bucket_index,
            target_quantity,
            filled_quantity: Quantity::ZERO,
            limit_price,
            filled_notional: 0.0,
            status: SliceStatus::Pending,
        }
    }

    pub fn average_fill_price(&self) -> Option<Price> {
        if self.filled_quantity.is_zero() {
            None
        } else {
            Some(Price::from_f64(self.filled_notional / self.filled_quantity.raw() as f64))
        }
    }
}

/// Represents a standardized 13-period intraday trading schedule (e.g., 9:30 to 16:00 in 30-min intervals)
#[derive(Debug, Clone)]
pub struct IntradayVolumeProfile {
    pub period_weights: Vec<f64>, // Normalized fractions summing to 1.0
}

impl IntradayVolumeProfile {
    /// Constructs a standard empirical U-shaped intraday volume distribution for liquid equities
    pub fn standard_u_curve() -> Self {
        // High at open, dip at lunch, elevated at close
        let raw_weights = vec![
            0.14, 0.10, 0.08, 0.06, 0.05, 0.05, 0.04, 0.05, 0.06, 0.07, 0.09, 0.11, 0.15,
        ];
        let sum: f64 = raw_weights.iter().sum();
        let normalized = raw_weights.iter().map(|w| w / sum).collect();
        Self { period_weights: normalized }
    }

    /// Constructs an even (flat) volume distribution for TWAP execution
    pub fn flat_profile(periods: usize) -> Self {
        assert!(periods > 0, "Periods must be > 0");
        let weight = 1.0 / periods as f64;
        Self {
            period_weights: vec![weight; periods],
        }
    }
}

#[derive(Debug, Clone)]
pub struct AlgoParentOrder {
    pub parent_id: String,
    pub instrument_id: InstrumentId,
    pub side: Side,
    pub total_quantity: Quantity,
    pub filled_quantity: Quantity,
    pub arrival_decision_price: Price,
    pub strategy: ExecutionStrategy,
    pub urgency: ExecutionUrgency,
    pub max_adverse_deviation_bps: u32, // e.g. 50 bps = 0.50%
    pub total_filled_notional: f64,
}

impl AlgoParentOrder {
    pub fn new(
        parent_id: impl Into<String>,
        instrument_id: InstrumentId,
        side: Side,
        total_quantity: Quantity,
        arrival_price: Price,
        strategy: ExecutionStrategy,
        urgency: ExecutionUrgency,
    ) -> Self {
        Self {
            parent_id: parent_id.into(),
            instrument_id,
            side,
            total_quantity,
            filled_quantity: Quantity::ZERO,
            arrival_decision_price: arrival_price,
            strategy,
            urgency,
            max_adverse_deviation_bps: 50, // Default 50 bps collar
            total_filled_notional: 0.0,
        }
    }

    pub fn execution_vwap(&self) -> Option<Price> {
        if self.filled_quantity.is_zero() {
            None
        } else {
            Some(Price::from_f64(self.total_filled_notional / self.filled_quantity.raw() as f64))
        }
    }
}

pub struct VwapTwapExecutionSlicer {
    pub parent_order: AlgoParentOrder,
    pub volume_profile: IntradayVolumeProfile,
    pub current_bucket_index: usize,
    pub child_slices: Vec<ChildOrderSlice>,
    pub market_cumulative_volume: u64,
    pub market_cumulative_notional: f64,
    next_slice_seq: u64,
}

impl VwapTwapExecutionSlicer {
    pub fn new(parent_order: AlgoParentOrder, volume_profile: IntradayVolumeProfile) -> Self {
        let periods = volume_profile.period_weights.len();
        let mut slicer = Self {
            parent_order,
            volume_profile,
            current_bucket_index: 0,
            child_slices: Vec::with_capacity(periods),
            market_cumulative_volume: 0,
            market_cumulative_notional: 0.0,
            next_slice_seq: 1,
        };
        slicer.generate_initial_schedule();
        slicer
    }

    fn generate_initial_schedule(&mut self) {
        let total_qty = self.parent_order.total_quantity.raw() as f64;
        let arrival_price = self.parent_order.arrival_decision_price;
        let mut allocated = 0u64;
        let periods = self.volume_profile.period_weights.len();

        for i in 0..periods {
            let weight = self.volume_profile.period_weights[i];
            let mut slice_qty = (total_qty * weight).round() as u64;
            if i == periods - 1 {
                // Ensure exact total allocation by adjusting remainder in last period
                let remaining = (self.parent_order.total_quantity.raw()).saturating_sub(allocated);
                slice_qty = remaining;
            }
            allocated += slice_qty;

            let slice = ChildOrderSlice::new(
                OrderId(self.next_slice_seq),
                i,
                Quantity::from_raw(slice_qty),
                arrival_price,
            );
            self.next_slice_seq += 1;
            self.child_slices.push(slice);
        }
    }

    /// Feeds an external market trade to track benchmark Market VWAP
    pub fn record_market_trade(&mut self, price: Price, quantity: Quantity) {
        let qty = quantity.raw();
        self.market_cumulative_volume += qty;
        self.market_cumulative_notional += price.to_f64() * qty as f64;
    }

    pub fn market_vwap(&self) -> Option<Price> {
        if self.market_cumulative_volume == 0 {
            None
        } else {
            Some(Price::from_f64(self.market_cumulative_notional / self.market_cumulative_volume as f64))
        }
    }

    /// Verifies whether prevailing market price has breached the adverse price collar limit
    pub fn is_price_collar_breached(&self, current_market_price: Price) -> bool {
        let arrival = self.parent_order.arrival_decision_price.to_f64();
        let current = current_market_price.to_f64();
        let max_dev_fraction = self.parent_order.max_adverse_deviation_bps as f64 / 10000.0;

        match self.parent_order.side {
            Side::Buy => {
                // If buying, adverse move is price surging above arrival + tolerance
                (current - arrival) / arrival > max_dev_fraction
            }
            Side::Sell => {
                // If selling, adverse move is price crashing below arrival - tolerance
                (arrival - current) / arrival > max_dev_fraction
            }
        }
    }

    /// Releases or adjusts the active child order for the current time bucket
    pub fn activate_current_bucket(&mut self, current_best_bid: Price, current_best_ask: Price) -> Option<&mut ChildOrderSlice> {
        if self.current_bucket_index >= self.child_slices.len() {
            return None;
        }

        let mid_f64 = (current_best_bid.to_f64() + current_best_ask.to_f64()) / 2.0;
        let midpoint = Price::from_f64(mid_f64);
        let collar_breached = self.is_price_collar_breached(midpoint);

        let slice = &mut self.child_slices[self.current_bucket_index];

        // If market price violates collar, halt child slice release
        if collar_breached {
            slice.status = SliceStatus::CollarHalted;
            return Some(slice);
        }

        // Adjust limit price according to execution urgency
        slice.limit_price = match (self.parent_order.side, self.parent_order.urgency) {
            (Side::Buy, ExecutionUrgency::Passive) => current_best_bid,
            (Side::Buy, ExecutionUrgency::Neutral) => midpoint,
            (Side::Buy, ExecutionUrgency::Aggressive) => current_best_ask,
            (Side::Sell, ExecutionUrgency::Passive) => current_best_ask,
            (Side::Sell, ExecutionUrgency::Neutral) => midpoint,
            (Side::Sell, ExecutionUrgency::Aggressive) => current_best_bid,
        };

        slice.status = SliceStatus::Active;
        Some(slice)
    }

    /// Records execution of a child slice fill and updates parent order metrics
    pub fn record_child_fill(&mut self, slice_index: usize, filled_qty: Quantity, exec_price: Price) {
        if slice_index >= self.child_slices.len() {
            return;
        }

        let notional = exec_price.to_f64() * filled_qty.raw() as f64;
        let slice = &mut self.child_slices[slice_index];
        slice.filled_quantity = slice.filled_quantity.checked_add(filled_qty).unwrap_or(slice.filled_quantity);
        slice.filled_notional += notional;

        if slice.filled_quantity >= slice.target_quantity {
            slice.status = SliceStatus::Filled;
        } else {
            slice.status = SliceStatus::PartiallyFilled;
        }

        self.parent_order.filled_quantity = self.parent_order.filled_quantity.checked_add(filled_qty).unwrap_or(self.parent_order.filled_quantity);
        self.parent_order.total_filled_notional += notional;
    }

    /// Advances to next time period bucket and rebalances any unfilled remainder across future periods
    pub fn advance_to_next_bucket(&mut self) {
        if self.current_bucket_index < self.child_slices.len() {
            let current_slice = &self.child_slices[self.current_bucket_index];
            let unfilled = current_slice.target_quantity.raw().saturating_sub(current_slice.filled_quantity.raw());

            self.current_bucket_index += 1;

            // If there was an unfilled shortfall and future buckets remain, rebalance
            let remaining_periods = self.child_slices.len().saturating_sub(self.current_bucket_index);
            if unfilled > 0 && remaining_periods > 0 {
                let add_per_period = (unfilled as f64 / remaining_periods as f64).round() as u64;
                for i in self.current_bucket_index..self.child_slices.len() {
                    let s = &mut self.child_slices[i];
                    s.target_quantity = Quantity::from_raw(s.target_quantity.raw() + add_per_period);
                }
            }
        }
    }

    /// Calculates tracking error between Parent Execution VWAP and Market Benchmark VWAP in basis points
    pub fn tracking_error_bps(&self) -> Option<f64> {
        let exec_vwap = self.parent_order.execution_vwap()?.to_f64();
        let mkt_vwap = self.market_vwap()?.to_f64();

        // For Buy: Lower execution than market is positive performance (-bps slippage)
        let bps = match self.parent_order.side {
            Side::Buy => ((exec_vwap - mkt_vwap) / mkt_vwap) * 10000.0,
            Side::Sell => ((mkt_vwap - exec_vwap) / mkt_vwap) * 10000.0,
        };
        Some(bps)
    }

    /// Calculates Implementation Shortfall / Slippage relative to Arrival Decision Price
    pub fn arrival_slippage_bps(&self) -> Option<f64> {
        let exec_vwap = self.parent_order.execution_vwap()?.to_f64();
        let arrival = self.parent_order.arrival_decision_price.to_f64();

        let bps = match self.parent_order.side {
            Side::Buy => ((exec_vwap - arrival) / arrival) * 10000.0,
            Side::Sell => ((arrival - exec_vwap) / arrival) * 10000.0,
        };
        Some(bps)
    }
}
