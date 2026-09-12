use trading_exchange::core::types::{InstrumentId, Price, Quantity, Side};
use trading_exchange::market_maker::{
    MarketMakerProtectionEngine, MmpBreachType, MmpConfig, MmpStatus,
};

#[test]
fn test_mmp_volume_and_delta_breach_protection() {
    let mut engine = MarketMakerProtectionEngine::new();
    let config = MmpConfig {
        window_millis: 1000,
        max_volume: Quantity::from_raw(1000),
        max_trade_count: 5,
        max_delta_lots: 500,
        auto_reset_millis: None,
    };

    let mm_account = 42;
    engine.register_account(mm_account, config);

    let symbol = InstrumentId::new("AAPL");
    let base_time = 1_000_000_000u64;

    // 1st fill: 200 buy lots -> OK
    let breach1 = engine.on_execution(
        mm_account,
        symbol.clone(),
        Side::Buy,
        Quantity::from_raw(200),
        Price::from_raw(1500000),
        base_time,
    );
    assert_eq!(breach1, None);

    // 2nd fill: 200 buy lots -> Total delta = +400 -> OK
    let breach2 = engine.on_execution(
        mm_account,
        symbol.clone(),
        Side::Buy,
        Quantity::from_raw(200),
        Price::from_raw(1500000),
        base_time + 100_000_000,
    );
    assert_eq!(breach2, None);

    // 3rd fill: 200 buy lots -> Total delta = +600 > max_delta_lots(500) -> DELTA BREACH!
    let breach3 = engine.on_execution(
        mm_account,
        symbol.clone(),
        Side::Buy,
        Quantity::from_raw(200),
        Price::from_raw(1500000),
        base_time + 200_000_000,
    );
    assert_eq!(breach3, Some(MmpBreachType::DeltaExposureExceeded));

    // Verify account is now frozen
    let status = engine.get_status(mm_account, base_time + 300_000_000);
    match status {
        Some(MmpStatus::Frozen { breach_type, .. }) => {
            assert_eq!(breach_type, MmpBreachType::DeltaExposureExceeded);
        }
        _ => panic!("Account must be in Frozen state"),
    }

    // Subsequent fill ignored while frozen
    let breach_post_freeze = engine.on_execution(
        mm_account,
        symbol,
        Side::Buy,
        Quantity::from_raw(100),
        Price::from_raw(1500000),
        base_time + 400_000_000,
    );
    assert_eq!(breach_post_freeze, None);

    // Manual reset handshake
    let reset_res = engine.reset_protection(mm_account);
    assert!(reset_res.is_ok());

    let status_after_reset = engine.get_status(mm_account, base_time + 500_000_000);
    assert_eq!(status_after_reset, Some(MmpStatus::Active));
}
