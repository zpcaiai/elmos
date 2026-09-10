use crate::core::types::*;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TradeCaptureReport {
    pub trade_report_id: String,
    pub trade_id: TradeId,
    pub instrument_id: InstrumentId,
    pub price: Price,
    pub quantity: Quantity,
    pub gross_cash_amount: Money,
    pub buy_participant_id: ParticipantId,
    pub sell_participant_id: ParticipantId,
    pub buy_order_id: OrderId,
    pub sell_order_id: OrderId,
    pub transact_time_ns: u64,
    pub clearing_business_date: String, // YYYY-MM-DD
    pub regulatory_uti: String,         // Unique Trade Identifier (ISO 23897)
}

impl TradeCaptureReport {
    pub fn new(
        trade_id: TradeId,
        instrument_id: InstrumentId,
        price: Price,
        quantity: Quantity,
        buy_participant: ParticipantId,
        sell_participant: ParticipantId,
        buy_order: OrderId,
        sell_order: OrderId,
        transact_time_ns: u64,
        date_str: impl Into<String>,
    ) -> Self {
        let gross_cash = Money::from_price_quantity(price, quantity);
        let date = date_str.into();
        let uti = format!("EXCH-{:08}-{}", trade_id.0, date.replace('-', ""));
        let report_id = format!("TCR-{}", uti);

        TradeCaptureReport {
            trade_report_id: report_id,
            trade_id,
            instrument_id,
            price,
            quantity,
            gross_cash_amount: gross_cash,
            buy_participant_id: buy_participant,
            sell_participant_id: sell_participant,
            buy_order_id: buy_order,
            sell_order_id: sell_order,
            transact_time_ns,
            clearing_business_date: date,
            regulatory_uti: uti,
        }
    }

    /// Renders FIX 4.4 tag-value string representation for tag 35=AE (TradeCaptureReport)
    pub fn to_fix_ae_string(&self) -> String {
        let s = format!(
            "35=AE|571={}|1003={}|55={}|31={}|32={}|119={}|60={}|75={}|",
            self.trade_report_id,
            self.trade_id.0,
            self.instrument_id.as_str(),
            self.price,
            self.quantity,
            self.gross_cash_amount.to_decimal(),
            self.transact_time_ns,
            self.clearing_business_date,
        );
        s.replace('|', "\x01")
    }
}
