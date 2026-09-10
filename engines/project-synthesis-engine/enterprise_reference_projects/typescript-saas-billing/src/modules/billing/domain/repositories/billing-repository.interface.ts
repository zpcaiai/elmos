import { CustomerAggregate } from '../entities/customer.entity';
import { SubscriptionAggregate } from '../entities/subscription.entity';
import { InvoiceAggregate } from '../entities/invoice.entity';

export interface CustomerRepository {
  findById(tenantId: string, customerId: string): Promise<CustomerAggregate | null>;
  findByEmail(tenantId: string, email: string): Promise<CustomerAggregate | null>;
  save(customer: CustomerAggregate): Promise<void>;
  list(tenantId: string, limit?: number, offset?: number): Promise<CustomerAggregate[]>;
}

export interface SubscriptionRepository {
  findById(tenantId: string, subscriptionId: string): Promise<SubscriptionAggregate | null>;
  findByCustomerId(tenantId: string, customerId: string): Promise<SubscriptionAggregate[]>;
  findActiveDueForRenewal(tenantId: string, asOf: Date): Promise<SubscriptionAggregate[]>;
  save(subscription: SubscriptionAggregate): Promise<void>;
}

export interface InvoiceRepository {
  findById(tenantId: string, invoiceId: string): Promise<InvoiceAggregate | null>;
  findByCustomerId(tenantId: string, customerId: string): Promise<InvoiceAggregate[]>;
  findByInvoiceNumber(tenantId: string, invoiceNumber: string): Promise<InvoiceAggregate | null>;
  save(invoice: InvoiceAggregate): Promise<void>;
}
