use crate::core::types::*;
use crate::core::order::Order;
use std::sync::mpsc::{channel, Sender, Receiver};

#[derive(Debug, Clone)]
pub enum OrderCommand {
    Submit(Order),
    Cancel { order_id: OrderId, participant_id: ParticipantId },
    HaltTrading { reason: String },
    ResumeTrading,
}

pub struct OrderDispatcher {
    sender: Sender<OrderCommand>,
    receiver: Receiver<OrderCommand>,
}

impl OrderDispatcher {
    pub fn new() -> Self {
        let (sender, receiver) = channel();
        OrderDispatcher { sender, receiver }
    }

    pub fn sender(&self) -> Sender<OrderCommand> {
        self.sender.clone()
    }

    pub fn poll_command(&self) -> Option<OrderCommand> {
        self.receiver.try_recv().ok()
    }
}
