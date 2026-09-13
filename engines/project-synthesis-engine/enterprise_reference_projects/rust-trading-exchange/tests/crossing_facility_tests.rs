use trading_exchange::core::types::{InstrumentId, OrderId, Price, Quantity, Side};
use trading_exchange::crossing::{
    CrossingBenchmark, CrossingOrder, VolumeWeightedCrossingEngine,
};

#[test]
fn test_block_trade_midpoint_crossing_facility() {
    let block_threshold = Quantity::from_raw(10_000); // 10k shares minimum block
    let mut engine = VolumeWeightedCrossingEngine::new(block_threshold);

    let symbol = InstrumentId::new("AAPL");
    let base_time = 1_000_000_000u64;

    // Order below threshold should be rejected
    let small_order = CrossingOrder {
        order_id: OrderId(1),
        instrument_id: symbol.clone(),
        side: Side::Buy,
        quantity: Quantity::from_raw(5_000), // Below 10k!
        min_execution_quantity: Quantity::from_raw(1_000),
        benchmark: CrossingBenchmark::ContinuousMidpoint,
        max_slippage_ticks: 2,
        client_id: 101,
        timestamp_nanos: base_time,
    };
    let rej = engine.submit_crossing_order(small_order);
    assert!(rej.is_err());

    // Submit Institutional Buy: 25,000 shares
    let buy_order = CrossingOrder {
        order_id: OrderId(2),
        instrument_id: symbol.clone(),
        side: Side::Buy,
        quantity: Quantity::from_raw(25_000),
        min_execution_quantity: Quantity::from_raw(10_000),
        benchmark: CrossingBenchmark::ContinuousMidpoint,
        max_slippage_ticks: 2,
        client_id: 101,
        timestamp_nanos: base_time,
    };
    engine.submit_crossing_order(buy_order).unwrap();

    // Submit Institutional Sell: 20,000 shares
    let sell_order = CrossingOrder {
        order_id: OrderId(3),
        instrument_id: symbol.clone(),
        side: Side::Sell,
        quantity: Quantity::from_raw(20_000),
        min_execution_quantity: Quantity::from_raw(10_000),
        benchmark: CrossingBenchmark::ContinuousMidpoint,
        max_slippage_ticks: 2,
        client_id: 202,
        timestamp_nanos: base_time,
    };
    engine.submit_crossing_order(sell_order).unwrap();

    // Trigger crossing round at midpoint price $150.25 (1502500)
    let midpoint_price = Price::from_raw(1502500);
    let matches = engine.execute_crossing_round(midpoint_price, base_time + 500_000_000);

    assert_eq!(matches.len(), 1);
    let m = &matches[0];
    assert_eq!(m.instrument_id, symbol);
    assert_eq!(m.buy_order_id, OrderId(2));
    assert_eq!(m.sell_order_id, OrderId(3));
    assert_eq!(m.execution_quantity, Quantity::from_raw(20_000));
    assert_eq!(m.execution_price, midpoint_price);
    assert_eq!(m.benchmark_applied, CrossingBenchmark::ContinuousMidpoint);
}
