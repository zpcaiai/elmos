use trading_exchange::core::types::{InstrumentId, Price, Quantity, Side};
use trading_exchange::synthetic::{
    CrossSpreadEngine, LegQuote, SpreadType, SyntheticSpreadDefinition,
};

#[test]
fn test_synthetic_calendar_spread_pricing_and_execution() {
    let mut engine = CrossSpreadEngine::new();

    let leg1_front = InstrumentId::new("CL-2026M");
    let leg2_back = InstrumentId::new("CL-2026N");
    let spread_sym = InstrumentId::new("CL-2026M-CL-2026N");

    let spread_def = SyntheticSpreadDefinition {
        spread_instrument_id: spread_sym.clone(),
        leg1_instrument_id: leg1_front.clone(),
        leg2_instrument_id: leg2_back.clone(),
        leg1_ratio: 1,
        leg2_ratio: -1,
        spread_type: SpreadType::CalendarSpread,
        min_tick_size: Price::from_raw(100), // 0.01
    };

    engine.register_spread(spread_def);

    // Set market data on legs:
    // Leg1 Front: Bid = 75.50 (755000), Ask = 75.52 (755200), Qty = 50
    engine.update_leg_bbo(
        leg1_front,
        LegQuote {
            bid_price: Some(Price::from_raw(755000)),
            bid_qty: Quantity::from_raw(50),
            ask_price: Some(Price::from_raw(755200)),
            ask_qty: Quantity::from_raw(50),
        },
    );

    // Leg2 Back: Bid = 74.80 (748000), Ask = 74.82 (748200), Qty = 30
    engine.update_leg_bbo(
        leg2_back,
        LegQuote {
            bid_price: Some(Price::from_raw(748000)),
            bid_qty: Quantity::from_raw(30),
            ask_price: Some(Price::from_raw(748200)),
            ask_qty: Quantity::from_raw(30),
        },
    );

    // Implied Spread BBO:
    // Implied Bid = Leg1 Bid (75.50) - Leg2 Ask (74.82) = +0.68 (6800)
    // Implied Ask = Leg1 Ask (75.52) - Leg2 Bid (74.80) = +0.72 (7200)
    // Implied Quantity = min(50, 30) = 30
    let implied = engine.calculate_implied_spread_quote(&spread_sym).unwrap();
    assert_eq!(implied.implied_bid_price, Some(Price::from_raw(6800)));
    assert_eq!(implied.implied_ask_price, Some(Price::from_raw(7200)));
    assert_eq!(implied.implied_bid_quantity, Quantity::from_raw(30));
    assert_eq!(implied.implied_ask_quantity, Quantity::from_raw(30));

    // Execute Spread Buy of 20 lots at limit +0.75 (7500)
    let exec = engine.execute_spread_order(
        &spread_sym,
        Side::Buy,
        Quantity::from_raw(20),
        Price::from_raw(7500),
    ).unwrap();

    assert_eq!(exec.leg1_executed_qty, Quantity::from_raw(20));
    assert_eq!(exec.leg2_executed_qty, Quantity::from_raw(20));
    assert_eq!(exec.legging_risk_unhedged_qty, Quantity::ZERO);
    assert_eq!(exec.net_spread_price_realized, Price::from_raw(7200)); // Executed at ask 0.72
}
