"""Go (Gin + GORM) Domain-Driven Design, Workflow FSM, and Distributed Transactions Emitter.

Generates complete industrial-grade Go domain models, value objects, concurrency-safe state machines,
and distributed transaction coordinators.
"""
from __future__ import annotations

from typing import Dict
from .models import SynthesisRequest, pascal


def generate_go_domain_workflow_files(request: SynthesisRequest) -> Dict[str, str]:
    """Generate industrial-grade DDD, FSM, and Distributed Transaction files for Go."""
    files: Dict[str, str] = {}
    app_name = request.project_name.lower().replace("_", "-")
    entity = request.entities[0] if request.entities else None
    entity_name = pascal(entity.singular) if entity else "Order"

    # 1. Domain Value Objects
    files["domain/value_objects.go"] = """package domain

import (
\t"errors"
\t"fmt"
\t"math/big"
\t"regexp"
\t"strings"
)

var currencyRegex = regexp.MustCompile(`^[A-Z]{3}$`)

// Money represents an immutable high-precision monetary value.
type Money struct {
\tAmount   *big.Float `json:"amount"`
\tCurrency string     `json:"currency"`
}

func NewMoney(amount float64, currency string) (*Money, error) {
\tcurr := strings.ToUpper(strings.TrimSpace(currency))
\tif !currencyRegex.MatchString(curr) {
\t\treturn nil, fmt.Errorf("invalid ISO-4217 currency code: %s", curr)
\t}
\tif amount < 0 {
\t\treturn nil, errors.New("amount cannot be negative")
\t}
\treturn &Money{Amount: big.NewFloat(amount), Currency: curr}, nil
}

func (m *Money) Add(other *Money) (*Money, error) {
\tif m.Currency != other.Currency {
\t\treturn nil, fmt.Errorf("currency mismatch: %s vs %s", m.Currency, other.Currency)
\t}
\tres := new(big.Float).Add(m.Amount, other.Amount)
\treturn &Money{Amount: res, Currency: m.Currency}, nil
}

func (m *Money) Subtract(other *Money) (*Money, error) {
\tif m.Currency != other.Currency {
\t\treturn nil, fmt.Errorf("currency mismatch: %s vs %s", m.Currency, other.Currency)
\t}
\tif m.Amount.Cmp(other.Amount) < 0 {
\t\treturn nil, errors.New("insufficient funds for subtraction")
\t}
\tres := new(big.Float).Sub(m.Amount, other.Amount)
\treturn &Money{Amount: res, Currency: m.Currency}, nil
}

// Address value object
type Address struct {
\tStreet        string `json:"street"`
\tCity          string `json:"city"`
\tStateProvince string `json:"state_province"`
\tPostalCode    string `json:"postal_code"`
\tCountry       string `json:"country"`
}

func NewAddress(street, city, state, postal, country string) (*Address, error) {
\tif strings.TrimSpace(street) == "" || strings.TrimSpace(city) == "" || strings.TrimSpace(postal) == "" {
\t\treturn nil, errors.New("address fields cannot be empty")
\t}
\treturn &Address{
\t\tStreet:        street,
\t\tCity:          city,
\t\tStateProvince: state,
\t\tPostalCode:    postal,
\t\tCountry:       country,
\t}, nil
}
"""

    # 2. Domain Events
    files["domain/events.go"] = f"""package domain

import (
\t"time"
\t"github.com/google/uuid"
)

type DomainEvent struct {{
\tEventID       string                 `json:"event_id"`
\tAggregateType string                 `json:"aggregate_type"`
\tAggregateID   string                 `json:"aggregate_id"`
\tEventType     string                 `json:"event_type"`
\tOccurredAt    time.Time              `json:"occurred_at"`
\tPayload       map[string]interface{{}} `json:"payload"`
\tTenantID      string                 `json:"tenant_id"`
}}

func NewDomainEvent(aggregateType, aggregateID, eventType string, payload map[string]interface{{}}) DomainEvent {{
\treturn DomainEvent{{
\t\tEventID:       "evt-" + uuid.New().String()[:16],
\t\tAggregateType: aggregateType,
\t\tAggregateID:   aggregateID,
\t\tEventType:     eventType,
\t\tOccurredAt:    time.Now().UTC(),
\t\tPayload:       payload,
\t\tTenantID:      "default",
\t}}
}}
"""

    # 3. Domain Aggregate Root & Invariants
    files["domain/aggregate.go"] = f"""package domain

import (
\t"errors"
\t"fmt"
\t"math/big"
\t"github.com/google/uuid"
)

type {entity_name}Item struct {{
\tItemID    string     `json:"item_id"`
\tName      string     `json:"name"`
\tUnitPrice *big.Float `json:"unit_price"`
\tQuantity  int64      `json:"quantity"`
}}

type {entity_name}Aggregate struct {{
\tID          string             `json:"id"`
\tTenantID    string             `json:"tenant_id"`
\tStatus      string             `json:"status"` // DRAFT, SUBMITTED, APPROVED, FULFILLED, CANCELLED
\tItems       []{entity_name}Item    `json:"items"`
\tTotalAmount *Money             `json:"total_amount"`
\tVersion     int64              `json:"version"`
\tevents      []DomainEvent
}}

func New{entity_name}Aggregate(tenantID string) *{entity_name}Aggregate {{
\tzeroMoney, _ := NewMoney(0, "USD")
\treturn &{entity_name}Aggregate{{
\t\tID:          "{entity_name.lower()}-" + uuid.New().String()[:12],
\t\tTenantID:    tenantID,
\t\tStatus:      "DRAFT",
\t\tItems:       make([]{entity_name}Item, 0),
\t\tTotalAmount: zeroMoney,
\t\tVersion:     1,
\t\tevents:      make([]DomainEvent, 0),
\t}}
}}

func (a *{entity_name}Aggregate) AddItem(name string, unitPrice float64, quantity int64) error {{
\tif a.Status != "DRAFT" {{
\t\treturn fmt.Errorf("cannot mutate items in status %s", a.Status)
\t}}
\tif quantity <= 0 || unitPrice <= 0 {{
\t\treturn errors.New("quantity and unit price must be positive")
\t}}

\titem := {entity_name}Item{{
\t\tItemID:    "itm-" + uuid.New().String()[:8],
\t\tName:      name,
\t\tUnitPrice: big.NewFloat(unitPrice),
\t\tQuantity:  quantity,
\t}}
\ta.Items = append(a.Items, item)
\ta.recalculateTotal()
\treturn nil
}}

func (a *{entity_name}Aggregate) Submit() error {{
\tif len(a.Items) == 0 {{
\t\treturn errors.New("cannot submit aggregate without items")
\t}}
\tif a.TotalAmount.Amount.Cmp(big.NewFloat(0)) <= 0 {{
\t\treturn errors.New("total amount must be greater than zero")
\t}}

\toldStatus := a.Status
\ta.Status = "SUBMITTED"
\ta.Version++
\ta.events = append(a.events, NewDomainEvent("{entity_name}", a.ID, "{entity_name}Submitted", map[string]interface{{}}{{
\t\t"old_status": oldStatus,
\t\t"new_status": a.Status,
\t}}))
\treturn nil
}}

func (a *{entity_name}Aggregate) Cancel(reason string) error {{
\tif a.Status == "FULFILLED" || a.Status == "CANCELLED" {{
\t\treturn fmt.Errorf("cannot cancel aggregate in status %s", a.Status)
\t}}
\ta.Status = "CANCELLED"
\ta.Version++
\ta.events = append(a.events, NewDomainEvent("{entity_name}", a.ID, "{entity_name}Cancelled", map[string]interface{{}}{{
\t\t"reason": reason,
\t}}))
\treturn nil
}}

func (a *{entity_name}Aggregate) recalculateTotal() {{
\ttotal := big.NewFloat(0)
\tfor _, itm := range a.Items {{
\t\tsub := new(big.Float).Mul(itm.UnitPrice, big.NewFloat(float64(itm.Quantity)))
\t\ttotal.Add(total, sub)
\t}}
\ta.TotalAmount.Amount = total
}}

func (a *{entity_name}Aggregate) PollEvents() []DomainEvent {{
\tcopied := make([]DomainEvent, len(a.events))
\tcopy(copied, a.events)
\ta.events = make([]DomainEvent, 0)
\treturn copied
}}
"""

    # 4. Concurrency-Safe Workflow State Machine
    files["workflow/fsm.go"] = f"""package workflow

import (
\t"fmt"
\t"sync"
\t"time"
)

type StateTransitionLog struct {{
\tTransitionID string    `json:"transition_id"`
\tAggregateID  string    `json:"aggregate_id"`
\tFromState    string    `json:"from_state"`
\tToState      string    `json:"to_state"`
\tEvent        string    `json:"event"`
\tTimestamp    time.Time `json:"timestamp"`
\tVersion      int64     `json:"version"`
}}

type {entity_name}StateMachine struct {{
\tmu          sync.RWMutex
\ttransitions map[string]string
\tlogs        []StateTransitionLog
}}

func New{entity_name}StateMachine() *{entity_name}StateMachine {{
\treturn &{entity_name}StateMachine{{
\t\ttransitions: map[string]string{{
\t\t\t"DRAFT:submit":     "SUBMITTED",
\t\t\t"SUBMITTED:approve": "APPROVED",
\t\t\t"SUBMITTED:reject":  "REJECTED",
\t\t\t"APPROVED:fulfill":  "FULFILLED",
\t\t\t"DRAFT:cancel":      "CANCELLED",
\t\t\t"SUBMITTED:cancel":  "CANCELLED",
\t\t\t"APPROVED:cancel":   "CANCELLED",
\t\t}},
\t\tlogs: make([]StateTransitionLog, 0),
\t}}
}}

func (f *{entity_name}StateMachine) CanTransition(currentState, event string) bool {{
\tf.mu.RLock()
\tdefer f.mu.RUnlock()
\tkey := currentState + ":" + event
\t_, ok := f.transitions[key]
\treturn ok
}}

func (f *{entity_name}StateMachine) ExecuteTransition(aggregateID, currentState, event string, currentVersion int64) (string, int64, *StateTransitionLog, error) {{
\tf.mu.Lock()
\tdefer f.mu.Unlock()

\tkey := currentState + ":" + event
\ttargetState, ok := f.transitions[key]
\tif !ok {{
\t\treturn "", currentVersion, nil, fmt.Errorf("illegal state transition from %s on event %s", currentState, event)
\t}}

\tnewVersion := currentVersion + 1
\tlog := StateTransitionLog{{
\t\tTransitionID: fmt.Sprintf("trn-%d", len(f.logs)+1),
\t\tAggregateID:  aggregateID,
\t\tFromState:    currentState,
\t\tToState:      targetState,
\t\tEvent:        event,
\t\tTimestamp:    time.Now().UTC(),
\t\tVersion:      newVersion,
\t}}
\tf.logs = append(f.logs, log)
\treturn targetState, newVersion, &log, nil
}}
"""

    # 5. Distributed Transactions: Saga Coordinator
    files["transactions/saga.go"] = f"""package transactions

import (
\t"errors"
\t"log"
)

type SagaStep struct {{
\tName         string
\tAction       func(ctx map[string]interface{{}}) (map[string]interface{{}}, error)
\tCompensation func(ctx map[string]interface{{}}) error
}}

type {entity_name}SagaCoordinator struct {{
\tSteps []SagaStep
}}

func New{entity_name}SagaCoordinator(steps []SagaStep) *{entity_name}SagaCoordinator {{
\treturn &{entity_name}SagaCoordinator{{Steps: steps}}
}}

func (s *{entity_name}SagaCoordinator) Execute(ctx map[string]interface{{}}) (bool, string, map[string]interface{{}}) {{
\tcompleted := make([]SagaStep, 0)

\t// Forward Phase
\tfor _, step := range s.Steps {{
\t\tout, err := step.Action(ctx)
\t\tif err != nil {{
\t\t\tlog.Printf("Saga step %s failed: %v. Triggering LIFO compensation.", step.Name, err)
\t\t\ts.rollback(completed, ctx)
\t\t\treturn false, "step failed: " + err.Error(), ctx
\t\t}}
\t\tfor k, v := range out {{
\t\t\tctx[k] = v
\t\t}}
\t\tcompleted = append(completed, step)
\t}}

\treturn true, "saga completed successfully", ctx
}}
func (s *{entity_name}SagaCoordinator) rollback(completed []SagaStep, ctx map[string]interface{{}}) {{
\t// LIFO reverse compensation
\tfor i := len(completed) - 1; i >= 0; i-- {{
\t\tstep := completed[i]
\t\tif err := step.Compensation(ctx); err != nil {{
\t\t\tlog.Printf("Critical: Saga compensation of %s failed: %v", step.Name, err)
\t\t}}
\t}}
}}

type SagaOrchestrator = {entity_name}SagaCoordinator
"""

    # 6. Transactional Outbox Pattern
    files["transactions/outbox.go"] = """package transactions

import (
\t"sync"
\t"time"
)

type OutboxRecord struct {
\tEventID    string                 `json:"event_id"`
\tTenantID   string                 `json:"tenant_id"`
\tEventType  string                 `json:"event_type"`
\tPayload    map[string]interface{} `json:"payload"`
\tStatus     string                 `json:"status"` // PENDING, IN_FLIGHT, PUBLISHED, FAILED
\tRetryCount int                    `json:"retry_count"`
\tCreatedAt  time.Time              `json:"created_at"`
}

type OutboxDispatcher struct {
\tmu        sync.Mutex
\trecords   map[string]*OutboxRecord
\tpublisher func(record *OutboxRecord) bool
}

func NewOutboxDispatcher(publisher func(record *OutboxRecord) bool) *OutboxDispatcher {
\treturn &OutboxDispatcher{
\t\trecords:   make(map[string]*OutboxRecord),
\t\tpublisher: publisher,
\t}
}

func (d *OutboxDispatcher) Enqueue(rec *OutboxRecord) {
\td.mu.Lock()
\tdefer d.mu.Unlock()
\td.records[rec.EventID] = rec
}

func (d *OutboxDispatcher) DispatchPending() int {
\td.mu.Lock()
\tdefer d.mu.Unlock()

\tpublished := 0
\tfor _, rec := range d.records {
\t\tif rec.Status == "PENDING" {
\t\t\trec.Status = "IN_FLIGHT"
\t\t\tok := d.publisher(rec)
\t\t\tif ok {
\t\t\t\trec.Status = "PUBLISHED"
\t\t\t\tpublished++
\t\t\t} else {
\t\t\t\trec.Status = "FAILED"
\t\t\t\trec.RetryCount++
\t\t\t}
\t\t}
\t}
\treturn published
}
"""

    # 7. Distributed Lock with Fencing
    files["transactions/lock.go"] = """package transactions

import (
\t"errors"
\t"sync"
\t"time"
)

type LockEntry struct {
\tOwner     string
\tExpiresAt time.Time
\tToken     int64
}

type DistributedLockManager struct {
\tmu         sync.Mutex
\tlocks      map[string]LockEntry
\tgenerators map[string]int64
}

func NewDistributedLockManager() *DistributedLockManager {
\treturn &DistributedLockManager{
\t\tlocks:      make(map[string]LockEntry),
\t\tgenerators: make(map[string]int64),
\t}
}

func (m *DistributedLockManager) Acquire(resourceKey, owner string, ttl time.Duration) (int64, error) {
\tm.mu.Lock()
\tdefer m.mu.Unlock()

\tnow := time.Now()
\tif lock, exists := m.locks[resourceKey]; exists && lock.ExpiresAt.After(now) && lock.Owner != owner {
\t\treturn 0, errors.New("resource already locked")
\t}

\ttoken := m.generators[resourceKey] + 1
\tm.generators[resourceKey] = token
\tm.locks[resourceKey] = LockEntry{
\t\tOwner:     owner,
\t\tExpiresAt: now.Add(ttl),
\t\tToken:     token,
\t}
\treturn token, nil
}

func (m *DistributedLockManager) Release(resourceKey, owner string) {
\tm.mu.Lock()
\tdefer m.mu.Unlock()

\tif lock, exists := m.locks[resourceKey]; exists && lock.Owner == owner {
\t\tdelete(m.locks, resourceKey)
\t}
}
"""

    return files
