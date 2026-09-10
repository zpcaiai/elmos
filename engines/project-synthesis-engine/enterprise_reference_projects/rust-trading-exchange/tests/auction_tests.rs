use trading_exchange::auction::*;
use trading_exchange::core::*;

#[test]
fn test_call_auction_equilibrium_clearing_and_tie_break() {
    let sym = InstrumentId::new("NVDA");
    let ref_price = Price::from_major_minor(120, 0); // $120.00
    let mut book = CallAuctionBook::new(sym.clone(), ref_price);

    // Bid 1: 100 shares @ $122.00
    let b1 = Order::new(
        OrderId(1), "C-1", ParticipantId::new("FIRM_A"), sym.clone(),
        Side::Buy, OrderType::Limit, TimeInForce::Day,
        Price::from_major_minor(122, 0), Quantity::from_raw(100), SelfTradePreventionMode::None,
    );
    // Bid 2: 200 shares @ $121.00
    let b2 = Order::new(
        OrderId(2), "C-2", ParticipantId::new("FIRM_B"), sym.clone(),
        Side::Buy, OrderType::Limit, TimeInForce::Day,
        Price::from_major_minor(121, 0), Quantity::from_raw(200), SelfTradePreventionMode::None,
    );
    // Ask 1: 150 shares @ $120.50
    let a1 = Order::new(
        OrderId(3), "C-3", ParticipantId::new("FIRM_C"), sym.clone(),
        Side::Sell, OrderType::Limit, TimeInForce::Day,
        Price::from_major_minor(120, 5000), Quantity::from_raw(150), SelfTradePreventionMode::None,
    );
    // Ask 2: 150 shares @ $121.50
    let a2 = Order::new(
        OrderId(4), "C-4", ParticipantId::new("FIRM_D"), sym.clone(),
        Side::Sell, OrderType::Limit, TimeInForce::Day,
        Price::from_major_minor(121, 5000), Quantity::from_raw(150), SelfTradePreventionMode::None,
    );

    book.insert_order(b1);
    book.insert_order(b2);
    book.insert_order(a1);
    book.insert_order(a2);

    // Equilibrium clearing price:
    // At $121.00:
    // Cum Buy (>= $121.00): 100 + 200 = 300 shares
    // Cum Sell (<= $121.00): Ask 1 (150 shares) = 150 shares
    // Executable volume = 150 shares, Imbalance = 150 shares Buy
    let clearing_px = book.determine_clearing_price();
    assert!(clearing_px.is_some());
    let px = clearing_px.unwrap();
    assert_eq!(px, Price::from_major_minor(121, 0));

    // Calculate NOII Imbalance
    let noii = book.calculate_imbalance(1_000_000_000);
    assert_eq!(noii.paired_quantity, Quantity::from_raw(150));
    assert_eq!(noii.total_imbalance_quantity, Quantity::from_raw(150));
    assert_eq!(noii.imbalance_side, ImbalanceSide::Buy);

    // Execute uncrossing
    let result = AuctionUncrossingEngine::uncross(book, px, 1001, 1_000_000_000);
    assert_eq!(result.total_matched_volume, Quantity::from_raw(150));
    assert_eq!(result.trades.len(), 2); // Matched b1 (100 shares) and b2 (50 shares) against a1 (150 shares)
    assert_eq!(result.remaining_bids.len(), 1); // b2 has 150 shares remaining
    assert_eq!(result.remaining_asks.len(), 1); // a2 has 150 shares remaining
}
