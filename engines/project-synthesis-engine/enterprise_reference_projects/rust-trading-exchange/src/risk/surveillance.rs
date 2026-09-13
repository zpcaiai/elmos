use crate::core::types::*;
use std::collections::{HashMap, VecDeque};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SurveillanceAlert {
    PotentialSpoofing {
        participant_id: ParticipantId,
        instrument_id: InstrumentId,
        cancelled_volume: Quantity,
        executed_opposite_volume: Quantity,
        time_delta_ms: u64,
    },
    WashTradingDetected {
        maker_id: ParticipantId,
        taker_id: ParticipantId,
        instrument_id: InstrumentId,
        volume: Quantity,
        price: Price,
    },
    QuoteStuffingPattern {
        participant_id: ParticipantId,
        messages_in_second: usize,
    },
}

#[allow(dead_code)]
#[derive(Debug, Clone)]
struct OrderEventRecord {
    pub order_id: OrderId,
    pub participant_id: ParticipantId,
    pub side: Side,
    pub quantity: Quantity,
    pub timestamp_ns: u64,
}

#[allow(dead_code)]
pub struct MarketSurveillanceEngine {
    cancellations: HashMap<ParticipantId, VecDeque<OrderEventRecord>>,
    executions: HashMap<ParticipantId, VecDeque<OrderEventRecord>>,
    spoofing_window_ms: u64,
    min_spoofing_volume: Quantity,
}

impl MarketSurveillanceEngine {
    pub fn new(spoofing_window_ms: u64, min_spoofing_volume: Quantity) -> Self {
        MarketSurveillanceEngine {
            cancellations: HashMap::new(),
            executions: HashMap::new(),
            spoofing_window_ms,
            min_spoofing_volume,
        }
    }

    fn current_time_ns() -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64
    }

    pub fn on_order_cancelled(
        &mut self,
        order_id: OrderId,
        participant_id: &ParticipantId,
        side: Side,
        quantity: Quantity,
    ) {
        let ts = Self::current_time_ns();
        let queue = self.cancellations.entry(participant_id.clone()).or_insert_with(VecDeque::new);
        queue.push_back(OrderEventRecord {
            order_id,
            participant_id: participant_id.clone(),
            side,
            quantity,
            timestamp_ns: ts,
        });

        // Retain only events within 10 seconds
        let cutoff = ts.saturating_sub(10_000_000_000);
        while let Some(front) = queue.front() {
            if front.timestamp_ns < cutoff {
                queue.pop_front();
            } else {
                break;
            }
        }
    }

    pub fn on_trade_executed(
        &mut self,
        maker_pid: &ParticipantId,
        taker_pid: &ParticipantId,
        instrument_id: &InstrumentId,
        side: Side,
        price: Price,
        quantity: Quantity,
    ) -> Vec<SurveillanceAlert> {
        let mut alerts = Vec::new();
        let ts = Self::current_time_ns();

        // 1. Direct wash trading check
        if maker_pid == taker_pid {
            alerts.push(SurveillanceAlert::WashTradingDetected {
                maker_id: maker_pid.clone(),
                taker_id: taker_pid.clone(),
                instrument_id: instrument_id.clone(),
                volume: quantity,
                price,
            });
        }

        // 2. Spoofing detection: Did taker execute opposite side right after canceling large resting orders?
        let opposite_side = side.opposite();
        if let Some(cancels) = self.cancellations.get(taker_pid) {
            let window_ns = self.spoofing_window_ms * 1_000_000;
            let mut total_cancelled = 0u64;

            for cancel in cancels.iter().rev() {
                if cancel.side == opposite_side && ts.saturating_sub(cancel.timestamp_ns) <= window_ns {
                    total_cancelled += cancel.quantity.raw();
                }
            }

            if total_cancelled >= self.min_spoofing_volume.raw() {
                alerts.push(SurveillanceAlert::PotentialSpoofing {
                    participant_id: taker_pid.clone(),
                    instrument_id: instrument_id.clone(),
                    cancelled_volume: Quantity::from_raw(total_cancelled),
                    executed_opposite_volume: quantity,
                    time_delta_ms: self.spoofing_window_ms,
                });
            }
        }

        alerts
    }
}
