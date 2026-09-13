use crate::core::types::*;
use crate::market_data::trades::TradeTick;
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Timeframe {
    Second1,
    Second5,
    Minute1,
    Minute5,
    Hour1,
    Day1,
}

impl Timeframe {
    pub fn duration_secs(&self) -> u64 {
        match self {
            Timeframe::Second1 => 1,
            Timeframe::Second5 => 5,
            Timeframe::Minute1 => 60,
            Timeframe::Minute5 => 300,
            Timeframe::Hour1 => 3600,
            Timeframe::Day1 => 86400,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Candlestick {
    pub timeframe: Timeframe,
    pub bucket_timestamp_secs: u64,
    pub open: Price,
    pub high: Price,
    pub low: Price,
    pub close: Price,
    pub volume: Quantity,
    pub turnover: Money,
    pub trades_count: usize,
}

impl Candlestick {
    pub fn new(timeframe: Timeframe, bucket_timestamp_secs: u64, price: Price, qty: Quantity) -> Self {
        let value = Money::from_price_quantity(price, qty);
        Candlestick {
            timeframe,
            bucket_timestamp_secs,
            open: price,
            high: price,
            low: price,
            close: price,
            volume: qty,
            turnover: value,
            trades_count: 1,
        }
    }

    pub fn update(&mut self, price: Price, qty: Quantity) {
        if price > self.high {
            self.high = price;
        }
        if price < self.low {
            self.low = price;
        }
        self.close = price;
        self.volume = self.volume + qty;
        let value = Money::from_price_quantity(price, qty);
        self.turnover = Money(self.turnover.0 + value.0);
        self.trades_count += 1;
    }
}

pub struct OhlcvAggregator {
    active_candles: HashMap<Timeframe, Candlestick>,
    completed_candles: HashMap<Timeframe, Vec<Candlestick>>,
}

impl OhlcvAggregator {
    pub fn new() -> Self {
        OhlcvAggregator {
            active_candles: HashMap::new(),
            completed_candles: HashMap::new(),
        }
    }

    pub fn on_trade(&mut self, trade: &TradeTick) {
        let trade_secs = trade.timestamp_ns / 1_000_000_000;

        let timeframes = [
            Timeframe::Second1,
            Timeframe::Second5,
            Timeframe::Minute1,
            Timeframe::Minute5,
            Timeframe::Hour1,
        ];

        for &tf in &timeframes {
            let dur = tf.duration_secs();
            let bucket = (trade_secs / dur) * dur;

            if let Some(active) = self.active_candles.get_mut(&tf) {
                if active.bucket_timestamp_secs == bucket {
                    active.update(trade.price, trade.quantity);
                } else {
                    let old = std::mem::replace(
                        active,
                        Candlestick::new(tf, bucket, trade.price, trade.quantity),
                    );
                    self.completed_candles.entry(tf).or_default().push(old);
                }
            } else {
                self.active_candles.insert(
                    tf,
                    Candlestick::new(tf, bucket, trade.price, trade.quantity),
                );
            }
        }
    }

    pub fn get_active_candle(&self, tf: Timeframe) -> Option<&Candlestick> {
        self.active_candles.get(&tf)
    }

    pub fn get_completed_candles(&self, tf: Timeframe) -> &[Candlestick] {
        self.completed_candles.get(&tf).map(|v| v.as_slice()).unwrap_or(&[])
    }
}
