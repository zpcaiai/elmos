"""TypeScript (NestJS) Domain-Driven Design, Workflow FSM, and Distributed Transactions Emitter.

Generates complete industrial-grade NestJS domain layers, value objects, FSM machines, and distributed
transaction coordinators.
"""

from __future__ import annotations

from .models import SynthesisRequest, pascal


def generate_typescript_domain_workflow_files(request: SynthesisRequest) -> dict[str, str]:
    """Generate industrial-grade DDD, FSM, and Distributed Transaction files for TypeScript."""
    files: dict[str, str] = {}
    entity = request.entities[0] if request.entities else None
    entity_name = pascal(entity.singular) if entity else "Order"

    # 1. Domain Value Objects
    files["src/domain/value-objects.ts"] = """/**
 * Domain Value Objects with structural immutability and invariant checks.
 */

export class Money {
  readonly amount: number;
  readonly currency: string;

  constructor(amount: number, currency = 'USD') {
    if (amount < 0) {
      throw new Error('Money amount cannot be negative');
    }
    const cleanCurrency = currency.trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(cleanCurrency)) {
      throw new Error(`Invalid ISO-4217 currency code: ${cleanCurrency}`);
    }
    this.amount = Math.round(amount * 100) / 100;
    this.currency = cleanCurrency;
    Object.freeze(this);
  }

  add(other: Money): Money {
    if (this.currency !== other.currency) {
      throw new Error(`Currency mismatch: ${this.currency} vs ${other.currency}`);
    }
    return new Money(this.amount + other.amount, this.currency);
  }

  subtract(other: Money): Money {
    if (this.currency !== other.currency) {
      throw new Error(`Currency mismatch: ${this.currency} vs ${other.currency}`);
    }
    if (this.amount < other.amount) {
      throw new Error('Insufficient funds for subtraction');
    }
    return new Money(this.amount - other.amount, this.currency);
  }
}

export class Address {
  readonly street: string;
  readonly city: string;
  readonly postalCode: string;
  readonly country: string;

  constructor(street: string, city: string, postalCode: string, country = 'CN') {
    if (!street || !city || !postalCode) {
      throw new Error('Address fields street, city, postalCode cannot be empty');
    }
    this.street = street.trim();
    this.city = city.trim();
    this.postalCode = postalCode.trim();
    this.country = country.trim();
    Object.freeze(this);
  }
}
"""

    # 2. Domain Events
    files["src/domain/events.ts"] = """/**
 * Strongly typed Domain Event Envelope.
 */

export interface DomainEvent {
  readonly eventId: string;
  readonly aggregateType: string;
  readonly aggregateId: string;
  readonly eventType: string;
  readonly occurredAt: string;
  readonly payload: Record<string, any>;
  readonly tenantId: string;
}

export function createDomainEvent(
  aggregateType: string,
  aggregateId: string,
  eventType: string,
  payload: Record<string, any>,
  tenantId = 'default',
): DomainEvent {
  return {
    eventId: `evt-${Math.random().toString(36).substring(2, 14)}`,
    aggregateType,
    aggregateId,
    eventType,
    occurredAt: new Date().toISOString(),
    payload,
    tenantId,
  };
}
"""

    # 3. Domain Aggregate Root
    files["src/domain/aggregate.ts"] = f"""import {{ Money, Address }} from './value-objects';
import {{ DomainEvent, createDomainEvent }} from './events';

export class {entity_name}Item {{
  readonly itemId: string;
  readonly name: string;
  readonly unitPrice: number;
  readonly quantity: number;

  constructor(itemId: string, name: string, unitPrice: number, quantity: number) {{
    if (unitPrice <= 0 || quantity <= 0) {{
      throw new Error('Item unitPrice and quantity must be positive');
    }}
    this.itemId = itemId;
    this.name = name;
    this.unitPrice = unitPrice;
    this.quantity = quantity;
    Object.freeze(this);
  }}

  get subtotal(): number {{
    return this.unitPrice * this.quantity;
  }}
}}

export class {entity_name}Aggregate {{
  readonly id: string;
  readonly tenantId: string;
  status: string; // DRAFT, SUBMITTED, APPROVED, FULFILLED, CANCELLED
  items: {entity_name}Item[] = [];
  totalAmount: Money;
  version: number;
  private uncommittedEvents: DomainEvent[] = [];

  constructor(id: string, tenantId = 'default') {{
    this.id = id;
    this.tenantId = tenantId;
    this.status = 'DRAFT';
    this.totalAmount = new Money(0, 'USD');
    this.version = 1;
  }}

  addItem(name: string, unitPrice: number, quantity: number): void {{
    if (this.status !== 'DRAFT') {{
      throw new Error(`Cannot add items in status ${{this.status}}`);
    }}
    const itemId = `itm-${{Math.random().toString(36).substring(2, 10)}}`;
    const item = new {entity_name}Item(itemId, name, unitPrice, quantity);
    this.items.push(item);
    this.recalculateTotal();
  }}

  submit(): void {{
    if (this.items.length === 0) {{
      throw new Error('Cannot submit aggregate without items');
    }}
    if (this.totalAmount.amount <= 0) {{
      throw new Error('Total amount must be greater than zero');
    }}

    const oldStatus = this.status;
    this.status = 'SUBMITTED';
    this.version++;
    this.uncommittedEvents.push(
      createDomainEvent('{entity_name}', this.id, '{entity_name}Submitted', {{
        oldStatus,
        newStatus: this.status,
      }}, this.tenantId),
    );
  }}

  cancel(reason = 'User requested cancellation'): void {{
    if (this.status === 'FULFILLED' || this.status === 'CANCELLED') {{
      throw new Error(`Cannot cancel aggregate in status ${{this.status}}`);
    }}

    this.status = 'CANCELLED';
    this.version++;
    this.uncommittedEvents.push(
      createDomainEvent('{entity_name}', this.id, '{entity_name}Cancelled', {{ reason }}, this.tenantId),
    );
  }}

  private recalculateTotal(): void {{
    const sum = this.items.reduce((acc, itm) => acc + itm.subtotal, 0);
    this.totalAmount = new Money(sum, this.totalAmount.currency);
  }}

  pollEvents(): DomainEvent[] {{
    const events = [...this.uncommittedEvents];
    this.uncommittedEvents = [];
    return events;
  }}
}}
"""

    # 4. Workflow State Machine Service
    files["src/workflow/fsm.service.ts"] = f"""import {{ Injectable }} from '@nestjs/common';

export interface StateTransitionLog {{
  transitionId: string;
  aggregateId: string;
  fromState: string;
  toState: string;
  event: string;
  version: number;
  timestamp: string;
}}

@Injectable()
export class {entity_name}StateMachineService {{
  private readonly transitions = new Map<string, string>([
    ['DRAFT:submit', 'SUBMITTED'],
    ['SUBMITTED:approve', 'APPROVED'],
    ['SUBMITTED:reject', 'REJECTED'],
    ['APPROVED:fulfill', 'FULFILLED'],
    ['DRAFT:cancel', 'CANCELLED'],
    ['SUBMITTED:cancel', 'CANCELLED'],
    ['APPROVED:cancel', 'CANCELLED'],
  ]);

  private logs: StateTransitionLog[] = [];

  canTransition(currentState: string, event: string): boolean {{
    return this.transitions.has(`${{currentState}}:${{event}}`);
  }}

  executeTransition(
    aggregateId: string,
    currentState: string,
    event: string,
    currentVersion: number,
  ): {{ newState: string; newVersion: number; log: StateTransitionLog }} {{
    const key = `${{currentState}}:${{event}}`;
    const toState = this.transitions.get(key);
    if (!toState) {{
      throw new Error(`Invalid transition from ${{currentState}} on event ${{event}}`);
    }}

    const newVersion = currentVersion + 1;
    const log: StateTransitionLog = {{
      transitionId: `trn-${{this.logs.length + 1}}`,
      aggregateId,
      fromState: currentState,
      toState,
      event,
      version: newVersion,
      timestamp: new Date().toISOString(),
    }};
    this.logs.push(log);
    return {{ newState: toState, newVersion, log }};
  }}

  getAuditLogs(): StateTransitionLog[] {{
    return [...this.logs];
  }}
}}
"""

    # 5. Distributed Transactions: Saga Coordinator
    files["src/transactions/saga.service.ts"] = f"""import {{ Injectable, Logger }} from '@nestjs/common';

export interface SagaStepDef {{
  name: string;
  action: (ctx: Record<string, any>) => Promise<Record<string, any>> | Record<string, any>;
  compensation: (ctx: Record<string, any>) => Promise<void> | void;
}}

@Injectable()
export class {entity_name}SagaService {{
  private readonly logger = new Logger('{entity_name}SagaService');

  async execute(steps: SagaStepDef[], initialContext: Record<string, any>): Promise<{{ success: boolean; message: string; context: Record<string, any> }}> {{
    const context = {{ ...initialContext }};
    const completedSteps: SagaStepDef[] = [];

    for (const step of steps) {{
      try {{
        const out = await step.action(context);
        Object.assign(context, out);
        completedSteps.push(step);
      }} catch (err: any) {{
        this.logger.error(`Saga step ${{step.name}} failed: ${{err.message}}. Starting LIFO compensation.`);
        await this.rollback(completedSteps, context);
        return {{ success: false, message: `Step ${{step.name}} failed: ${{err.message}}`, context }};
      }}
    }}

    return {{ success: true, message: 'Saga completed successfully', context }};
  }}

  private async rollback(completedSteps: SagaStepDef[], context: Record<string, any>): Promise<void> {{
    for (let i = completedSteps.length - 1; i >= 0; i--) {{
      const step = completedSteps[i];
      try {{
        await step.compensation(context);
      }} catch (err: any) {{
        this.logger.error(`Compensation error in ${{step.name}}: ${{err.message}}`);
      }}
    }}
  }}
}}
"""

    # 6. Transactional Outbox
    files["src/transactions/outbox.service.ts"] = """import { Injectable } from '@nestjs/common';

export interface OutboxRecord {
  eventId: string;
  tenantId: string;
  eventType: string;
  payload: Record<string, any>;
  status: 'PENDING' | 'IN_FLIGHT' | 'PUBLISHED' | 'FAILED';
  retryCount: number;
}

@Injectable()
export class OutboxDispatcherService {
  private records = new Map<string, OutboxRecord>();

  enqueue(record: OutboxRecord): void {
    this.records.set(record.eventId, record);
  }

  async dispatchPending(publisher: (rec: OutboxRecord) => Promise<boolean>): Promise<number> {
    let published = 0;
    for (const rec of this.records.values()) {
      if (rec.status === 'PENDING') {
        rec.status = 'IN_FLIGHT';
        try {
          const ok = await publisher(rec);
          if (ok) {
            rec.status = 'PUBLISHED';
            published++;
          } else {
            rec.status = 'FAILED';
            rec.retryCount++;
          }
        } catch {
          rec.status = 'FAILED';
          rec.retryCount++;
        }
      }
    }
    return published;
  }
}
"""

    # 7. Distributed Lock with Fencing
    files["src/transactions/lock.service.ts"] = """import { Injectable } from '@nestjs/common';

interface LockEntry {
  owner: string;
  expiresAt: number;
  token: number;
}

@Injectable()
export class DistributedLockService {
  private locks = new Map<string, LockEntry>();
  private generators = new Map<string, number>();

  acquire(resourceKey: string, owner: string, ttlMs = 30000): number {
    const now = Date.now();
    const existing = this.locks.get(resourceKey);
    if (existing && existing.expiresAt > now && existing.owner !== owner) {
      throw new Error(`Resource ${resourceKey} already locked`);
    }

    const token = (this.generators.get(resourceKey) || 0) + 1;
    this.generators.set(resourceKey, token);
    this.locks.set(resourceKey, { owner, expiresAt: now + ttlMs, token });
    return token;
  }

  release(resourceKey: string, owner: string): void {
    const existing = this.locks.get(resourceKey);
    if (existing && existing.owner === owner) {
      this.locks.delete(resourceKey);
    }
  }
}
"""

    return files
