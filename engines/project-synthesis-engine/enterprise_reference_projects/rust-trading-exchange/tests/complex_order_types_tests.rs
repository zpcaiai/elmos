use trading_exchange::order_types::*;
use trading_exchange::core::*;

#[test]
fn test_trailing_stop_ratchet_and_trigger() {
    let sym = InstrumentId::new("AAPL");
    let initial_px = Price::from_major_minor(180, 0); // $180.00
    let trailing_delta = Price::from_major_minor(5, 0); // $5.00 trailing stop

    // Sell trailing stop: Protecting a long position
    let base_order = Order::new(
        OrderId(10), "TS-1", ParticipantId::new("TRADER_1"), sym.clone(),
        Side::Sell, OrderType::TrailingStop { trailing_delta, high_water_mark: initial_px },
        TimeInForce::GoodTilCancel, initial_px, Quantity::from_raw(100), SelfTradePreventionMode::None,
    );

    let mut ts = TrailingStopOrder::new(base_order, trailing_delta, initial_px);
    assert_eq!(ts.high_water_mark, Price::from_major_minor(180, 0));
    assert_eq!(ts.current_stop_price, Price::from_major_minor(175, 0)); // 180 - 5

    // Price moves up to $185.00 -> Ratchets stop up to $180.00
    let triggered1 = ts.on_market_trade(Price::from_major_minor(185, 0), 100);
    assert!(triggered1.is_none());
    assert_eq!(ts.high_water_mark, Price::from_major_minor(185, 0));
    assert_eq!(ts.current_stop_price, Price::from_major_minor(180, 0));

    // Price moves up to $190.00 -> Ratchets stop up to $185.00
    let triggered2 = ts.on_market_trade(Price::from_major_minor(190, 0), 200);
    assert!(triggered2.is_none());
    assert_eq!(ts.high_water_mark, Price::from_major_minor(190, 0));
    assert_eq!(ts.current_stop_price, Price::from_major_minor(185, 0));

    // Price dips to $187.00 -> Stop price stays at $185.00 (does not loosen!)
    let triggered3 = ts.on_market_trade(Price::from_major_minor(187, 0), 300);
    assert!(triggered3.is_none());
    assert_eq!(ts.current_stop_price, Price::from_major_minor(185, 0));

    // Price crashes to $184.50 -> Breaches $185.00 stop -> Triggers market sell order!
    let triggered4 = ts.on_market_trade(Price::from_major_minor(184, 5000), 400);
    assert!(triggered4.is_some());
    let triggered_order = triggered4.unwrap();
    assert_eq!(triggered_order.order_type, OrderType::Market);
    assert_eq!(ts.is_triggered, true);
}

#[test]
fn test_pegged_midpoint_order_repricing() {
    let sym = InstrumentId::new("MSFT");
    let base_order = Order::new(
        OrderId(20), "PEG-1", ParticipantId::new("ALGO_1"), sym.clone(),
        Side::Buy, OrderType::Limit, TimeInForce::Day,
        Price::ZERO, Quantity::from_raw(50), SelfTradePreventionMode::None,
    );

    let mut peg = PeggedOrder::new(
        base_order,
        PegType::Midpoint,
        0, // Zero tick offset from midpoint
        Some(Price::from_major_minor(410, 0)), // Ceiling cap at $410.00
        Some(Price::from_major_minor(400, 0)), // Bid: $400.00
        Some(Price::from_major_minor(402, 0)), // Ask: $402.00
    ).unwrap();

    // Initial midpoint: (400 + 402) / 2 = $401.00
    assert_eq!(peg.current_pegged_price, Price::from_major_minor(401, 0));

    // BBO tightens: Bid $401.00, Ask $402.00 -> New Midpoint: $401.50
    let updated_px = peg.on_bbo_update(
        Some(Price::from_major_minor(401, 0)),
        Some(Price::from_major_minor(402, 0)),
    );
    assert!(updated_px.is_some());
    assert_eq!(updated_px.unwrap(), Price::from_major_minor(401, 5000));
    assert_eq!(peg.current_pegged_price, Price::from_major_minor(401, 5000));
}

#[test]
fn test_contingent_oco_and_oto_lifecycle() {
    let sym = InstrumentId::new("TSLA");
    let mut manager = ContingentOrderManager::new();

    // Setup OCO: Limit Profit Order (101) vs Stop Loss Order (102)
    let leg_a = Order::new(
        OrderId(101), "LEG-A", ParticipantId::new("TRADER_A"), sym.clone(),
        Side::Sell, OrderType::Limit, TimeInForce::GoodTilCancel,
        Price::from_major_minor(250, 0), Quantity::from_raw(10), SelfTradePreventionMode::None,
    );
    let leg_b = Order::new(
        OrderId(102), "LEG-B", ParticipantId::new("TRADER_A"), sym.clone(),
        Side::Sell, OrderType::StopLoss(Price::from_major_minor(230, 0)), TimeInForce::GoodTilCancel,
        Price::from_major_minor(230, 0), Quantity::from_raw(10), SelfTradePreventionMode::None,
    );

    manager.register_oco(OcoOrderGroup::new("GRP-OCO-1", leg_a, leg_b));

    // When Take Profit Leg A fills, Leg B must be canceled!
    let (oco_cancel, _) = manager.on_order_filled(OrderId(101));
    assert_eq!(oco_cancel, Some(OrderId(102)));

    // Setup OTO: Parent Buy Order (201) triggers Child Profit Target Sell (202)
    let parent = Order::new(
        OrderId(201), "PARENT", ParticipantId::new("TRADER_B"), sym.clone(),
        Side::Buy, OrderType::Limit, TimeInForce::Day,
        Price::from_major_minor(240, 0), Quantity::from_raw(20), SelfTradePreventionMode::None,
    );
    let child = Order::new(
        OrderId(202), "CHILD", ParticipantId::new("TRADER_B"), sym.clone(),
        Side::Sell, OrderType::Limit, TimeInForce::GoodTilCancel,
        Price::from_major_minor(260, 0), Quantity::from_raw(20), SelfTradePreventionMode::None,
    );

    manager.register_oto(OtoOrderGroup::new("GRP-OTO-1", parent, child));

    // When parent fills, child is released!
    let (_, oto_released) = manager.on_order_filled(OrderId(201));
    assert!(oto_released.is_some());
    let rel = oto_released.unwrap();
    assert_eq!(rel.id, OrderId(202));
    assert_eq!(rel.price, Price::from_major_minor(260, 0));
}
