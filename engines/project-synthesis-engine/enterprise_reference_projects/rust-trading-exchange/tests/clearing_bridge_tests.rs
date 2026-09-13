use trading_exchange::clearing_bridge::*;
use trading_exchange::core::*;

#[test]
fn test_trade_capture_report_fix_ae_format() {
    let tcr = TradeCaptureReport::new(
        TradeId(555),
        InstrumentId::new("MSFT"),
        Price::from_major_minor(400, 5000), // $400.50
        Quantity::from_raw(100),
        ParticipantId::new("BUYER_FIRM"),
        ParticipantId::new("SELLER_FIRM"),
        OrderId(1),
        OrderId(2),
        1_700_000_000_000_000_000,
        "2026-09-10",
    );

    assert_eq!(tcr.trade_id, TradeId(555));
    assert_eq!(tcr.gross_cash_amount, Money(4_005_000)); // $40,050.00 = 4,005,000 cents
    assert!(tcr.regulatory_uti.contains("EXCH-00000555-20260910"));

    let fix = tcr.to_fix_ae_string();
    assert!(fix.contains("35=AE"));
    assert!(fix.contains("55=MSFT"));
    assert!(fix.contains("1003=555"));
}

#[test]
fn test_clearing_batch_netting_and_settlement_feed() {
    let mut agg = ClearingBatchAggregator::new("BATCH-2026-001", "2026-09-10");

    // Trade 1: Firm A buys 100 shares of AAPL from Firm B @ $150
    let t1 = TradeCaptureReport::new(
        TradeId(1), InstrumentId::new("AAPL"), Price::from_major_minor(150, 0), Quantity::from_raw(100),
        ParticipantId::new("FIRM_A"), ParticipantId::new("FIRM_B"), OrderId(11), OrderId(12), 100, "2026-09-10",
    );
    // Trade 2: Firm B buys 40 shares of AAPL from Firm A @ $150
    let t2 = TradeCaptureReport::new(
        TradeId(2), InstrumentId::new("AAPL"), Price::from_major_minor(150, 0), Quantity::from_raw(40),
        ParticipantId::new("FIRM_B"), ParticipantId::new("FIRM_A"), OrderId(13), OrderId(14), 200, "2026-09-10",
    );

    agg.add_trade_report(t1);
    agg.add_trade_report(t2);

    let export = agg.aggregate(500);

    // Netting balance check:
    // Firm A: Bought 100, Sold 40 -> Net quantity = +60 (receiver of AAPL); Net cash = +$9,000 (payer)
    // Firm B: Bought 40, Sold 100 -> Net quantity = -60 (deliverer of AAPL); Net cash = -$9,000 (receiver)
    assert_eq!(export.is_balanced, true);
    assert_eq!(export.total_trades_processed, 2);

    let firm_a = export.member_summaries.iter().find(|s| s.participant_id.as_str() == "FIRM_A").unwrap();
    let firm_b = export.member_summaries.iter().find(|s| s.participant_id.as_str() == "FIRM_B").unwrap();

    assert_eq!(firm_a.net_quantity, 60);
    assert_eq!(firm_b.net_quantity, -60);
    assert_eq!(firm_a.net_cash_amount, 900_000);  // +$9,000 in cents
    assert_eq!(firm_b.net_cash_amount, -900_000); // -$9,000 in cents

    // Test signed settlement feed publisher with CRC32
    let mut publisher = SettlementFeedPublisher::new();
    let feed_entry = publisher.publish_batch(&export);

    assert_eq!(feed_entry.sequence_number, 1);
    assert_eq!(feed_entry.batch_id, "BATCH-2026-001");
    assert!(feed_entry.checksum_crc32 > 0);
    assert!(feed_entry.payload_csv.contains("FIRM_A,AAPL,60,900000,2"));
    assert!(feed_entry.payload_csv.contains("FIRM_B,AAPL,-60,-900000,2"));
}
