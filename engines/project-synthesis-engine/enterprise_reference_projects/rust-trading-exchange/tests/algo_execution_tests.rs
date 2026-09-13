use trading_exchange::algo::{
    AlgoParentOrder, ExecutionStrategy, ExecutionUrgency, IntradayVolumeProfile,
    SliceStatus, VwapTwapExecutionSlicer,
};
use trading_exchange::core::types::{InstrumentId, Price, Quantity, Side};

#[test]
fn test_vwap_u_curve_schedule_and_exact_quantity_conservation() {
    let aapl = InstrumentId::new("AAPL");
    let arrival_price = Price::from_major_minor(150, 0); // $150.00
    let total_qty = Quantity::from_raw(100_000); // 100,000 shares parent order

    let parent = AlgoParentOrder::new(
        "ALGO-VWAP-001",
        aapl.clone(),
        Side::Buy,
        total_qty,
        arrival_price,
        ExecutionStrategy::Vwap,
        ExecutionUrgency::Neutral,
    );

    let profile = IntradayVolumeProfile::standard_u_curve();
    let slicer = VwapTwapExecutionSlicer::new(parent, profile);

    assert_eq!(slicer.child_slices.len(), 13, "Standard U-curve must have 13 half-hour periods");

    // Verify quantity conservation: Sum of all slices must equal exactly 100,000
    let sum_slices: u64 = slicer.child_slices.iter().map(|s| s.target_quantity.raw()).sum();
    assert_eq!(sum_slices, 100_000, "Child order slices must sum exactly to parent quantity");

    // First period (09:30-10:00) and last period (15:30-16:00) must have the highest allocations
    let first_slice = &slicer.child_slices[0];
    let last_slice = &slicer.child_slices[12];
    let mid_slice = &slicer.child_slices[6]; // Midday (12:30-13:00)

    assert!(first_slice.target_quantity.raw() > mid_slice.target_quantity.raw(), "Opening slice must be larger than midday");
    assert!(last_slice.target_quantity.raw() > mid_slice.target_quantity.raw(), "Closing slice must be larger than midday");
}

#[test]
fn test_vwap_execution_tracking_error_and_market_benchmark() {
    let msft = InstrumentId::new("MSFT");
    let arrival_price = Price::from_major_minor(400, 0); // $400.00
    let total_qty = Quantity::from_raw(10_000);

    let parent = AlgoParentOrder::new(
        "ALGO-VWAP-002",
        msft.clone(),
        Side::Buy,
        total_qty,
        arrival_price,
        ExecutionStrategy::Vwap,
        ExecutionUrgency::Aggressive,
    );

    let profile = IntradayVolumeProfile::flat_profile(4); // 4 equal periods of 2,500 shares
    let mut slicer = VwapTwapExecutionSlicer::new(parent, profile);

    // Feed market trades across the day:
    // Trade 1: 50,000 @ $399.50
    slicer.record_market_trade(Price::from_major_minor(399, 5000), Quantity::from_raw(50_000));
    // Trade 2: 100,000 @ $400.00
    slicer.record_market_trade(Price::from_major_minor(400, 0), Quantity::from_raw(100_000));
    // Trade 3: 50,000 @ $401.00
    slicer.record_market_trade(Price::from_major_minor(401, 0), Quantity::from_raw(50_000));

    let mkt_vwap = slicer.market_vwap().expect("Market VWAP must be available");
    // (50k * 399.50 + 100k * 400.00 + 50k * 401.00) / 200k = (19,975,000 + 40,000,000 + 20,050,000) / 200,000 = $400.125
    assert!((mkt_vwap.to_f64() - 400.125).abs() < 0.001, "Expected market VWAP ~$400.125");

    // Execute Bucket 0: 2,500 shares filled at $399.80 (better than market VWAP)
    let bid = Price::from_major_minor(399, 7000);
    let ask = Price::from_major_minor(399, 8000);
    let slice = slicer.activate_current_bucket(bid, ask).expect("Slice must activate");
    assert_eq!(slice.status, SliceStatus::Active);
    assert_eq!(slice.limit_price, ask, "Aggressive buy urgency must cross spread to ask");

    slicer.record_child_fill(0, Quantity::from_raw(2500), ask);
    assert_eq!(slicer.child_slices[0].status, SliceStatus::Filled);

    // Advance and execute Bucket 1: 2,500 shares filled at $400.10
    slicer.advance_to_next_bucket();
    let bid2 = Price::from_major_minor(400, 0);
    let ask2 = Price::from_major_minor(400, 1000);
    slicer.activate_current_bucket(bid2, ask2);
    slicer.record_child_fill(1, Quantity::from_raw(2500), ask2);

    let exec_vwap = slicer.parent_order.execution_vwap().expect("Execution VWAP should exist");
    // Executed: (2,500 * $399.80 + 2,500 * $400.10) / 5,000 = $399.95
    assert!((exec_vwap.to_f64() - 399.95).abs() < 0.01, "Expected parent execution VWAP of $399.95");

    // Tracking error for Buy: ((Exec - Market) / Market) * 10,000
    // ($399.95 - $400.125) / $400.125 * 10,000 = -4.37 bps (favorable execution!)
    let te_bps = slicer.tracking_error_bps().expect("Tracking error should be computable");
    assert!(te_bps < 0.0, "Execution beat market VWAP, so tracking error must be negative bps");

    // Arrival slippage: ($399.95 - $400.00) / $400.00 * 10000 = -1.25 bps (beat arrival decision price)
    let slippage = slicer.arrival_slippage_bps().expect("Slippage should be computable");
    assert!(slippage < 0.0, "Execution beat arrival price");
}

