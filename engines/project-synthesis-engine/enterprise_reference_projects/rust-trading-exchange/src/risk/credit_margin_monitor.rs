use std::collections::HashMap;
use crate::core::types::{InstrumentId, ParticipantId, Price, Quantity, Side};

#[derive(Debug, Clone, PartialEq)]
pub enum MarginViolationType {
    ExcessiveLeverage { current_ratio: f64, max_allowed: f64 },
    InsufficientCreditCollateral { required_cents: i64, available_cents: i64 },
    ConcentrationLimitBreached { instrument: InstrumentId, share: f64, max_share: f64 },
    StressGridDeficit { scenario: String, potential_loss_cents: i64, buffer_cents: i64 },
}

#[derive(Debug, Clone)]
pub struct ParticipantCreditAccount {
    pub participant_id: ParticipantId,
    pub equity_balance_cents: i64,       // Cash + acceptable collateral value
    pub maintenance_margin_cents: i64,   // Regulatory minimum equity required
    pub max_leverage_ratio: f64,        // e.g. 10.0 for 10x max gross leverage
    pub max_single_name_concentration: f64, // e.g. 0.35 (35% max in one instrument)
    pub net_positions: HashMap<InstrumentId, i64>, // Signed quantity (positive = long, negative = short)
    pub mark_to_market_prices: HashMap<InstrumentId, Price>,
}

impl ParticipantCreditAccount {
    pub fn new(participant_id: ParticipantId, equity_balance_cents: i64, max_leverage: f64) -> Self {
        Self {
            participant_id,
            equity_balance_cents,
            maintenance_margin_cents: (equity_balance_cents as f64 * 0.20) as i64, // 20% maintenance requirement
            max_leverage_ratio: max_leverage,
            max_single_name_concentration: 0.35,
            net_positions: HashMap::new(),
            mark_to_market_prices: HashMap::new(),
        }
    }

    pub fn set_price(&mut self, instrument: InstrumentId, price: Price) {
        self.mark_to_market_prices.insert(instrument, price);
    }

    pub fn update_position(&mut self, instrument: InstrumentId, delta_qty: i64) {
        let pos = self.net_positions.entry(instrument).or_insert(0);
        *pos += delta_qty;
    }

    pub fn gross_notional_exposure_cents(&self) -> i64 {
        let mut total = 0i64;
        for (inst, &qty) in &self.net_positions {
            if let Some(&price) = self.mark_to_market_prices.get(inst) {
                let notional = (qty.abs() as f64 * price.to_f64() * 100.0) as i64;
                total += notional;
            }
        }
        total
    }
}

pub struct PreTradeCreditMarginEngine {
    accounts: HashMap<ParticipantId, ParticipantCreditAccount>,
    stress_scenarios: Vec<(&'static str, f64)>, // Name and price shock fraction (e.g. -0.15 = -15%)
}

impl PreTradeCreditMarginEngine {
    pub fn new() -> Self {
        Self {
            accounts: HashMap::new(),
            stress_scenarios: vec![
                ("CRASH_MINUS_15_PCT", -0.15),
                ("CRASH_MINUS_8_PCT", -0.08),
                ("DIP_MINUS_4_PCT", -0.04),
                ("RALLY_PLUS_4_PCT", 0.04),
                ("RALLY_PLUS_8_PCT", 0.08),
                ("SURGE_PLUS_15_PCT", 0.15),
            ],
        }
    }

    pub fn register_account(&mut self, account: ParticipantCreditAccount) {
        self.accounts.insert(account.participant_id.clone(), account);
    }

    pub fn get_account_mut(&mut self, id: &ParticipantId) -> Option<&mut ParticipantCreditAccount> {
        self.accounts.get_mut(id)
    }

    /// Evaluates pre-trade margin credit check in ultra-low latency before an order hits the matching book.
    pub fn evaluate_pre_trade_order(
        &self,
        participant_id: &ParticipantId,
        instrument: &InstrumentId,
        side: Side,
        price: Price,
        quantity: Quantity,
    ) -> Result<f64, MarginViolationType> {
        let acct = match self.accounts.get(participant_id) {
            Some(a) => a,
            None => {
                return Err(MarginViolationType::InsufficientCreditCollateral {
                    required_cents: 1,
                    available_cents: 0,
                })
            }
        };

        let order_notional_cents = (quantity.raw() as f64 * price.to_f64() * 100.0) as i64;
        let current_gross = acct.gross_notional_exposure_cents();
        let projected_gross = current_gross + order_notional_cents;

        // 1. Leverage Check
        let projected_leverage = projected_gross as f64 / acct.equity_balance_cents.max(1) as f64;
        if projected_leverage > acct.max_leverage_ratio {
            return Err(MarginViolationType::ExcessiveLeverage {
                current_ratio: projected_leverage,
                max_allowed: acct.max_leverage_ratio,
            });
        }

        // 2. Concentration Check
        let current_instrument_pos = *acct.net_positions.get(instrument).unwrap_or(&0);
        let signed_delta = if side.is_buy() { quantity.raw() as i64 } else { -(quantity.raw() as i64) };
        let projected_instrument_pos = (current_instrument_pos + signed_delta).abs();
        let projected_instrument_notional = (projected_instrument_pos as f64 * price.to_f64() * 100.0) as i64;

        if projected_gross > 0 {
            let share = projected_instrument_notional as f64 / projected_gross as f64;
            if share > acct.max_single_name_concentration && projected_gross > acct.equity_balance_cents {
                return Err(MarginViolationType::ConcentrationLimitBreached {
                    instrument: instrument.clone(),
                    share,
                    max_share: acct.max_single_name_concentration,
                });
            }
        }

        // 3. Span-like Stress Grid Simulation
        for &(scen_name, shock) in &self.stress_scenarios {
            let mut projected_loss_cents = 0i64;

            for (inst, &pos) in &acct.net_positions {
                let mkt_price = acct.mark_to_market_prices.get(inst).copied().unwrap_or(price);
                let pnl = (pos as f64 * (mkt_price.to_f64() * shock) * 100.0) as i64;
                if pnl < 0 {
                    projected_loss_cents += pnl.abs();
                }
            }

            // Include incoming order delta
            let order_pnl = (signed_delta as f64 * (price.to_f64() * shock) * 100.0) as i64;
            if order_pnl < 0 {
                projected_loss_cents += order_pnl.abs();
            }

            // Margin buffer = Equity - Maintenance Margin
            let available_buffer = acct.equity_balance_cents - acct.maintenance_margin_cents;
            if projected_loss_cents > available_buffer {
                return Err(MarginViolationType::StressGridDeficit {
                    scenario: scen_name.to_string(),
                    potential_loss_cents: projected_loss_cents,
                    buffer_cents: available_buffer,
                });
            }
        }

        // Return current margin utilization fraction (e.g. 0.42 for 42%)
        let margin_utilization = projected_leverage / acct.max_leverage_ratio;
        Ok(margin_utilization)
    }
}
