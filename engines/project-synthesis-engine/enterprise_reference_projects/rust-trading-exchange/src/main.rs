use trading_exchange::core::*;
use trading_exchange::risk::*;
use trading_exchange::engine::TradingSession;
use trading_exchange::protocol::FixEncoder;

fn main() {
    println!("==========================================================");
    println!("  Ultra-Low-Latency Trading Exchange & Matching Engine");
    println!("==========================================================");

    let symbol = InstrumentId::new("AAPL");
    let baseline_price = Price::from_f64(150.00); // $150.00

    let mut risk_cfg = RiskLimitConfig::default();
    risk_cfg.max_order_quantity = Quantity::from_raw(500_000);
    risk_cfg.price_collar_percentage = 0.10; // 10% collar

    let cb_cfg = CircuitBreakerConfig::default();

    let mut session = TradingSession::new(symbol.clone(), baseline_price, risk_cfg, cb_cfg);
    println!("Initialized Trading Session for {} at baseline ${:.2}", symbol, baseline_price.to_f64());

    // 1. Establish initial book with resting orders
    println!("\n[Phase 1: Order Book Injection]");
    let orders_to_seed = vec![
        // Asks (Sells)
        OrderBuilder::new().id(OrderId(101)).participant_id("CITADEL").instrument_id("AAPL")
            .side(Side::Sell).price(Price::from_f64(150.10)).quantity(Quantity::from_raw(5_000)).build().unwrap(),
        OrderBuilder::new().id(OrderId(102)).participant_id("VIRTU").instrument_id("AAPL")
            .side(Side::Sell).price(Price::from_f64(150.15)).quantity(Quantity::from_raw(8_000)).build().unwrap(),
        OrderBuilder::new().id(OrderId(103)).participant_id("SUSQUEHANNA").instrument_id("AAPL")
            .side(Side::Sell).price(Price::from_f64(150.20)).quantity(Quantity::from_raw(12_000)).build().unwrap(),

        // Bids (Buys)
        OrderBuilder::new().id(OrderId(201)).participant_id("JUMP").instrument_id("AAPL")
            .side(Side::Buy).price(Price::from_f64(149.95)).quantity(Quantity::from_raw(6_000)).build().unwrap(),
        OrderBuilder::new().id(OrderId(202)).participant_id("DRW").instrument_id("AAPL")
            .side(Side::Buy).price(Price::from_f64(149.90)).quantity(Quantity::from_raw(10_000)).build().unwrap(),
    ];

    for order in orders_to_seed {
        let (res, reports, _) = session.handle_new_order(order).expect("Seed order should pass risk");
        println!("  Resting Order Injected: {} [{}]", res.taker_order.id, reports[0].get_field(11).unwrap_or(""));
    }

    let bbo = session.get_bbo();
    println!("\nCurrent Market BBO:\n  {}", bbo);

    // 2. Aggressive Market Sweep Order
    println!("\n[Phase 2: Aggressive Taker Market Sweep]");
    let taker_order = OrderBuilder::new()
        .id(OrderId(301))
        .participant_id("GOLDMAN")
        .instrument_id("AAPL")
        .side(Side::Buy)
        .order_type(OrderType::Market)
        .quantity(Quantity::from_raw(10_000))
        .build()
        .unwrap();

    let (res, reports, alerts) = session.handle_new_order(taker_order).expect("Taker should match");
    println!("Taker Order Executed: {} Status: {:?}", res.taker_order.id, res.taker_order.status);
    println!("Fills Generated: {}", res.fills.len());
    for fill in &res.fills {
        println!("  -> Trade {}: {} lots @ ${:.4} (Maker: {})",
            fill.trade_id, fill.quantity, fill.price.to_f64(), fill.maker_participant_id);
    }

    if !alerts.is_empty() {
        println!("Surveillance Alerts: {:?}", alerts);
    }

    // 3. FIX Protocol serialization demonstration
    println!("\n[Phase 3: FIX 4.2 Protocol Execution Reports]");
    for report in reports.iter().take(2) {
        let encoded_bytes = FixEncoder::encode(report, "FIX.4.2");
        println!("  FIX Raw Wire ({} bytes): {}", encoded_bytes.len(), report.to_debug_string());
    }

    // 4. L2 Market Depth & VWAP
    println!("\n[Phase 4: Market Telemetry & VWAP]");
    let depth = session.get_l2_depth(3);
    println!("L2 Asks: {:?}", depth.asks);
    println!("L2 Bids: {:?}", depth.bids);
    println!("Session VWAP: ${:.4}", session.vwap.current_vwap().map_or(0.0, |p| p.to_f64()));
    println!("Total Turnover: {}", session.trade_tape.total_turnover());

    println!("\n==========================================================");
    println!("  Trading Exchange Engine Demo Complete (100% Deterministic)");
    println!("==========================================================");
}