#[test]
fn test_algo_price_collar_adverse_market_halt() {
    let nvda = InstrumentId::new("NVDA");
    let arrival_price = Price::from_major_minor(100, 0); // $100.00
    let total_qty = Quantity::from_raw(50_000);

    let mut parent = AlgoParentOrder::new(
        "ALGO-COLLAR-001",
        nvda.clone(),
        Side::Buy,
        total_qty,
        arrival_price,
        ExecutionStrategy::Vwap,
        ExecutionUrgency::Passive,
    );
    parent.max_adverse_deviation_bps = 50; // 50 bps = 0.50% max allowable surge ($100.50)

    let profile = IntradayVolumeProfile::flat_profile(5);
    let mut slicer = VwapTwapExecutionSlicer::new(parent, profile);

    // Prevailing market suddenly surges to $101.00 (100 bps surge > 50 bps collar)
    let surging_bid = Price::from_major_minor(101, 0);
    let surging_ask = Price::from_major_minor(101, 2000);

    let slice = slicer.activate_current_bucket(surging_bid, surging_ask).expect("Bucket exists");
    assert_eq!(
        slice.status,
        SliceStatus::CollarHalted,
        "Child order release must be halted when market surges beyond adverse collar"
    );
}

#[test]
fn test_unfilled_slice_dynamic_rebalancing_across_future_periods() {
    let tsla = InstrumentId::new("TSLA");
    let arrival_price = Price::from_major_minor(200, 0);
    let total_qty = Quantity::from_raw(10_000);

    let parent = AlgoParentOrder::new(
        "ALGO-REBAL-001",
        tsla.clone(),
        Side::Sell,
        total_qty,
        arrival_price,
        ExecutionStrategy::Twap,
        ExecutionUrgency::Passive,
    );

    let profile = IntradayVolumeProfile::flat_profile(5); // 5 periods of 2,000 shares
    let mut slicer = VwapTwapExecutionSlicer::new(parent, profile);

    assert_eq!(slicer.child_slices[0].target_quantity.raw(), 2000);
    assert_eq!(slicer.child_slices[1].target_quantity.raw(), 2000);

    // Period 0 only achieves partial fill of 800 shares (1,200 unfilled shortfall)
    slicer.record_child_fill(0, Quantity::from_raw(800), Price::from_major_minor(200, 0));

    // Advance to Period 1: The 1,200 shortfall should be redistributed across remaining 4 periods (+300 each)
    slicer.advance_to_next_bucket();

    assert_eq!(slicer.child_slices[1].target_quantity.raw(), 2300, "Period 1 target should increase from 2,000 to 2,300");
    assert_eq!(slicer.child_slices[2].target_quantity.raw(), 2300, "Period 2 target should increase from 2,000 to 2,300");
    assert_eq!(slicer.child_slices[3].target_quantity.raw(), 2300, "Period 3 target should increase from 2,000 to 2,300");
    assert_eq!(slicer.child_slices[4].target_quantity.raw(), 2300, "Period 4 target should increase from 2,000 to 2,300");
}
