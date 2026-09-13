use crate::core::types::*;
use crate::core::order::Order;
use crate::core::matching_engine::{MatchingEngine, MatchResult};
use crate::core::orderbook::L2Snapshot;
use crate::risk::pre_trade_risk::{PreTradeRiskEngine, RiskViolation};
use crate::risk::limits::RiskLimitConfig;
use crate::risk::circuit_breaker::{CircuitBreaker, CircuitBreakerConfig};
use crate::risk::surveillance::{MarketSurveillanceEngine, SurveillanceAlert};
use crate::market_data::bbo::BestBidOffer;
use crate::market_data::trades::{TradeTick, TradeTape};
use crate::market_data::candles::OhlcvAggregator;
use crate::market_data::vwap::VwapAccumulator;
use crate::journal::wal::{WriteAheadLog, WalPayloadType};
use crate::protocol::execution_report::ExecutionReportFactory;
use crate::protocol::fix_message::FixMessage;

pub struct TradingSession {
    pub instrument_id: InstrumentId,
    pub matching_engine: MatchingEngine,
    pub risk_engine: PreTradeRiskEngine,
    pub circuit_breaker: CircuitBreaker,
    pub surveillance: MarketSurveillanceEngine,
    pub trade_tape: TradeTape,
    pub vwap: VwapAccumulator,
    pub ohlcv: OhlcvAggregator,
    pub wal: WriteAheadLog,
    pub fix_seq_num: u64,
    pub exec_id_seq: u64,
}

impl TradingSession {
    pub fn new(
        instrument_id: InstrumentId,
        baseline_price: Price,
        risk_cfg: RiskLimitConfig,
        cb_cfg: CircuitBreakerConfig,
    ) -> Self {
        let matching_engine = MatchingEngine::new(instrument_id.clone());
        let mut risk_engine = PreTradeRiskEngine::new(risk_cfg);
        risk_engine.update_reference_price(instrument_id.clone(), baseline_price);

        let circuit_breaker = CircuitBreaker::new(instrument_id.clone(), baseline_price, cb_cfg);
        let surveillance = MarketSurveillanceEngine::new(500, Quantity::from_raw(10_000));
        let trade_tape = TradeTape::new(10_000);
        let vwap = VwapAccumulator::new();
        let ohlcv = OhlcvAggregator::new();
        let wal = WriteAheadLog::new();

        TradingSession {
            instrument_id,
            matching_engine,
            risk_engine,
            circuit_breaker,
            surveillance,
            trade_tape,
            vwap,
            ohlcv,
            wal,
            fix_seq_num: 1,
            exec_id_seq: 1,
        }
    }

    fn next_exec_id(&mut self) -> u64 {
        let id = self.exec_id_seq;
        self.exec_id_seq += 1;
        id
    }

    fn next_fix_seq(&mut self) -> u64 {
        let seq = self.fix_seq_num;
        self.fix_seq_num += 1;
        seq
    }

