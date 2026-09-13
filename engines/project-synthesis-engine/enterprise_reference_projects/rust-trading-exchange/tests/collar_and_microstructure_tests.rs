use trading_exchange::core::types::{Price, Quantity, Side};
use trading_exchange::market_data::market_microstructure_signals::{
    MarketMicrostructureEngine, TopOfBookQuote,
};
use trading_exchange::synthetic::collar_strategy_engine::{
    CollarStrategyEngine, OptionType,
};

#[test]
fn test_black_scholes_analytical_and_zero_cost_collar() {
    let pricer = CollarStrategyEngine::new(0.045); // 4.5% risk-free rate

    // Standard Normal CDF sanity checks
    assert!((CollarStrategyEngine::normal_cdf(0.0) - 0.5000).abs() < 1e-4);
    assert!((CollarStrategyEngine::normal_cdf(1.96) - 0.9750).abs() < 1e-3);
    assert!((CollarStrategyEngine::normal_cdf(-1.96) - 0.0250).abs() < 1e-3);

    // Test European Option Pricing: Spot $100, Strike $100, 1 Year, 20% Volatility
    let call = pricer.price_black_scholes(100.0, 100.0, 1.0, 0.20, OptionType::Call);
    let put = pricer.price_black_scholes(100.0, 100.0, 1.0, 0.20, OptionType::Put);

    // Put-Call Parity: Call - Put = Spot - Strike * exp(-r*T)
    let discount = (-0.045 * 1.0f64).exp();
    let parity_lhs = call.price - put.price;
    let parity_rhs = 100.0 - 100.0 * discount;
    assert!((parity_lhs - parity_rhs).abs() < 0.05, "Put-Call parity must hold within numerical tolerance");

    // Call Delta should be approx ~0.60, Put Delta ~ -0.40
    assert!(call.delta > 0.50 && call.delta < 0.70);
    assert!(put.delta < -0.30 && put.delta > -0.50);

    // Zero-Cost Collar Construction:
    // Long 10,000 shares of stock at $150.00. Protective Put at $135.00 (90% floor).
    // Solve for call cap strike.
    let collar = pricer.construct_zero_cost_collar(150.0, 10_000, 135.0, 0.50, 0.25);

    // Verifications:
    // 1. Net premium outlay must be virtually $0.00 (within $0.05)
    assert!(
        collar.net_premium_outlay < 0.05,
        "Zero-cost collar net premium must be ~0, got {}",
        collar.net_premium_outlay
    );

    // 2. Call strike cap must be above spot price ($150)
    assert!(
        collar.call_strike_cap > 150.0,
        "Call strike cap must exceed spot price"
    );

    // 3. Max downside must be exactly 10.0% ($135 vs $150)
    assert!((collar.max_downside_pct - 10.0).abs() < 0.01);

    // 4. Portfolio delta must be reduced from 1.0 down toward market neutral
    assert!(collar.portfolio_net_delta > 0.0 && collar.portfolio_net_delta < 0.80);
}

#[test]
fn test_market_microstructure_order_flow_imbalance_and_impact() {
    let mut engine = MarketMicrostructureEngine::new(20);

    let q1 = TopOfBookQuote {
        bid_price: Price::from_major_minor(100, 0),
        bid_qty: Quantity::from_raw(500),
        ask_price: Price::from_major_minor(100, 1000), // $100.10
        ask_qty: Quantity::from_raw(500),
    };

    // First quote sets baseline
    let ofi1 = engine.update_quote_and_compute_ofi(q1);
    assert_eq!(ofi1, 0);

    // Second quote: Buyers aggressively replenish bid depth (+300 units)
    let q2 = TopOfBookQuote {
        bid_price: Price::from_major_minor(100, 0),
        bid_qty: Quantity::from_raw(800), // +300 units at bid
        ask_price: Price::from_major_minor(100, 1000),
        ask_qty: Quantity::from_raw(500),
    };
    let ofi2 = engine.update_quote_and_compute_ofi(q2);
    assert_eq!(ofi2, 300, "Order Flow Imbalance should reflect +300 buy replenishment");

    // Ingest aggressive buy trade into ask
    let signals = engine.record_trade_and_compute_signals(
        Price::from_major_minor(100, 1000),
        Quantity::from_raw(200),
        Side::Buy,
        q2,
        Some(Price::from_major_minor(100, 1200)), // Future mid slightly higher
    );

    assert!(signals.effective_spread_bps > 0.0, "Effective spread must be positive");
    assert!(signals.kyles_lambda >= 0.0, "Kyle's lambda must be non-negative");
}
