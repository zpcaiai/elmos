pub const SOH: u8 = 0x01;

// Standard Header Tags
pub const BEGIN_STRING: u32 = 8;
pub const BODY_LENGTH: u32 = 9;
pub const MSG_TYPE: u32 = 35;
pub const SENDER_COMP_ID: u32 = 49;
pub const TARGET_COMP_ID: u32 = 56;
pub const MSG_SEQ_NUM: u32 = 34;
pub const SENDING_TIME: u32 = 52;

// Standard Message Body Tags
pub const CL_ORD_ID: u32 = 11;
pub const ORDER_ID: u32 = 37;
pub const EXEC_ID: u32 = 17;
pub const EXEC_TYPE: u32 = 150;
pub const ORD_STATUS: u32 = 39;
pub const SYMBOL: u32 = 55;
pub const SIDE: u32 = 54;
pub const ORDER_QTY: u32 = 38;
pub const ORD_TYPE: u32 = 40;
pub const PRICE: u32 = 44;
pub const TIME_IN_FORCE: u32 = 59;
pub const LAST_QTY: u32 = 32;
pub const LAST_PX: u32 = 31;
pub const LEAVES_QTY: u32 = 151;
pub const CUM_QTY: u32 = 14;
pub const AVG_PX: u32 = 6;
pub const TEXT: u32 = 58;
pub const ORIG_CL_ORD_ID: u32 = 41;
pub const ORD_REJ_REASON: u32 = 103;
pub const ACCOUNT: u32 = 1;
pub const SECURITY_ID: u32 = 48;
pub const ID_SOURCE: u32 = 22;

// Standard Trailer Tags
pub const CHECK_SUM: u32 = 10;

// MsgType Values
pub const MSG_TYPE_HEARTBEAT: &str = "0";
pub const MSG_TYPE_TEST_REQUEST: &str = "1";
pub const MSG_TYPE_RESEND_REQUEST: &str = "2";
pub const MSG_TYPE_REJECT: &str = "3";
pub const MSG_TYPE_LOGON: &str = "A";
pub const MSG_TYPE_LOGOUT: &str = "5";
pub const MSG_TYPE_NEW_ORDER_SINGLE: &str = "D";
pub const MSG_TYPE_ORDER_CANCEL_REQUEST: &str = "F";
pub const MSG_TYPE_ORDER_CANCEL_REPLACE_REQUEST: &str = "G";
pub const MSG_TYPE_ORDER_STATUS_REQUEST: &str = "H";
pub const MSG_TYPE_EXECUTION_REPORT: &str = "8";
pub const MSG_TYPE_ORDER_CANCEL_REJECT: &str = "9";
