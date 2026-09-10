use crate::core::types::*;
use crate::clearing_bridge::trade_capture_report::TradeCaptureReport;
use std::collections::HashMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MemberClearingSummary {
    pub participant_id: ParticipantId,
    pub instrument_id: InstrumentId,
    pub gross_buy_quantity: Quantity,
    pub gross_sell_quantity: Quantity,
    pub net_quantity: i64, // Positive = net buyer (receives securities); Negative = net seller (delivers securities)
    pub gross_buy_cash: Money,
    pub gross_sell_cash: Money,
    pub net_cash_amount: i64, // Minor units (cents): Positive = net payer; Negative = net receiver
    pub trade_count: u32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClearingBatchExport {
    pub batch_id: String,
    pub business_date: String,
    pub created_at_epoch_ns: u64,
    pub total_trades_processed: usize,
    pub total_gross_cash: Money,
    pub member_summaries: Vec<MemberClearingSummary>,
    pub is_balanced: bool,
}

pub struct ClearingBatchAggregator {
    pub batch_id: String,
    pub business_date: String,
    pub reports: Vec<TradeCaptureReport>,
}

impl ClearingBatchAggregator {
    pub fn new(batch_id: impl Into<String>, business_date: impl Into<String>) -> Self {
        ClearingBatchAggregator {
            batch_id: batch_id.into(),
            business_date: business_date.into(),
            reports: Vec::new(),
        }
    }

    pub fn add_trade_report(&mut self, report: TradeCaptureReport) {
        self.reports.push(report);
    }

    /// Aggregates member positions across all trades in the batch and performs bilateral zero-sum check
    pub fn aggregate(&self, epoch_ns: u64) -> ClearingBatchExport {
        // Key: (ParticipantId, InstrumentId)
        let mut map: HashMap<(ParticipantId, InstrumentId), MemberClearingSummary> = HashMap::new();
        let mut total_cash_raw: i64 = 0;

        for r in &self.reports {
            total_cash_raw += r.gross_cash_amount.0;

            // Buyer entry
            let buyer_key = (r.buy_participant_id.clone(), r.instrument_id.clone());
            let buyer_entry = map.entry(buyer_key).or_insert_with(|| MemberClearingSummary {
                participant_id: r.buy_participant_id.clone(),
                instrument_id: r.instrument_id.clone(),
                gross_buy_quantity: Quantity::ZERO,
                gross_sell_quantity: Quantity::ZERO,
                net_quantity: 0,
                gross_buy_cash: Money::ZERO,
                gross_sell_cash: Money::ZERO,
                net_cash_amount: 0,
                trade_count: 0,
            });
            buyer_entry.gross_buy_quantity = buyer_entry.gross_buy_quantity + r.quantity;
            buyer_entry.gross_buy_cash = Money(buyer_entry.gross_buy_cash.0 + r.gross_cash_amount.0);
            buyer_entry.net_quantity += r.quantity.raw() as i64;
            buyer_entry.net_cash_amount += r.gross_cash_amount.0; // Payer
            buyer_entry.trade_count += 1;

            // Seller entry
            let seller_key = (r.sell_participant_id.clone(), r.instrument_id.clone());
            let seller_entry = map.entry(seller_key).or_insert_with(|| MemberClearingSummary {
                participant_id: r.sell_participant_id.clone(),
                instrument_id: r.instrument_id.clone(),
                gross_buy_quantity: Quantity::ZERO,
                gross_sell_quantity: Quantity::ZERO,
                net_quantity: 0,
                gross_buy_cash: Money::ZERO,
                gross_sell_cash: Money::ZERO,
                net_cash_amount: 0,
                trade_count: 0,
            });
            seller_entry.gross_sell_quantity = seller_entry.gross_sell_quantity + r.quantity;
            seller_entry.gross_sell_cash = Money(seller_entry.gross_sell_cash.0 + r.gross_cash_amount.0);
            seller_entry.net_quantity -= r.quantity.raw() as i64;
            seller_entry.net_cash_amount -= r.gross_cash_amount.0; // Receiver
            seller_entry.trade_count += 1;
        }

        let summaries: Vec<MemberClearingSummary> = map.into_values().collect();

        // Verification invariant: Sum of net quantities == 0, Sum of net cash == 0
        let sum_net_qty: i64 = summaries.iter().map(|s| s.net_quantity).sum();
        let sum_net_cash: i64 = summaries.iter().map(|s| s.net_cash_amount).sum();
        let is_balanced = sum_net_qty == 0 && sum_net_cash == 0;

        ClearingBatchExport {
            batch_id: self.batch_id.clone(),
            business_date: self.business_date.clone(),
            created_at_epoch_ns: epoch_ns,
            total_trades_processed: self.reports.len(),
            total_gross_cash: Money(total_cash_raw),
            member_summaries: summaries,
            is_balanced,
        }
    }
}