    /// Primary order ingestion pipeline with risk checks, circuit breaker, execution, and telemetry
    pub fn handle_new_order(&mut self, order: Order) -> Result<(MatchResult, Vec<FixMessage>, Vec<SurveillanceAlert>), RiskViolation> {
        let mut fix_reports = Vec::new();

        // 1. Check Circuit Breaker trading halt
        if !self.circuit_breaker.is_trading_allowed() {
            return Err(RiskViolation::TradingHalted {
                reason: format!("Market state is {:?}", self.circuit_breaker.state),
            });
        }

        // 2. Pre-Trade Risk Checks
        self.risk_engine.validate_order(&order)?;

        // 3. Log to Write-Ahead Log (WAL)
        let now_ns = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64;

        let payload = format!("{}:{}", order.id.0, order.price.raw()).into_bytes();
        self.wal.append(WalPayloadType::OrderSubmitted, payload, now_ns);

        // 4. Send Order Accepted FIX Report
        let exec_id = self.next_exec_id();
        let fix_seq = self.next_fix_seq();
        fix_reports.push(ExecutionReportFactory::create_order_accepted(&order, exec_id, fix_seq));

        // 5. Submit into Matching Engine
        let match_result = self.matching_engine.submit_order(order)
            .map_err(|e| RiskViolation::TradingHalted { reason: e.to_string() })?;

        // 6. Process Trades / Fills
        let mut alerts = Vec::new();
        for fill in &match_result.fills {
            // Update Circuit Breaker
            if let Some(new_state) = self.circuit_breaker.check_execution(fill.price) {
                let cb_payload = format!("HALT:{:?}:{}", new_state, fill.price.raw()).into_bytes();
                self.wal.append(WalPayloadType::CircuitBreakerTriggered, cb_payload, now_ns);
            }

            // Update Reference Price in Risk Engine
            self.risk_engine.update_reference_price(self.instrument_id.clone(), fill.price);

            // Record Trade in Market Data Tape, VWAP, Candlesticks
            let tick = TradeTick {
                trade_id: fill.trade_id,
                instrument_id: fill.instrument_id.clone(),
                price: fill.price,
                quantity: fill.quantity,
                aggressor_side: fill.side,
                timestamp_ns: fill.timestamp_ns,
            };

            self.trade_tape.record_trade(tick.clone());
            self.vwap.on_trade(&tick);
            self.ohlcv.on_trade(&tick);

            // Surveillance Check (wash trade & spoofing)
            let alert_batch = self.surveillance.on_trade_executed(
                &fill.maker_participant_id,
                &fill.taker_participant_id,
                &fill.instrument_id,
                fill.side,
                fill.price,
                fill.quantity,
            );
            alerts.extend(alert_batch);

            // Emit Trade Executed FIX Reports for Taker
            let fill_exec_id = self.next_exec_id();
            let fill_seq = self.next_fix_seq();
            fix_reports.push(ExecutionReportFactory::create_fill_report(
                &match_result.taker_order,
                fill,
                fill_exec_id,
                fill_seq,
            ));
        }

        // 7. Cleanup risk state if closed
        if match_result.taker_order.is_filled() || match_result.taker_order.status.is_terminal() {
            self.risk_engine.on_order_closed(&match_result.taker_order.participant_id);
        }

        Ok((match_result, fix_reports, alerts))
    }

    /// Cancel an active resting order
    pub fn handle_cancel_order(&mut self, order_id: OrderId) -> Result<FixMessage, &'static str> {
        let order = self.matching_engine.book.cancel_order(order_id)?;

        let now_ns = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64;

        let payload = format!("CANCEL:{}", order_id.0).into_bytes();
        self.wal.append(WalPayloadType::OrderCancelled, payload, now_ns);

        // Record cancellation in surveillance engine
        self.surveillance.on_order_cancelled(
            order_id,
            &order.participant_id,
            order.side,
            order.remaining_quantity,
        );

        self.risk_engine.on_order_closed(&order.participant_id);

        let exec_id = self.next_exec_id();
        let fix_seq = self.next_fix_seq();
        let report = ExecutionReportFactory::create_canceled_report(&order, &order.client_order_id, exec_id, fix_seq);
        Ok(report)
    }

    /// Current Best-Bid-Offer (BBO)
    pub fn get_bbo(&self) -> BestBidOffer {
        let (bid_p, bid_q) = match self.matching_engine.book.best_bid() {
            Some((p, q)) => (Some(p), q),
            None => (None, Quantity::ZERO),
        };
        let (ask_p, ask_q) = match self.matching_engine.book.best_ask() {
            Some((p, q)) => (Some(p), q),
            None => (None, Quantity::ZERO),
        };

        BestBidOffer {
            instrument_id: self.instrument_id.clone(),
            bid_price: bid_p,
            bid_quantity: bid_q,
            ask_price: ask_p,
            ask_quantity: ask_q,
            timestamp_ns: std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos() as u64,
            sequence_number: self.matching_engine.book.sequence_number,
        }
    }

    /// Current L2 Market Depth
    pub fn get_l2_depth(&self, depth: usize) -> L2Snapshot {
        self.matching_engine.book.get_l2_snapshot(depth)
    }
}
