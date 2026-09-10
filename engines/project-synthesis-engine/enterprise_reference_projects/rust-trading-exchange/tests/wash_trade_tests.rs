use trading_exchange::core::types::{InstrumentId, ParticipantId, Price, Quantity};
use trading_exchange::risk::wash_trade_detector::{
    ExecutedTradeRecord, WashTradeSurveillanceEngine, WashTradeType,
};

#[test]
fn test_direct_beneficial_ownership_wash_trade_detection() {
    let mut engine = WashTradeSurveillanceEngine::new(300_000_000_000); // 5-minute sliding window

    let acct_a1 = ParticipantId::new("ACCT-CIT-01");
    let acct_a2 = ParticipantId::new("ACCT-CIT-02");
    let acct_ext = ParticipantId::new("ACCT-JPM-01");

    // Both acct_a1 and acct_a2 belong to same parent legal entity
    engine.register_beneficial_owner(acct_a1.clone(), "LEI-CITADEL-GLOBAL");
    engine.register_beneficial_owner(acct_a2.clone(), "LEI-CITADEL-GLOBAL");
    engine.register_beneficial_owner(acct_ext.clone(), "LEI-JPM-CHASE");

    let aapl = InstrumentId::new("AAPL");

    // 1. External arm's length trade -> Clean
    let clean_trade = ExecutedTradeRecord {
        trade_id: "TRD-001".to_string(),
        buyer_id: acct_a1.clone(),
        seller_id: acct_ext.clone(),
        instrument_id: aapl.clone(),
        price: Price::from_major_minor(150, 0),
        quantity: Quantity::from_raw(5000),
        timestamp_ns: 1_000_000_000,
    };
    let res1 = engine.ingest_and_evaluate_trade(clean_trade);
    assert!(res1.is_none(), "Arms-length trade between independent entities should not trigger alert");

    // 2. Wash trade between accounts sharing beneficial owner
    let wash_trade = ExecutedTradeRecord {
        trade_id: "TRD-002".to_string(),
        buyer_id: acct_a1.clone(),
        seller_id: acct_a2.clone(),
        instrument_id: aapl.clone(),
        price: Price::from_major_minor(150, 5000),
        quantity: Quantity::from_raw(10_000),
        timestamp_ns: 2_000_000_000,
    };
    let res2 = engine.ingest_and_evaluate_trade(wash_trade);
    assert!(res2.is_some(), "Trade between accounts sharing beneficial owner must trigger alert");

    let alert = res2.unwrap();
    assert_eq!(alert.alert_type, WashTradeType::DirectBeneficialSelfMatch);
    assert_eq!(alert.matched_quantity, Quantity::from_raw(10_000));
}

#[test]
fn test_circular_ring_trading_collusion_detection() {
    let mut engine = WashTradeSurveillanceEngine::new(600_000_000_000); // 10-minute window

    let p_alpha = ParticipantId::new("PROP-ALPHA");
    let p_beta = ParticipantId::new("PROP-BETA");
    let p_gamma = ParticipantId::new("PROP-GAMMA");

    let tsla = InstrumentId::new("TSLA");

    // Sequence of trades circulating shares in a ring:
    // Trade 1: Alpha sells 15,000 TSLA to Beta @ $200
    engine.ingest_and_evaluate_trade(ExecutedTradeRecord {
        trade_id: "TRD-RING-1".to_string(),
        buyer_id: p_beta.clone(),
        seller_id: p_alpha.clone(),
        instrument_id: tsla.clone(),
        price: Price::from_major_minor(200, 0),
        quantity: Quantity::from_raw(15_000),
        timestamp_ns: 10_000_000_000,
    });

    // Trade 2: Beta sells 15,000 TSLA to Gamma @ $200.05
    engine.ingest_and_evaluate_trade(ExecutedTradeRecord {
        trade_id: "TRD-RING-2".to_string(),
        buyer_id: p_gamma.clone(),
        seller_id: p_beta.clone(),
        instrument_id: tsla.clone(),
        price: Price::from_major_minor(200, 500),
        quantity: Quantity::from_raw(15_000),
        timestamp_ns: 20_000_000_000,
    });

    // Trade 3: Gamma sells 15,000 TSLA back to Alpha @ $200.02 (completing ring!)
    engine.ingest_and_evaluate_trade(ExecutedTradeRecord {
        trade_id: "TRD-RING-3".to_string(),
        buyer_id: p_alpha.clone(),
        seller_id: p_gamma.clone(),
        instrument_id: tsla.clone(),
        price: Price::from_major_minor(200, 200),
        quantity: Quantity::from_raw(15_000),
        timestamp_ns: 30_000_000_000,
    });

    let ring_alerts = engine.detect_circular_wash_rings(&tsla);
    assert_eq!(ring_alerts.len(), 1, "Exactly one circular collusion wash ring should be detected");

    let alert = &ring_alerts[0];
    assert_eq!(alert.alert_type, WashTradeType::CircularRingCollusion);
    assert_eq!(alert.matched_quantity, Quantity::from_raw(15_000));
    assert!(alert.cycle_path.is_some());

    let cycle = alert.cycle_path.as_ref().unwrap();
    assert_eq!(cycle.len(), 3, "Ring cycle must involve exactly 3 participants");
}
