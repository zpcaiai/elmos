use crate::core::types::{Price, Quantity, Side};

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct MicrostructureSignals {
    pub kyles_lambda: f64,             // Price impact per unit volume (ticks/unit)
    pub amihud_illiquidity: f64,       // |Return| / Dollar Volume
    pub order_flow_imbalance: i64,     // Net quantity delta across top-of-book shifts
    pub effective_spread_bps: f64,     // 2 * |Trade Price - Midpoint| / Midpoint * 10,000
    pub realized_spread_bps: f64,      // 2 * Sign * (Trade Price - Midpoint_t+tau) / Midpoint * 10,000
}

#[derive(Debug, Clone, Copy)]
pub struct TopOfBookQuote {
    pub bid_price: Price,
    pub bid_qty: Quantity,
    pub ask_price: Price,
    pub ask_qty: Quantity,
}

pub struct MarketMicrostructureEngine {
    last_quote: Option<TopOfBookQuote>,
    rolling_price_deltas: Vec<f64>,
    rolling_volumes: Vec<f64>,
    window_capacity: usize,
}

impl MarketMicrostructureEngine {
    pub fn new(window_capacity: usize) -> Self {
        Self {
            last_quote: None,
            rolling_price_deltas: Vec::with_capacity(window_capacity),
            rolling_volumes: Vec::with_capacity(window_capacity),
            window_capacity: window_capacity.max(10),
        }
    }

    /// Computes multi-level Order Flow Imbalance (OFI) from successive top-of-book snapshots.
    /// Follows Cont, Kukanov & Stoikov (2014) formulation:
    /// $\Delta OFI_t = I_{Bid} - I_{Ask}$
    pub fn update_quote_and_compute_ofi(&mut self, current: TopOfBookQuote) -> i64 {
        let ofi = match self.last_quote {
            None => 0i64,
            Some(prev) => {
                let bid_component = if current.bid_price > prev.bid_price {
                    current.bid_qty.raw() as i64
                } else if current.bid_price == prev.bid_price {
                    current.bid_qty.raw() as i64 - prev.bid_qty.raw() as i64
                } else {
                    -(prev.bid_qty.raw() as i64)
                };

                let ask_component = if current.ask_price < prev.ask_price {
                    current.ask_qty.raw() as i64
                } else if current.ask_price == prev.ask_price {
                    current.ask_qty.raw() as i64 - prev.ask_qty.raw() as i64
                } else {
                    -(prev.ask_qty.raw() as i64)
                };

                bid_component - ask_component
            }
        };

        self.last_quote = Some(current);
        ofi
    }

    /// Ingests a trade execution and calculates Kyle's Lambda price impact and spreads.
    pub fn record_trade_and_compute_signals(
        &mut self,
        trade_price: Price,
        trade_qty: Quantity,
        side: Side,
        current_quote: TopOfBookQuote,
        future_midpoint: Option<Price>,
    ) -> MicrostructureSignals {
        let mid_price = (current_quote.bid_price.to_f64() + current_quote.ask_price.to_f64()) / 2.0;
        let trade_p = trade_price.to_f64();
        let trade_q = trade_qty.raw() as f64;

        // Effective Spread (basis points)
        let eff_spread_bps = if mid_price > 0.0 {
            2.0 * (trade_p - mid_price).abs() / mid_price * 10_000.0
        } else {
            0.0
        };

        // Realized Spread (basis points)
        let realized_spread_bps = match future_midpoint {
            Some(f_mid) if mid_price > 0.0 => {
                let direction = if side.is_buy() { 1.0 } else { -1.0 };
                2.0 * direction * (trade_p - f_mid.to_f64()) / mid_price * 10_000.0
            }
            _ => eff_spread_bps,
        };

        // Kyle's Lambda price impact regression update
        let price_delta = (trade_p - mid_price).abs();
        if self.rolling_price_deltas.len() >= self.window_capacity {
            self.rolling_price_deltas.remove(0);
            self.rolling_volumes.remove(0);
        }
        self.rolling_price_deltas.push(price_delta);
        self.rolling_volumes.push(trade_q);

        let sum_delta: f64 = self.rolling_price_deltas.iter().sum();
        let sum_vol: f64 = self.rolling_volumes.iter().sum();
        let kyles_lambda = if sum_vol > 0.0 { sum_delta / sum_vol } else { 0.0 };

        // Amihud illiquidity: |Return| / Dollar Volume
        let dollar_volume = trade_p * trade_q;
        let amihud = if dollar_volume > 0.0 {
            (price_delta / mid_price.max(1.0)) / dollar_volume * 1_000_000.0
        } else {
            0.0
        };

        let ofi = self.update_quote_and_compute_ofi(current_quote);

        MicrostructureSignals {
            kyles_lambda,
            amihud_illiquidity: amihud,
            order_flow_imbalance: ofi,
            effective_spread_bps: eff_spread_bps,
            realized_spread_bps,
        }
    }
}
