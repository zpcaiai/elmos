use std::fmt;
use std::ops::{Add, Sub};

/// Fixed-point price representation with 4 decimal places (scaled by 10,000).
/// E.g., $150.25 is represented as 1,502,500 ticks.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Default)]
pub struct Price(i64);

impl Price {
    pub const SCALE: i64 = 10_000;
    pub const ZERO: Price = Price(0);
    pub const MIN: Price = Price(1);
    pub const MAX: Price = Price(i64::MAX);

    #[inline(always)]
    pub const fn from_raw(raw: i64) -> Self {
        Price(raw)
    }

    #[inline(always)]
    pub const fn raw(self) -> i64 {
        self.0
    }

    #[inline]
    pub fn from_major_minor(major: i64, minor: i64) -> Self {
        Price(major * Self::SCALE + minor)
    }

    #[inline]
    pub fn from_f64(val: f64) -> Self {
        Price((val * Self::SCALE as f64).round() as i64)
    }

    #[inline]
    pub fn to_f64(self) -> f64 {
        self.0 as f64 / Self::SCALE as f64
    }

    #[inline]
    pub fn is_positive(self) -> bool {
        self.0 > 0
    }

    #[inline]
    pub fn is_zero(self) -> bool {
        self.0 == 0
    }

    #[inline]
    pub fn abs_diff(self, other: Price) -> Price {
        Price((self.0 - other.0).abs())
    }

    #[inline]
    pub fn checked_add(self, other: Price) -> Option<Price> {
        self.0.checked_add(other.0).map(Price)
    }

    #[inline]
    pub fn checked_sub(self, other: Price) -> Option<Price> {
        self.0.checked_sub(other.0).map(Price)
    }
}

impl fmt::Display for Price {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let whole = self.0 / Self::SCALE;
        let frac = (self.0 % Self::SCALE).abs();
        write!(f, "{}.{:04}", whole, frac)
    }
}

impl Add for Price {
    type Output = Self;
    #[inline(always)]
    fn add(self, rhs: Self) -> Self {
        Price(self.0 + rhs.0)
    }
}

impl Sub for Price {
    type Output = Self;
    #[inline(always)]
    fn sub(self, rhs: Self) -> Self {
        Price(self.0 - rhs.0)
    }
}

/// Quantity representing whole or fractional lots.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Default)]
pub struct Quantity(u64);

impl Quantity {
    pub const ZERO: Quantity = Quantity(0);
    pub const MAX: Quantity = Quantity(u64::MAX);

    #[inline(always)]
    pub const fn from_raw(raw: u64) -> Self {
        Quantity(raw)
    }

    #[inline(always)]
    pub const fn raw(self) -> u64 {
        self.0
    }

    #[inline(always)]
    pub const fn is_zero(self) -> bool {
        self.0 == 0
    }

    #[inline]
    pub fn checked_add(self, other: Quantity) -> Option<Quantity> {
        self.0.checked_add(other.0).map(Quantity)
    }

    #[inline]
    pub fn checked_sub(self, other: Quantity) -> Option<Quantity> {
        self.0.checked_sub(other.0).map(Quantity)
    }

    #[inline]
    pub fn saturating_sub(self, other: Quantity) -> Quantity {
        Quantity(self.0.saturating_sub(other.0))
    }
}

impl fmt::Display for Quantity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl Add for Quantity {
    type Output = Self;
    #[inline(always)]
    fn add(self, rhs: Self) -> Self {
        Quantity(self.0 + rhs.0)
    }
}

impl Sub for Quantity {
    type Output = Self;
    #[inline(always)]
    fn sub(self, rhs: Self) -> Self {
        Quantity(self.0 - rhs.0)
    }
}

/// Order Side: Buy or Sell
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Side {
    Buy,
    Sell,
}

impl Side {
    #[inline(always)]
    pub fn opposite(self) -> Side {
        match self {
            Side::Buy => Side::Sell,
            Side::Sell => Side::Buy,
        }
    }

