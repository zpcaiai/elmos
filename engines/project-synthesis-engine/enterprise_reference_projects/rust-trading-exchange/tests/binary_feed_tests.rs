use trading_exchange::binary_feed::*;
use trading_exchange::core::*;

#[test]
fn test_itch_add_order_encode_decode_roundtrip() {
    let sym_bytes = ItchCodec::symbol_to_bytes("AAPL");
    let original = ItchMessage::AddOrder {
        timestamp_ns: 123_456_789_000,
        order_reference_number: 987654321,
        side: Side::Buy,
        shares: 500,
        stock_symbol: sym_bytes,
        price_ticks: 1502500, // $150.25
    };

    let mut buf = Vec::new();
    ItchCodec::encode(&original, &mut buf);

    let decoded = ItchCodec::decode(&buf).expect("Decode should succeed");
    assert_eq!(decoded, original);
}

#[test]
fn test_itch_order_executed_and_delete_roundtrip() {
    let exec_msg = ItchMessage::OrderExecuted {
        timestamp_ns: 123_456_800_000,
        order_reference_number: 987654321,
        executed_shares: 200,
        match_number: 555123,
    };

    let mut buf = Vec::new();
    ItchCodec::encode(&exec_msg, &mut buf);

    let decoded = ItchCodec::decode(&buf).expect("Decode should succeed");
    assert_eq!(decoded, exec_msg);

    let del_msg = ItchMessage::OrderDelete {
        timestamp_ns: 123_456_900_000,
        order_reference_number: 987654321,
    };

    let mut del_buf = Vec::new();
    ItchCodec::encode(&del_msg, &mut del_buf);

    let decoded_del = ItchCodec::decode(&del_buf).expect("Decode should succeed");
    assert_eq!(decoded_del, del_msg);
}

#[test]
fn test_moldudp64_packet_framing_and_extraction() {
    let header = MoldPacketHeader {
        session: *b"SESSION_01",
        sequence_number: 10001,
        message_count: 2,
    };

    let mut packet_buf = Vec::new();
    MoldUdp64Framer::encode_header(&header, &mut packet_buf);

    // Encode two ITCH messages into packet payload
    let mut msg1_buf = Vec::new();
    ItchCodec::encode(&ItchMessage::SystemEvent { timestamp_ns: 100, event_code: b'O' }, &mut msg1_buf);
    MoldUdp64Framer::append_message_block(&msg1_buf, &mut packet_buf);

    let mut msg2_buf = Vec::new();
    ItchCodec::encode(&ItchMessage::OrderDelete { timestamp_ns: 200, order_reference_number: 42 }, &mut msg2_buf);
    MoldUdp64Framer::append_message_block(&msg2_buf, &mut packet_buf);

    // Extract message payloads from packet
    let extracted = MoldUdp64Framer::extract_message_payloads(&packet_buf).expect("Extraction should succeed");
    assert_eq!(extracted.len(), 2);

    let parsed1 = ItchCodec::decode(extracted[0]).expect("Parse 1 should succeed");
    let parsed2 = ItchCodec::decode(extracted[1]).expect("Parse 2 should succeed");

    assert_eq!(parsed1, ItchMessage::SystemEvent { timestamp_ns: 100, event_code: b'O' });
    assert_eq!(parsed2, ItchMessage::OrderDelete { timestamp_ns: 200, order_reference_number: 42 });
}

#[test]
fn test_sbe_header_encode_decode() {
    let header = SbeHeader::new(64, 101, 1, 2);
    let mut buf = Vec::new();
    header.encode_to(&mut buf);

    assert_eq!(buf.len(), SbeHeader::HEADER_SIZE);
    let decoded = SbeHeader::decode_from(&buf).expect("SBE decode should succeed");
    assert_eq!(decoded, header);
}
