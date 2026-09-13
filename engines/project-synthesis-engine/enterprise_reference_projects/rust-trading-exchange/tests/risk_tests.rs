use trading_exchange::core::*;
use trading_exchange::risk::*;

#[test]
fn test_pre_trade_price_collar_breach() {
    let mut risk_engine = PreTradeRiskEngine::new(RiskLimitConfig {
        price_collar_percentage: 0.05, // 5% collar
        ..Default::default()
    });

    let aapl = InstrumentId::new("AAPL");
    risk_engine.update_reference_price(aapl.clone(), Price::from_f64(100.00));

    // Order within 5% collar ($104.00) -> Allowed
    let valid_order = OrderBuilder::new()
        .id(OrderId(1))
        .participant_id("TRADER-1")
        .instrument_id("AAPL")
        .side(Side::Buy)
        .price(Price::from_f64(104.00))
        .quantity(Quantity::from_raw(10))
        .build()
        .unwrap();
    assert!(risk_engine.validate_order(&valid_order).is_ok());

    // Order breaching collar ($108.00 = 8% > 5%) -> Rejected
    let collar_order = OrderBuilder::new()
        .id(OrderId(2))
        .participant_id("TRADER-1")
        .instrument_id("AAPL")
        .side(Side::Buy)
        .price(Price::from_f64(108.00))
        .quantity(Quantity::from_raw(10))
        .build()
        .unwrap();

    let err = risk_engine.validate_order(&collar_order).unwrap_err();
    match err {
        RiskViolation::PriceCollarBreached { .. } => {}
        _ => panic!("Expected PriceCollarBreached, got {:?}", err),
    }
}

#[test]
fn test_max_order_quantity_limit() {
    let mut risk_engine = PreTradeRiskEngine::new(RiskLimitConfig {
        max_order_quantity: Quantity::from_raw(10_000),
        ..Default::default()
    });

    let big_order = OrderBuilder::new()
        .id(OrderId(3))
        .participant_id("FAT-FINGER")
        .instrument_id("AAPL")
        .side(Side::Buy)
        .price(Price::from_f64(100.00))
        .quantity(Quantity::from_raw(50_000))
        .build()
        .unwrap();

    let err = risk_engine.validate_order(&big_order).unwrap_err();
    assert_eq!(
        err,
        RiskViolation::OrderQuantityExceeded {
            limit: Quantity::from_raw(10_000),
            requested: Quantity::from_raw(50_000),
        }
    );
}