    #[inline]
    pub fn is_buy(self) -> bool {
        matches!(self, Side::Buy)
    }

    #[inline]
    pub fn is_sell(self) -> bool {
        matches!(self, Side::Sell)
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Side::Buy => "BUY",
            Side::Sell => "SELL",
        }
    }
}

impl fmt::Display for Side {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

/// Time in Force (TIF)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum TimeInForce {
    GoodTilCancel,
    ImmediateOrCancel,
    FillOrKill,
    GoodTilDate(u64), // epoch timestamp in micros
    Day,
}

impl Default for TimeInForce {
    fn default() -> Self {
        TimeInForce::GoodTilCancel
    }
}

/// Supported Order Types
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum OrderType {
    Limit,
    Market,
    StopLoss(Price),
    StopLimit { stop_price: Price, limit_price: Price },
    TrailingStop { trailing_delta: Price, high_water_mark: Price },
    Iceberg { peak_size: Quantity },
    PostOnly,
}

/// Execution Status of an Order
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum OrderStatus {
    PendingNew,
    New,
    PartiallyFilled,
    Filled,
    DoneForDay,
    Canceled,
    PendingCancel,
    Stopped,
    Rejected,
    Suspended,
    PendingNewReplace,
    Calculated,
    Expired,
}

impl OrderStatus {
    #[inline]
    pub fn is_terminal(self) -> bool {
        matches!(
            self,
            OrderStatus::Filled
                | OrderStatus::Canceled
                | OrderStatus::Rejected
                | OrderStatus::Expired
        )
    }

    #[inline]
    pub fn is_active(self) -> bool {
        matches!(
            self,
            OrderStatus::New | OrderStatus::PartiallyFilled | OrderStatus::PendingNew
        )
    }
}

/// Self-Trade Prevention (STP) Modes
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum SelfTradePreventionMode {
    #[default]
    None,
    CancelNewest,
    CancelOldest,
    CancelBoth,
    DecrementAndCancel,
}

/// Strongly typed Order ID
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct OrderId(pub u64);

impl fmt::Display for OrderId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "ORD-{}", self.0)
    }
}

/// Strongly typed Trade ID
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct TradeId(pub u64);

impl fmt::Display for TradeId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "TRD-{}", self.0)
    }
}

/// Strongly typed Instrument Symbol Identifier
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct InstrumentId(pub String);

impl InstrumentId {
    pub fn new(sym: impl Into<String>) -> Self {
        InstrumentId(sym.into())
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for InstrumentId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// Strongly typed Participant Identifier (firm, broker, trader)
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ParticipantId(pub String);

impl ParticipantId {
    pub fn new(id: impl Into<String>) -> Self {
        ParticipantId(id.into())
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for ParticipantId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// FIX-compatible Execution Type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ExecType {
    New,
    PartialFill,
    Fill,
    DoneForDay,
    Canceled,
    Replace,
    PendingCancel,
    Stopped,
    Rejected,
    Suspended,
    PendingNew,
    Calculated,
    Expired,
    Restated,
    Trade,
}

/// Currency minor unit value representation
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Default)]
pub struct Money(pub i64);

impl Money {
    pub const ZERO: Money = Money(0);

    pub fn from_price_quantity(price: Price, qty: Quantity) -> Self {
        // Price has scale 10_000, value in major units * 10_000 * qty
        // Minor units (cents, scale 100): (price.raw() * qty.raw()) / (10_000 / 100) = / 100
        let raw = (price.raw() as i128 * qty.raw() as i128) / 100;
        Money(raw as i64)
    }

    pub fn to_decimal(self) -> f64 {
        self.0 as f64 / 100.0
    }
}

impl fmt::Display for Money {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let dollars = self.0 / 100;
        let cents = (self.0 % 100).abs();
        write!(f, "${}.{:02}", dollars, cents)
    }
}
