use crate::core::types::*;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Order {
    pub id: OrderId,
    pub client_order_id: String,
    pub participant_id: ParticipantId,
    pub instrument_id: InstrumentId,
    pub side: Side,
    pub order_type: OrderType,
    pub time_in_force: TimeInForce,
    pub price: Price,
    pub initial_quantity: Quantity,
    pub remaining_quantity: Quantity,
    pub executed_quantity: Quantity,
    pub cumulative_quote_quantity: Money,
    pub status: OrderStatus,
    pub stp_mode: SelfTradePreventionMode,
    pub timestamp_ns: u64,
    pub visible_quantity: Quantity,
    pub hidden_quantity: Quantity,
}

impl Order {
    pub fn new(
        id: OrderId,
        client_order_id: impl Into<String>,
        participant_id: ParticipantId,
        instrument_id: InstrumentId,
        side: Side,
        order_type: OrderType,
        time_in_force: TimeInForce,
        price: Price,
        quantity: Quantity,
        stp_mode: SelfTradePreventionMode,
    ) -> Self {
        let ts = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64;

        let (vis_qty, hid_qty) = match order_type {
            OrderType::Iceberg { peak_size } => {
                let peak = peak_size.raw().min(quantity.raw());
                let rem = quantity.raw() - peak;
                (Quantity::from_raw(peak), Quantity::from_raw(rem))
            }
            _ => (quantity, Quantity::ZERO),
        };

        Order {
            id,
            client_order_id: client_order_id.into(),
            participant_id,
            instrument_id,
            side,
            order_type,
            time_in_force,
            price,
            initial_quantity: quantity,
            remaining_quantity: quantity,
            executed_quantity: Quantity::ZERO,
            cumulative_quote_quantity: Money::ZERO,
            status: OrderStatus::New,
            stp_mode,
            timestamp_ns: ts,
            visible_quantity: vis_qty,
            hidden_quantity: hid_qty,
        }
    }

    #[inline]
    pub fn is_filled(&self) -> bool {
        self.remaining_quantity.is_zero()
    }

    #[inline]
    pub fn leaves_qty(&self) -> Quantity {
        self.remaining_quantity
    }

    #[inline]
    pub fn is_iceberg(&self) -> bool {
        matches!(self.order_type, OrderType::Iceberg { .. })
    }

    /// Execute a fill on the order
    pub fn fill(&mut self, fill_qty: Quantity, exec_price: Price) -> Result<(), &'static str> {
        if fill_qty > self.remaining_quantity {
            return Err("Fill quantity exceeds remaining quantity");
        }

        self.remaining_quantity = self.remaining_quantity - fill_qty;
        self.executed_quantity = self.executed_quantity + fill_qty;

        let trade_value = Money::from_price_quantity(exec_price, fill_qty);
        self.cumulative_quote_quantity = Money(self.cumulative_quote_quantity.0 + trade_value.0);

        if self.remaining_quantity.is_zero() {
            self.status = OrderStatus::Filled;
            self.visible_quantity = Quantity::ZERO;
            self.hidden_quantity = Quantity::ZERO;
        } else {
            self.status = OrderStatus::PartiallyFilled;
            if self.is_iceberg() {
                self.visible_quantity = self.visible_quantity.saturating_sub(fill_qty);
                if self.visible_quantity.is_zero() && !self.hidden_quantity.is_zero() {
                    self.replenish_iceberg();
                }
            } else {
                self.visible_quantity = self.remaining_quantity;
            }
        }

