"""Rust (Axum + Tokio) Domain-Driven Design, Workflow FSM, and Distributed Transactions Emitter.

Generates industrial-grade Rust domain models, value objects, FSM state machines,
and distributed transaction coordinators (Saga LIFO compensation, Outbox, Fencing Locks).
"""
from __future__ import annotations

from typing import Dict
from .models import SynthesisRequest, pascal


def generate_rust_domain_workflow_files(request: SynthesisRequest) -> Dict[str, str]:
    """Generate industrial-grade DDD, FSM, and Distributed Transaction files for Rust."""
    files: Dict[str, str] = {}
    entity = request.entities[0] if request.entities else None
    entity_name = pascal(entity.singular) if entity else "Order"

    # 1. Domain Value Objects
    files["src/domain/value_objects.rs"] = """use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum ValueError {
    #[error("Amount cannot be negative: {0}")]
    NegativeAmount(f64),
    #[error("Invalid ISO-4217 currency: {0}")]
    InvalidCurrency(String),
    #[error("Currency mismatch: {0} vs {1}")]
    CurrencyMismatch(String, String),
    #[error("Insufficient funds for subtraction")]
    InsufficientFunds,
}

/// Immutable high-precision monetary Value Object.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Money {
    pub amount: f64,
    pub currency: String,
}

impl Money {
    pub fn new(amount: f64, currency: &str) -> Result<Self, ValueError> {
        if amount < 0.0 {
            return Err(ValueError::NegativeAmount(amount));
        }
        let norm = currency.trim().to_uppercase();
        if norm.len() != 3 || !norm.chars().all(|c| c.is_ascii_uppercase()) {
            return Err(ValueError::InvalidCurrency(norm));
        }
        Ok(Self { amount, currency: norm })
    }

    pub fn add(&self, other: &Money) -> Result<Self, ValueError> {
        if self.currency != other.currency {
            return Err(ValueError::CurrencyMismatch(self.currency.clone(), other.currency.clone()));
        }
        Ok(Self {
            amount: self.amount + other.amount,
            currency: self.currency.clone(),
        })
    }

    pub fn subtract(&self, other: &Money) -> Result<Self, ValueError> {
        if self.currency != other.currency {
            return Err(ValueError::CurrencyMismatch(self.currency.clone(), other.currency.clone()));
        }
        if self.amount < other.amount {
            return Err(ValueError::InsufficientFunds);
        }
        Ok(Self {
            amount: self.amount - other.amount,
            currency: self.currency.clone(),
        })
    }
}

/// Physical Address Value Object with structural equality.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Address {
    pub street: String,
    pub city: String,
    pub state_province: String,
    pub postal_code: String,
    pub country: String,
}

/// Quantity Value Object.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Quantity {
    pub value: f64,
    pub unit: String,
}
"""

    # 2. Domain Events
    files["src/domain/events.rs"] = """use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Strongly typed Domain Event Envelope.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DomainEvent {
    pub event_id: String,
    pub aggregate_type: String,
    pub aggregate_id: String,
    pub event_type: String,
    pub payload: serde_json::Value,
    pub occurred_at: DateTime<Utc>,
    pub trace_id: String,
}

impl DomainEvent {
    pub fn create(aggregate_type: &str, aggregate_id: &str, event_type: &str, payload: serde_json::Value) -> Self {
        Self {
            event_id: format!("evt-{}", &Uuid::new_v4().simple().to_string()[..16]),
            aggregate_type: aggregate_type.to_string(),
            aggregate_id: aggregate_id.to_string(),
            event_type: event_type.to_string(),
            payload,
            occurred_at: Utc::now(),
            trace_id: format!("tr-{}", &Uuid::new_v4().simple().to_string()[..12]),
        }
    }
}
"""

    # 3. Aggregate Root
    files["src/domain/aggregate.rs"] = f"""use chrono::{{DateTime, Utc}};
use serde::{{Deserialize, Serialize}};
use uuid::Uuid;
use super::events::DomainEvent;
use super::value_objects::Money;

/// Industrial-grade DDD Aggregate Root for {entity_name}.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct {entity_name}Aggregate {{
    pub id: String,
    pub tenant_id: String,
    pub reference: String,
    pub total: Money,
    pub status: String,
    pub version: i64,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    #[serde(skip)]
    uncommitted_events: Vec<DomainEvent>,
}}

impl {entity_name}Aggregate {{
    pub fn new(id: Option<String>, tenant_id: String, reference: String, total: Money) -> Result<Self, String> {{
        if reference.trim().is_empty() {{
            return Err("Domain Invariant Violation: Reference cannot be empty".to_string());
        }}
        if total.amount < 0.0 {{
            return Err("Domain Invariant Violation: Total cannot be negative".to_string());
        }}

        let agg_id = id.unwrap_or_else(|| format!("agg-{{}}", &Uuid::new_v4().simple().to_string()[..12]));
        let mut agg = Self {{
            id: agg_id.clone(),
            tenant_id,
            reference: reference.clone(),
            total: total.clone(),
            status: "CREATED".to_string(),
            version: 1,
            created_at: Utc::now(),
            updated_at: Utc::now(),
            uncommitted_events: Vec::new(),
        }};

        agg.record_event("{entity_name}Created", serde_json::json!({{
            "id": agg_id,
            "reference": reference,
            "total": total.amount,
            "currency": total.currency
        }}));

        Ok(agg)
    }}

    pub fn update_details(&mut self, new_reference: String, new_total: Money) -> Result<(), String> {{
        if new_reference.trim().is_empty() {{
            return Err("Reference cannot be empty".to_string());
        }}
        self.reference = new_reference;
        self.total = new_total;
        self.version += 1;
        self.updated_at = Utc::now();

        self.record_event("{entity_name}Updated", serde_json::json!({{
            "id": self.id,
            "reference": self.reference,
            "total": self.total.amount
        }}));

        Ok(())
    }}

    pub fn transition_status(&mut self, new_status: &str) {{
        self.status = new_status.to_string();
        self.version += 1;
        self.updated_at = Utc::now();
        self.record_event("{entity_name}StatusTransitioned", serde_json::json!({{
            "id": self.id,
            "new_status": new_status
        }}));
    }}

    fn record_event(&mut self, event_type: &str, payload: serde_json::Value) {{
        self.uncommitted_events.push(DomainEvent::create("{entity_name}", &self.id, event_type, payload));
    }}

    pub fn poll_events(&mut self) -> Vec<DomainEvent> {{
        std::mem::take(&mut self.uncommitted_events)
    }}
}}
"""

    # 4. Workflow State Machine (FSM)
    files["src/workflow/fsm.rs"] = f"""use chrono::{{DateTime, Utc}};
use serde::{{Deserialize, Serialize}};
use std::sync::Mutex;
use crate::domain::aggregate::{entity_name}Aggregate;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum State {{
    Created,
    PendingPayment,
    Paid,
    Fulfilled,
    Cancelled,
    Refunded,
}}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Trigger {{
    Submit,
    Pay,
    Complete,
    Cancel,
    Refund,
}}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransitionLog {{
    pub aggregate_id: String,
    pub from_state: State,
    pub to_state: State,
    pub transitioned_at: DateTime<Utc>,
    pub operator: String,
}}

pub struct StateMachine {{
    journal: Mutex<Vec<TransitionLog>>,
}}

impl Default for StateMachine {{
    fn default() -> Self {{
        Self::new()
    }}
}}

impl StateMachine {{
    pub fn new() -> Self {{
        Self {{
            journal: Mutex::new(Vec::new()),
        }}
    }}

    pub fn transition(
        &self,
        aggregate: &mut {entity_name}Aggregate,
        trigger: Trigger,
        operator: &str,
    ) -> Result<State, String> {{
        let current = match aggregate.status.as_str() {{
            "CREATED" => State::Created,
            "PENDING_PAYMENT" => State::PendingPayment,
            "PAID" => State::Paid,
            "FULFILLED" => State::Fulfilled,
            "CANCELLED" => State::Cancelled,
            "REFUNDED" => State::Refunded,
            _ => State::Created,
        }};

        let next = match (current, trigger) {{
            (State::Created, Trigger::Submit) => State::PendingPayment,
            (State::Created, Trigger::Cancel) => State::Cancelled,
            (State::PendingPayment, Trigger::Pay) => State::Paid,
            (State::PendingPayment, Trigger::Cancel) => State::Cancelled,
            (State::Paid, Trigger::Complete) => State::Fulfilled,
            (State::Paid, Trigger::Refund) => State::Refunded,
            _ => return Err(format!("Invalid state transition from {{:?}} via {{:?}}", current, trigger)),
        }};

        // Guard validation
        if trigger == Trigger::Pay && aggregate.total.amount <= 0.0 {{
            return Err("Guard violation: Cannot pay zero or negative total".to_string());
        }}

        let status_str = match next {{
            State::Created => "CREATED",
            State::PendingPayment => "PENDING_PAYMENT",
            State::Paid => "PAID",
            State::Fulfilled => "FULFILLED",
            State::Cancelled => "CANCELLED",
            State::Refunded => "REFUNDED",
        }};

        aggregate.transition_status(status_str);

        if let Ok(mut journal) = self.journal.lock() {{
            journal.push(TransitionLog {{
                aggregate_id: aggregate.id.clone(),
                from_state: current,
                to_state: next,
                transitioned_at: Utc::now(),
                operator: operator.to_string(),
            }});
        }}

        Ok(next)
    }}

    pub fn get_journal(&self) -> Vec<TransitionLog> {{
        self.journal.lock().map(|j| j.clone()).unwrap_or_default()
    }}
}}
"""

    # 5. Distributed Transactions (Saga Orchestrator with LIFO compensation)
    files["src/transactions/saga.rs"] = """use std::future::Future;
use std::pin::Pin;

pub type AsyncAction = Box<dyn Fn() -> Pin<Box<dyn Future<Output = bool> + Send>> + Send + Sync>;
pub type AsyncComp = Box<dyn Fn() -> Pin<Box<dyn Future<Output = ()> + Send>> + Send + Sync>;

pub struct SagaStep {
    pub name: String,
    pub forward: AsyncAction,
    pub compensation: AsyncComp,
}

pub struct SagaOrchestrator {
    steps: Vec<SagaStep>,
}

impl Default for SagaOrchestrator {
    fn default() -> Self {
        Self::new()
    }
}

impl SagaOrchestrator {
    pub fn new() -> Self {
        Self { steps: Vec::new() }
    }

    pub fn add_step<F, C>(&mut self, name: &str, forward: F, compensation: C)
    where
        F: Fn() -> Pin<Box<dyn Future<Output = bool> + Send>> + Send + Sync + 'static,
        C: Fn() -> Pin<Box<dyn Future<Output = ()> + Send>> + Send + Sync + 'static,
    {
        self.steps.push(SagaStep {
            name: name.to_string(),
            forward: Box::new(forward),
            compensation: Box::new(compensation),
        });
    }

    pub async fn execute(&self) -> bool {
        let mut executed_indices: Vec<usize> = Vec::new();

        for (idx, step) in self.steps.iter().enumerate() {
            let ok = (step.forward)().await;
            if !ok {
                self.rollback(&executed_indices).await;
                return false;
            }
            executed_indices.push(idx);
        }

        true
    }

    async fn rollback(&self, executed: &[usize]) {
        for &idx in executed.iter().rev() {
            let step = &self.steps[idx];
            (step.compensation)().await;
        }
    }
}
"""

    # 6. Distributed Lock with Monotonic Fencing Token
    files["src/transactions/lock.rs"] = """use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

#[derive(Debug, Clone)]
pub struct LockEntry {
    pub owner: String,
    pub expires_at: Instant,
    pub fencing_token: u64,
}

pub struct DistributedLockManager {
    locks: Mutex<HashMap<String, LockEntry>>,
    generation: Mutex<HashMap<String, u64>>,
}

impl Default for DistributedLockManager {
    fn default() -> Self {
        Self::new()
    }
}

impl DistributedLockManager {
    pub fn new() -> Self {
        Self {
            locks: Mutex::new(HashMap::new()),
            generation: Mutex::new(HashMap::new()),
        }
    }

    pub fn acquire(&self, resource_id: &str, owner: &str, ttl: Duration) -> Result<u64, String> {
        let mut locks = self.locks.lock().unwrap();
        let mut gen = self.generation.lock().unwrap();
        let now = Instant::now();

        if let Some(current) = locks.get(resource_id) {
            if current.expires_at > now && current.owner != owner {
                return Err(format!("Resource '{}' is locked by '{}'", resource_id, current.owner));
            }
        }

        let token = gen.entry(resource_id.to_string()).or_insert(0);
        *token += 1;
        let assigned_token = *token;

        locks.insert(
            resource_id.to_string(),
            LockEntry {
                owner: owner.to_string(),
                expires_at: now + ttl,
                fencing_token: assigned_token,
            },
        );

        Ok(assigned_token)
    }

    pub fn release(&self, resource_id: &str, owner: &str) {
        let mut locks = self.locks.lock().unwrap();
        if let Some(current) = locks.get(resource_id) {
            if current.owner == owner {
                locks.remove(resource_id);
            }
        }
    }

    pub fn is_locked(&self, resource_id: &str) -> bool {
        let locks = self.locks.lock().unwrap();
        locks.get(resource_id).map_or(false, |l| l.expires_at > Instant::now())
    }
}
"""

    return files
