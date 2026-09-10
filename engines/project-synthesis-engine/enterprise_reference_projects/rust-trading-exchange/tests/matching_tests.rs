use trading_exchange::core::*;

#[test]
fn test_limit_order_crossing_fifo() {
    let mut engine = MatchingEngine::new(InstrumentId::new("AAPL"));

    // Resting Sell: 100 shares @ $150.00
    let maker = OrderBuilder::new()
        .id(OrderId(1))
        .participant_id("MAKER-1")
        .instrument_id("AAPL")
        .side(Side::Sell)
        .price(Price::from_f64(150.00))
        .quantity(Quantity::from_raw(100))
        .build()
        .unwrap();

    let res1 = engine.submit_order(maker).unwrap();
    assert!(res1.resting_added);
    assert_eq!(res1.fills.len(), 0);

    // Taker Buy: 60 shares @ $150.00 (Crosses)
    let taker = OrderBuilder::new()
        .id(OrderId(2))
        .participant_id("TAKER-1")
        .instrument_id("AAPL")
        .side(Side::Buy)
        .price(Price::from_f64(150.00))
        .quantity(Quantity::from_raw(60))
        .build()
        .unwrap();

    let res2 = engine.submit_order(taker).unwrap();
    assert_eq!(res2.fills.len(), 1);
    assert_eq!(res2.fills[0].quantity, Quantity::from_raw(60));
    assert_eq!(res2.fills[0].price, Price::from_f64(150.00));
    assert_eq!(res2.taker_order.status, OrderStatus::Filled);

    // Verify Maker remaining quantity on book = 40
    let best_ask = engine.book.best_ask().unwrap();
    assert_eq!(best_ask.0, Price::from_f64(150.00));
    assert_eq!(best_ask.1, Quantity::from_raw(40));
}

#[test]
fn test_post_only_rejection() {
    let mut engine = MatchingEngine::new(InstrumentId::new("AAPL"));

    // Resting Sell: 100 @ $150.00
    let maker = OrderBuilder::new()
        .id(OrderId(10))
        .participant_id("MAKER")
        .instrument_id("AAPL")
        .side(Side::Sell)
        .price(Price::from_f64(150.00))
        .quantity(Quantity::from_raw(100))
        .build()
        .unwrap();
    engine.submit_order(maker).unwrap();

    // Post-Only Buy @ $150.00 (Crosses -> must be rejected)
    let post_only = OrderBuilder::new()
        .id(OrderId(11))
        .participant_id("TAKER")
        .instrument_id("AAPL")
        .side(Side::Buy)
        .order_type(OrderType::PostOnly)
        .price(Price::from_f64(150.00))
        .quantity(Quantity::from_raw(50))
        .build()
        .unwrap();

    let res = engine.submit_order(post_only).unwrap();
    assert_eq!(res.taker_order.status, OrderStatus::Rejected);
    assert_eq!(res.fills.len(), 0);
}

#[test]
fn test_fok_fill_or_kill() {
    let mut engine = MatchingEngine::new(InstrumentId::new("AAPL"));

    // Resting Sell: only 50 available @ $150.00
    let maker = OrderBuilder::new()
        .id(OrderId(20))
        .participant_id("MAKER")
        .instrument_id("AAPL")
        .side(Side::Sell)
        .price(Price::from_f64(150.00))
        .quantity(Quantity::from_raw(50))
        .build()
        .unwrap();
    engine.submit_order(maker).unwrap();

    // FOK Buy: wants 100 @ $150.00 (Insufficient volume -> killed)
    let fok = OrderBuilder::new()
        .id(OrderId(21))
        .participant_id("TAKER")
        .instrument_id("AAPL")
        .side(Side::Buy)
        .time_in_force(TimeInForce::FillOrKill)
        .price(Price::from_f64(150.00))
        .quantity(Quantity::from_raw(100))
        .build()
        .unwrap();

    let res = engine.submit_order(fok).unwrap();
    assert_eq!(res.taker_order.status, OrderStatus::Canceled);
    assert_eq!(res.fills.len(), 0);
    // Maker still in book
    assert_eq!(engine.book.best_ask().unwrap().1, Quantity::from_raw(50));
}

#[test]
fn test_iceberg_replenishment() {
    let mut engine = MatchingEngine::new(InstrumentId::new("AAPL"));

    // Iceberg Sell: Total 10,000, Visible peak 1,000
    let iceberg = OrderBuilder::new()
        .id(OrderId(30))
        .participant_id("WHALE")
        .instrument_id("AAPL")
        .side(Side::Sell)
        .order_type(OrderType::Iceberg { peak_size: Quantity::from_raw(1_000) })
        .price(Price::from_f64(150.00))
        .quantity(Quantity::from_raw(10_000))
        .build()
        .unwrap();

    engine.submit_order(iceberg).unwrap();

    // Verify initial visible quantity is 1,000, not 10,000
    assert_eq!(engine.book.best_ask().unwrap().1, Quantity::from_raw(1_000));

    // Taker Buys 1,500
    let taker = OrderBuilder::new()
        .id(OrderId(31))
        .participant_id("TAKER")
        .instrument_id("AAPL")
        .side(Side::Buy)
        .price(Price::from_f64(150.00))
        .quantity(Quantity::from_raw(1_500))
        .build()
        .unwrap();

    let res = engine.submit_order(taker).unwrap();
    // Fills 1,000 first, replenishes, then fills 500 more
    assert_eq!(res.fills.len(), 2);
    assert_eq!(res.fills[0].quantity, Quantity::from_raw(1_000));
    assert_eq!(res.fills[1].quantity, Quantity::from_raw(500));

    // Check remaining visible on book (replenished: 1,000 - 500 = 500)
    assert_eq!(engine.book.best_ask().unwrap().1, Quantity::from_raw(500));
}

#[test]
fn test_self_trade_prevention_cancel_newest() {
    let mut engine = MatchingEngine::new(InstrumentId::new("AAPL"));

    // Maker: FIRM-A Sells 100 @ 150
    let maker = OrderBuilder::new()
        .id(OrderId(40))
        .participant_id("FIRM-A")
        .instrument_id("AAPL")
        .side(Side::Sell)
        .price(Price::from_f64(150.00))
        .quantity(Quantity::from_raw(100))
        .build()
        .unwrap();
    engine.submit_order(maker).unwrap();

    // Taker: FIRM-A Buys 100 @ 150 with CancelNewest
    let taker = OrderBuilder::new()
        .id(OrderId(41))
        .participant_id("FIRM-A")
        .instrument_id("AAPL")
        .side(Side::Buy)
        .stp_mode(SelfTradePreventionMode::CancelNewest)
        .price(Price::from_f64(150.00))
        .quantity(Quantity::from_raw(100))
        .build()
        .unwrap();

    let res = engine.submit_order(taker).unwrap();
    assert_eq!(res.taker_order.status, OrderStatus::Canceled);
    assert_eq!(res.fills.len(), 0);
    // Maker remained on book untouched
    assert!(engine.book.get_order(&OrderId(40)).is_some());
}
