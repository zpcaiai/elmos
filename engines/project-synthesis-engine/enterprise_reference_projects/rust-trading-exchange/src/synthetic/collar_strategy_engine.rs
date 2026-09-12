use std::f64::consts::PI;

pub enum OptionType {
    Call,
    Put,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct OptionGreeks {
    pub price: f64,
    pub delta: f64,
    pub gamma: f64,
    pub vega: f64,
    pub theta_per_day: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ZeroCostCollarResult {
    pub underlying_spot: f64,
    pub shares_count: u64,
    pub put_strike_floor: f64,
    pub put_premium: f64,
    pub call_strike_cap: f64,
    pub call_premium: f64,
    pub net_premium_outlay: f64, // Must be approx 0.00
    pub max_downside_pct: f64,
    pub max_upside_pct: f64,
    pub portfolio_net_delta: f64,
}

pub struct CollarStrategyEngine {
    risk_free_rate: f64, // e.g. 0.045 for 4.5% SOFR
}

impl CollarStrategyEngine {
    pub fn new(risk_free_rate: f64) -> Self {
        Self { risk_free_rate }
    }

    /// Standard Normal Cumulative Distribution Function $\Phi(x)$ via Abramowitz & Stegun 7.1.26
    pub fn normal_cdf(x: f64) -> f64 {
        let b1 = 0.319381530;
        let b2 = -0.356563782;
        let b3 = 1.781477937;
        let b4 = -1.821255978;
        let b5 = 1.330274429;
        let p = 0.2316419;
        let c2 = 1.0 / (2.0 * PI).sqrt();

        if x >= 0.0 {
            let t = 1.0 / (1.0 + p * x);
            let poly = t * (b1 + t * (b2 + t * (b3 + t * (b4 + t * b5))));
            1.0 - c2 * (-x * x / 2.0).exp() * poly
        } else {
            1.0 - Self::normal_cdf(-x)
        }
    }

    /// Standard Normal Probability Density Function $\phi(x)$
    pub fn normal_pdf(x: f64) -> f64 {
        (-0.5 * x * x).exp() / (2.0 * PI).sqrt()
    }

    /// Computes analytical Black-Scholes price and first/second-order Greeks.
    pub fn price_black_scholes(
        &self,
        spot: f64,
        strike: f64,
        time_to_maturity_years: f64,
        volatility: f64,
        option_type: OptionType,
    ) -> OptionGreeks {
        let t = time_to_maturity_years.max(0.0001);
        let vol = volatility.max(0.0001);
        let r = self.risk_free_rate;

        let sqrt_t = t.sqrt();
        let d1 = ((spot / strike).ln() + (r + 0.5 * vol * vol) * t) / (vol * sqrt_t);
        let d2 = d1 - vol * sqrt_t;

        let pdf_d1 = Self::normal_pdf(d1);
        let discount = (-r * t).exp();

        let gamma = pdf_d1 / (spot * vol * sqrt_t);
        let vega = spot * sqrt_t * pdf_d1 * 0.01; // Scaled per 1% vol shift

        match option_type {
            OptionType::Call => {
                let cdf_d1 = Self::normal_cdf(d1);
                let cdf_d2 = Self::normal_cdf(d2);
                let price = spot * cdf_d1 - strike * discount * cdf_d2;
                let delta = cdf_d1;
                let theta_annual = -(spot * pdf_d1 * vol) / (2.0 * sqrt_t) - r * strike * discount * cdf_d2;
                OptionGreeks {
                    price: price.max(0.0),
                    delta,
                    gamma,
                    vega,
                    theta_per_day: theta_annual / 365.0,
                }
            }
            OptionType::Put => {
                let cdf_neg_d1 = Self::normal_cdf(-d1);
                let cdf_neg_d2 = Self::normal_cdf(-d2);
                let price = strike * discount * cdf_neg_d2 - spot * cdf_neg_d1;
                let delta = -cdf_neg_d1;
                let theta_annual = -(spot * pdf_d1 * vol) / (2.0 * sqrt_t) + r * strike * discount * cdf_neg_d2;
                OptionGreeks {
                    price: price.max(0.0),
                    delta,
                    gamma,
                    vega,
                    theta_per_day: theta_annual / 365.0,
                }
            }
        }
    }

    /// Constructs an institutional Zero-Cost Collar (Long Stock + Long OTM Put + Short OTM Call).
    /// Solves for the exact call strike cap $K_{call}$ such that Call Premium == Put Premium.
    pub fn construct_zero_cost_collar(
        &self,
        spot: f64,
        shares_count: u64,
        put_strike_floor: f64,
        time_to_maturity_years: f64,
        volatility: f64,
    ) -> ZeroCostCollarResult {
        assert!(put_strike_floor < spot, "Protective put floor must be below spot price");

        let put_greeks = self.price_black_scholes(
            spot,
            put_strike_floor,
            time_to_maturity_years,
            volatility,
            OptionType::Put,
        );
        let target_premium = put_greeks.price;

        // Binary bisection search for call strike where Call(K) == Put(K_put)
        let mut low_k = spot;
        let mut high_k = spot * 2.5;
        let mut best_call_k = high_k;
        let mut best_call_greeks = self.price_black_scholes(spot, best_call_k, time_to_maturity_years, volatility, OptionType::Call);

        for _ in 0..64 {
            let mid_k = (low_k + high_k) / 2.0;
            let call_greeks = self.price_black_scholes(spot, mid_k, time_to_maturity_years, volatility, OptionType::Call);

            if (call_greeks.price - target_premium).abs() < 0.0001 {
                best_call_k = mid_k;
                best_call_greeks = call_greeks;
                break;
            }

            if call_greeks.price > target_premium {
                // Call is too expensive, raise the strike price to lower call premium
                low_k = mid_k;
            } else {
                high_k = mid_k;
            }

            best_call_k = mid_k;
            best_call_greeks = call_greeks;
        }

        let net_premium = (put_greeks.price - best_call_greeks.price).abs();
        let max_downside = (spot - put_strike_floor) / spot * 100.0;
        let max_upside = (best_call_k - spot) / spot * 100.0;

        // Portfolio Delta = 1.0 (Stock) + Delta(Put) - Delta(Call)
        let portfolio_delta = 1.0 + put_greeks.delta - best_call_greeks.delta;

        ZeroCostCollarResult {
            underlying_spot: spot,
            shares_count,
            put_strike_floor,
            put_premium: put_greeks.price,
            call_strike_cap: best_call_k,
            call_premium: best_call_greeks.price,
            net_premium_outlay: net_premium,
            max_downside_pct: max_downside,
            max_upside_pct: max_upside,
            portfolio_net_delta: portfolio_delta,
        }
    }
}
