use trading_exchange::protocol::*;

#[test]
fn test_fix_encode_decode_roundtrip() {
    let mut msg = FixMessage::new();
    msg.set_field(MSG_TYPE, MSG_TYPE_NEW_ORDER_SINGLE);
    msg.set_field(CL_ORD_ID, "CL-123456");
    msg.set_field(SYMBOL, "AAPL");
    msg.set_field(SIDE, "1");
    msg.set_field(ORDER_QTY, "1000");
    msg.set_field(PRICE, "150.2500");

    let encoded_bytes = FixEncoder::encode(&msg, "FIX.4.2");
    assert!(!encoded_bytes.is_empty());

    // Verify Checksum tag 10= is in bytes
    assert!(encoded_bytes.windows(3).any(|w| w == b"10="));

    let decoded = FixDecoder::decode(&encoded_bytes).expect("Valid FIX message should decode");
    assert_eq!(decoded.get_field(MSG_TYPE), Some(MSG_TYPE_NEW_ORDER_SINGLE));
    assert_eq!(decoded.get_field(CL_ORD_ID), Some("CL-123456"));
    assert_eq!(decoded.get_field(SYMBOL), Some("AAPL"));
    assert_eq!(decoded.get_field(SIDE), Some("1"));
    assert_eq!(decoded.get_field(ORDER_QTY), Some("1000"));
    assert_eq!(decoded.get_field(PRICE), Some("150.2500"));
}

#[test]
fn test_fix_checksum_corruption_detection() {
    let mut msg = FixMessage::new();
    msg.set_field(MSG_TYPE, MSG_TYPE_HEARTBEAT);
    msg.set_field(MSG_SEQ_NUM, "1");

    let mut encoded_bytes = FixEncoder::encode(&msg, "FIX.4.2");

    // Corrupt one byte before checksum
    if let Some(pos) = encoded_bytes.iter().position(|&b| b == b'0') {
        encoded_bytes[pos] = b'9';
    }

    let res = FixDecoder::decode(&encoded_bytes);
    assert!(matches!(res, Err(FixDecodeError::InvalidChecksum { .. })));
}
