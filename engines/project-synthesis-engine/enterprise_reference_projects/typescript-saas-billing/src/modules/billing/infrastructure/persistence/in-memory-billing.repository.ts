import { CustomerAggregate } from '../../domain/entities/customer.entity';
import { SubscriptionAggregate, SubscriptionStatus } from '../../domain/entities/subscription.entity';
import { InvoiceAggregate } from '../../domain/entities/invoice.entity';
import {
  CustomerRepository,
  SubscriptionRepository,
  InvoiceRepository,
} from '../../domain/repositories/billing-repository.interface';

export class InMemoryCustomerRepository implements CustomerRepository {
  private customers = new Map<string, CustomerAggregate>();

  private key(tenantId: string, id: string): string {
    return `${tenantId}:${id}`;
  }

  async findById(tenantId: string, customerId: string): Promise<CustomerAggregate | null> {
    return this.customers.get(this.key(tenantId, customerId)) || null;
  }

  async findByEmail(tenantId: string, email: string): Promise<CustomerAggregate | null> {
    for (const c of this.customers.values()) {
      if (c.tenantId === tenantId && c.email.toLowerCase() === email.toLowerCase()) {
        return c;
      }
    }
    return null;
  }

  async save(customer: CustomerAggregate): Promise<void> {
    this.customers.set(this.key(customer.tenantId, customer.customerId), customer);
  }

  async list(tenantId: string, limit = 50, offset = 0): Promise<CustomerAggregate[]> {
    const list: CustomerAggregate[] = [];
    for (const c of this.customers.values()) {
      if (c.tenantId === tenantId) {
        list.push(c);
      }
    }
    return list.slice(offset, offset + limit);
  }
}

export class InMemorySubscriptionRepository implements SubscriptionRepository {
  private subscriptions = new Map<string, SubscriptionAggregate>();

  private key(tenantId: string, id: string): string {
    return `${tenantId}:${id}`;
  }

  async findById(tenantId: string, subscriptionId: string): Promise<SubscriptionAggregate | null> {
    return this.subscriptions.get(this.key(tenantId, subscriptionId)) || null;
  }

  async findByCustomerId(tenantId: string, customerId: string): Promise<SubscriptionAggregate[]> {
    const res: SubscriptionAggregate[] = [];
    for (const s of this.subscriptions.values()) {
      if (s.tenantId === tenantId && s.customerId === customerId) {
        res.push(s);
      }
    }
    return res;
  }

  async findActiveDueForRenewal(tenantId: string, asOf: Date): Promise<SubscriptionAggregate[]> {
    const res: SubscriptionAggregate[] = [];
    for (const s of this.subscriptions.values()) {
      if (
        s.tenantId === tenantId &&
        (s.status === SubscriptionStatus.ACTIVE || s.status === SubscriptionStatus.TRIALING) &&
        s.currentPeriodEnd <= asOf
      ) {
        res.push(s);
      }
    }
    return res;
  }

  async save(subscription: SubscriptionAggregate): Promise<void> {
    this.subscriptions.set(this.key(subscription.tenantId, subscription.subscriptionId), subscription);
  }
}

export class InMemoryInvoiceRepository implements InvoiceRepository {
  private invoices = new Map<string, InvoiceAggregate>();

  private key(tenantId: string, id: string): string {
    return `${tenantId}:${id}`;
  }

  async findById(tenantId: string, invoiceId: string): Promise<InvoiceAggregate | null> {
    return this.invoices.get(this.key(tenantId, invoiceId)) || null;
  }

  async findByCustomerId(tenantId: string, customerId: string): Promise<InvoiceAggregate[]> {
    const res: InvoiceAggregate[] = [];
    for (const inv of this.invoices.values()) {
      if (inv.tenantId === tenantId && inv.customerId === customerId) {
        res.push(inv);
      }
    }
    return res;
  }

  async findByInvoiceNumber(tenantId: string, invoiceNumber: string): Promise<InvoiceAggregate | null> {
    for (const inv of this.invoices.values()) {
      if (inv.tenantId === tenantId && inv.invoiceNumber === invoiceNumber) {
        return inv;
      }
    }
    return null;
  }

  async save(invoice: InvoiceAggregate): Promise<void> {
    this.invoices.set(this.key(invoice.tenantId, invoice.invoiceId), invoice);
  }
}
