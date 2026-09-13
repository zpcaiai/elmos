use trading_exchange::core::types::{InstrumentId, ParticipantId, Price, Quantity, Side};
use trading_exchange::risk::credit_margin_monitor::{
    MarginViolationType, ParticipantCreditAccount, PreTradeCreditMarginEngine,
};

#[test]
fn test_pre_trade_margin_credit_checks_and_rejections() {
    let mut engine = PreTradeCreditMarginEngine::new();

    let mm_id = ParticipantId::new("MM-JITSU");
    let aapl = InstrumentId::new("AAPL");
    let msft = InstrumentId::new("MSFT");

    // Pledged equity: $1,000,000 (100,000,000 cents), 10x max leverage -> $10M max gross
    let mut acct = ParticipantCreditAccount::new(mm_id.clone(), 100_000_000, 10.0);
    acct.set_price(aapl.clone(), Price::from_major_minor(150, 0)); // $150.00
    acct.set_price(msft.clone(), Price::from_major_minor(400, 0)); // $400.00
    engine.register_account(acct);

    // 1. Valid trade well within leverage and concentration: Buy 1,000 AAPL ($150,000)
    let res1 = engine.evaluate_pre_trade_order(
        &mm_id,
        &aapl,
        Side::Buy,
        Price::from_major_minor(150, 0),
        Quantity::from_raw(1000),
    );
    assert!(res1.is_ok(), "Expected order to pass margin check");
    let util = res1.unwrap();
    assert!(util > 0.0 && util < 0.20, "Margin utilization should be small");

    // Update account position with filled trade
    if let Some(a) = engine.get_account_mut(&mm_id) {
        a.update_position(aapl.clone(), 1000);
    }

    // 2. Excessive Leverage Breach: Try to buy 70,000 AAPL ($10.5M notional > $10M max leverage)
    let res2 = engine.evaluate_pre_trade_order(
        &mm_id,
        &aapl,
        Side::Buy,
        Price::from_major_minor(150, 0),
        Quantity::from_raw(70_000),
    );
    assert!(
        matches!(res2, Err(MarginViolationType::ExcessiveLeverage { .. })),
        "Order exceeding 10x gross leverage must be rejected"
    );

    // 3. Concentration Breach: Buy 20,000 MSFT ($8.0M notional) where max single-name is 35%
    let res3 = engine.evaluate_pre_trade_order(
        &mm_id,
        &msft,
        Side::Buy,
        Price::from_major_minor(400, 0),
        Quantity::from_raw(20_000),
    );
    assert!(
        matches!(res3, Err(MarginViolationType::ConcentrationLimitBreached { .. })),
        "Order breaching 35% single-stock concentration must be rejected"
    );
}

#[test]
fn test_span_stress_grid_tail_loss_protection() {
    let mut engine = PreTradeCreditMarginEngine::new();
    let prop_id = ParticipantId::new("PROP-DESK-99");
    let nvda = InstrumentId::new("NVDA");

    // $200,000 equity (20,000,000 cents), 20% maintenance margin -> buffer is $160,000
    let mut acct = ParticipantCreditAccount::new(prop_id.clone(), 20_000_000, 10.0);
    acct.max_single_name_concentration = 1.0; // Allow 100% concentration to isolate SPAN tail stress loss check
    acct.set_price(nvda.clone(), Price::from_major_minor(100, 0)); // $100.00
    engine.register_account(acct);

    // Attempt to buy 15,000 NVDA ($1,500,000 notional)
    // Under CRASH_MINUS_15_PCT scenario (-15% shock):
    // Loss = 15,000 * $100 * 15% = $225,000 loss > $160,000 buffer!
    let res = engine.evaluate_pre_trade_order(
        &prop_id,
        &nvda,
        Side::Buy,
        Price::from_major_minor(100, 0),
        Quantity::from_raw(15_000),
    );

    assert!(
        matches!(res, Err(MarginViolationType::StressGridDeficit { .. })),
        "Order with potential 15% stress loss exceeding margin buffer must be rejected by SPAN grid"
    );
}