        Ok(())
    }

    /// Replenish visible peak from hidden portion for iceberg orders
    pub fn replenish_iceberg(&mut self) {
        if let OrderType::Iceberg { peak_size } = self.order_type {
            let needed = peak_size.raw().min(self.hidden_quantity.raw());
            self.visible_quantity = Quantity::from_raw(needed);
            self.hidden_quantity = Quantity::from_raw(self.hidden_quantity.raw() - needed);
        }
    }

    /// Cancel remaining quantity
    pub fn cancel(&mut self) -> Result<Quantity, &'static str> {
        if self.status.is_terminal() {
            return Err("Cannot cancel order in terminal status");
        }
        let canceled_qty = self.remaining_quantity;
        self.remaining_quantity = Quantity::ZERO;
        self.visible_quantity = Quantity::ZERO;
        self.hidden_quantity = Quantity::ZERO;
        self.status = OrderStatus::Canceled;
        Ok(canceled_qty)
    }

    /// Mark order as rejected
    pub fn reject(&mut self, _reason: &str) {
        self.status = OrderStatus::Rejected;
        self.remaining_quantity = Quantity::ZERO;
        self.visible_quantity = Quantity::ZERO;
        self.hidden_quantity = Quantity::ZERO;
    }

    /// Decrement quantity (for STP DecrementAndCancel)
    pub fn decrement_qty(&mut self, decr: Quantity) {
        let actual_decr = Quantity::from_raw(decr.raw().min(self.remaining_quantity.raw()));
        self.remaining_quantity = self.remaining_quantity - actual_decr;
        if self.remaining_quantity.is_zero() {
            self.status = OrderStatus::Canceled;
            self.visible_quantity = Quantity::ZERO;
            self.hidden_quantity = Quantity::ZERO;
        } else {
            if self.is_iceberg() {
                self.visible_quantity = Quantity::from_raw(self.visible_quantity.raw().saturating_sub(actual_decr.raw()));
                if self.visible_quantity.is_zero() {
                    self.replenish_iceberg();
                }
            } else {
                self.visible_quantity = self.remaining_quantity;
            }
        }
    }
}

pub struct OrderBuilder {
    id: Option<OrderId>,
    client_order_id: Option<String>,
    participant_id: Option<ParticipantId>,
    instrument_id: Option<InstrumentId>,
    side: Option<Side>,
    order_type: OrderType,
    time_in_force: TimeInForce,
    price: Price,
    quantity: Quantity,
    stp_mode: SelfTradePreventionMode,
}

impl OrderBuilder {
    pub fn new() -> Self {
        OrderBuilder {
            id: None,
            client_order_id: None,
            participant_id: None,
            instrument_id: None,
            side: None,
            order_type: OrderType::Limit,
            time_in_force: TimeInForce::GoodTilCancel,
            price: Price::ZERO,
            quantity: Quantity::ZERO,
            stp_mode: SelfTradePreventionMode::None,
        }
    }

    pub fn id(mut self, id: OrderId) -> Self {
        self.id = Some(id);
        self
    }

    pub fn client_order_id(mut self, cl_ord_id: impl Into<String>) -> Self {
        self.client_order_id = Some(cl_ord_id.into());
        self
    }

    pub fn participant_id(mut self, pid: impl Into<String>) -> Self {
        self.participant_id = Some(ParticipantId::new(pid));
        self
    }

    pub fn instrument_id(mut self, sym: impl Into<String>) -> Self {
        self.instrument_id = Some(InstrumentId::new(sym));
        self
    }

    pub fn side(mut self, side: Side) -> Self {
        self.side = Some(side);
        self
    }

    pub fn order_type(mut self, ot: OrderType) -> Self {
        self.order_type = ot;
        self
    }

    pub fn time_in_force(mut self, tif: TimeInForce) -> Self {
        self.time_in_force = tif;
        self
    }

    pub fn price(mut self, price: Price) -> Self {
        self.price = price;
        self
    }

    pub fn quantity(mut self, qty: Quantity) -> Self {
        self.quantity = qty;
        self
    }

    pub fn stp_mode(mut self, stp: SelfTradePreventionMode) -> Self {
        self.stp_mode = stp;
        self
    }

    pub fn build(self) -> Result<Order, &'static str> {
        let id = self.id.ok_or("OrderId is required")?;
        let client_order_id = self.client_order_id.unwrap_or_else(|| format!("CL-{}", id.0));
        let participant_id = self.participant_id.ok_or("ParticipantId is required")?;
        let instrument_id = self.instrument_id.ok_or("InstrumentId is required")?;
        let side = self.side.ok_or("Side is required")?;

        if self.quantity.is_zero() {
            return Err("Quantity must be positive");
        }

        if matches!(self.order_type, OrderType::Limit | OrderType::PostOnly) && !self.price.is_positive() {
            return Err("Limit price must be positive");
        }

        Ok(Order::new(
            id,
            client_order_id,
            participant_id,
            instrument_id,
            side,
            self.order_type,
            self.time_in_force,
            self.price,
            self.quantity,
            self.stp_mode,
        ))
    }
}
