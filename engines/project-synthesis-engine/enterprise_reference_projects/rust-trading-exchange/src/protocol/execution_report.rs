use crate::core::types::*;
use crate::core::order::Order;
use crate::core::matching_engine::FillEvent;
use crate::protocol::fix_message::FixMessage;
use crate::protocol::fix_tags::*;
use std::time::{SystemTime, UNIX_EPOCH};

pub struct ExecutionReportFactory;

impl ExecutionReportFactory {
    fn current_fix_utc_timestamp() -> String {
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
        let secs_in_day = now % 86400;
        let hours = secs_in_day / 3600;
        let minutes = (secs_in_day % 3600) / 60;
        let seconds = secs_in_day % 60;
        format!("20260910-{:02}:{:02}:{:02}.000", hours, minutes, seconds)
    }

    pub fn create_order_accepted(order: &Order, exec_id: u64, seq_num: u64) -> FixMessage {
        let mut msg = FixMessage::new();
        msg.set_field(MSG_TYPE, MSG_TYPE_EXECUTION_REPORT);
        msg.set_field(MSG_SEQ_NUM, seq_num.to_string());
        msg.set_field(SENDING_TIME, Self::current_fix_utc_timestamp());
        msg.set_field(ORDER_ID, order.id.0.to_string());
        msg.set_field(CL_ORD_ID, &order.client_order_id);
        msg.set_field(EXEC_ID, format!("EXEC-{}", exec_id));
        msg.set_field(EXEC_TYPE, "0"); // New
        msg.set_field(ORD_STATUS, "0"); // New
        msg.set_field(SYMBOL, order.instrument_id.as_str());
        msg.set_field(SIDE, match order.side { Side::Buy => "1", Side::Sell => "2" });
        msg.set_field(ORDER_QTY, order.initial_quantity.raw().to_string());
        msg.set_field(PRICE, order.price.to_string());
        msg.set_field(LEAVES_QTY, order.leaves_qty().raw().to_string());
        msg.set_field(CUM_QTY, "0");
        msg.set_field(AVG_PX, "0.0000");
        msg
    }

    pub fn create_fill_report(order: &Order, fill: &FillEvent, exec_id: u64, seq_num: u64) -> FixMessage {
        let mut msg = FixMessage::new();
        msg.set_field(MSG_TYPE, MSG_TYPE_EXECUTION_REPORT);
        msg.set_field(MSG_SEQ_NUM, seq_num.to_string());
        msg.set_field(SENDING_TIME, Self::current_fix_utc_timestamp());
        msg.set_field(ORDER_ID, order.id.0.to_string());
        msg.set_field(CL_ORD_ID, &order.client_order_id);
        msg.set_field(EXEC_ID, format!("EXEC-{}", exec_id));

        let (exec_type_str, ord_status_str) = if order.is_filled() {
            ("2", "2") // Filled
        } else {
            ("1", "1") // Partially Filled
        };

        msg.set_field(EXEC_TYPE, exec_type_str);
        msg.set_field(ORD_STATUS, ord_status_str);
        msg.set_field(SYMBOL, order.instrument_id.as_str());
        msg.set_field(SIDE, match order.side { Side::Buy => "1", Side::Sell => "2" });
        msg.set_field(ORDER_QTY, order.initial_quantity.raw().to_string());
        msg.set_field(LAST_QTY, fill.quantity.raw().to_string());
        msg.set_field(LAST_PX, fill.price.to_string());
        msg.set_field(LEAVES_QTY, order.leaves_qty().raw().to_string());
        msg.set_field(CUM_QTY, order.executed_quantity.raw().to_string());

        let avg_px = if !order.executed_quantity.is_zero() {
            (order.cumulative_quote_quantity.0 as f64) / (order.executed_quantity.raw() as f64)
        } else {
            0.0
        };
        msg.set_field(AVG_PX, format!("{:.4}", avg_px));
        msg
    }

    pub fn create_canceled_report(order: &Order, orig_cl_ord_id: &str, exec_id: u64, seq_num: u64) -> FixMessage {
        let mut msg = FixMessage::new();
        msg.set_field(MSG_TYPE, MSG_TYPE_EXECUTION_REPORT);
        msg.set_field(MSG_SEQ_NUM, seq_num.to_string());
        msg.set_field(SENDING_TIME, Self::current_fix_utc_timestamp());
        msg.set_field(ORDER_ID, order.id.0.to_string());
        msg.set_field(CL_ORD_ID, &order.client_order_id);
        msg.set_field(ORIG_CL_ORD_ID, orig_cl_ord_id);
        msg.set_field(EXEC_ID, format!("EXEC-{}", exec_id));
        msg.set_field(EXEC_TYPE, "4"); // Canceled
        msg.set_field(ORD_STATUS, "4"); // Canceled
        msg.set_field(SYMBOL, order.instrument_id.as_str());
        msg.set_field(SIDE, match order.side { Side::Buy => "1", Side::Sell => "2" });
        msg.set_field(ORDER_QTY, order.initial_quantity.raw().to_string());
        msg.set_field(LEAVES_QTY, "0");
        msg.set_field(CUM_QTY, order.executed_quantity.raw().to_string());
        msg
    }

    pub fn create_rejected_report(order: &Order, reason: &str, exec_id: u64, seq_num: u64) -> FixMessage {
        let mut msg = FixMessage::new();
        msg.set_field(MSG_TYPE, MSG_TYPE_EXECUTION_REPORT);
        msg.set_field(MSG_SEQ_NUM, seq_num.to_string());
        msg.set_field(SENDING_TIME, Self::current_fix_utc_timestamp());
        msg.set_field(ORDER_ID, order.id.0.to_string());
        msg.set_field(CL_ORD_ID, &order.client_order_id);
        msg.set_field(EXEC_ID, format!("EXEC-{}", exec_id));
        msg.set_field(EXEC_TYPE, "8"); // Rejected
        msg.set_field(ORD_STATUS, "8"); // Rejected
        msg.set_field(SYMBOL, order.instrument_id.as_str());
        msg.set_field(SIDE, match order.side { Side::Buy => "1", Side::Sell => "2" });
        msg.set_field(ORDER_QTY, order.initial_quantity.raw().to_string());
        msg.set_field(LEAVES_QTY, "0");
        msg.set_field(CUM_QTY, "0");
        msg.set_field(TEXT, reason);
        msg
    }
}
