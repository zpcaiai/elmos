export enum InvoiceStatus {
  DRAFT = 'DRAFT',
  OPEN = 'OPEN',
  PAID = 'PAID',
  UNCOLLECTIBLE = 'UNCOLLECTIBLE',
  VOID = 'VOID',
}

export enum LineItemType {
  SUBSCRIPTION_BASE = 'SUBSCRIPTION_BASE',
  SEAT_OVERAGE = 'SEAT_OVERAGE',
  USAGE_METERED = 'USAGE_METERED',
  PRORATION_CREDIT = 'PRORATION_CREDIT',
  ONE_TIME_CHARGE = 'ONE_TIME_CHARGE',
  DISCOUNT = 'DISCOUNT',
  TAX = 'TAX',
}

export interface InvoiceLineItem {
  lineId: string;
  type: LineItemType;
  description: string;
  quantity: number;
  unitPriceCents: number;
  subtotalCents: number;
  discountCents: number;
  taxCents: number;
  totalCents: number;
  periodStart?: Date;
  periodEnd?: Date;
  metadata?: Record<string, unknown>;
}

export interface PaymentAttempt {
  attemptId: string;
  timestamp: Date;
  amountCents: number;
  paymentMethodId: string;
  status: 'SUCCESS' | 'FAILED' | 'PENDING';
  gatewayTransactionId?: string;
  failureCode?: string;
  failureMessage?: string;
}

export class InvoiceAggregate {
  invoiceId: string;
  tenantId: string;
  customerId: string;
  subscriptionId?: string;
  invoiceNumber: string;
  status: InvoiceStatus;
  currency: string;
  lineItems: InvoiceLineItem[];
  subtotalCents: number;
  discountTotalCents: number;
  taxTotalCents: number;
  totalCents: number;
  amountPaidCents: number;
  amountRemainingCents: number;
  dueDate: Date;
  issuedAt: Date;
  paidAt?: Date;
  voidedAt?: Date;
  paymentAttempts: PaymentAttempt[];
  createdAt: Date;
  updatedAt: Date;

  constructor(params: {
    invoiceId: string;
    tenantId: string;
    customerId: string;
    subscriptionId?: string;
    invoiceNumber: string;
    currency: string;
    dueDate?: Date;
    issuedAt?: Date;
    lineItems?: InvoiceLineItem[];
  }) {
    const now = new Date();
    this.invoiceId = params.invoiceId;
    this.tenantId = params.tenantId;
    this.customerId = params.customerId;
    this.subscriptionId = params.subscriptionId;
    this.invoiceNumber = params.invoiceNumber;
    this.status = InvoiceStatus.DRAFT;
    this.currency = params.currency.toUpperCase();
    this.issuedAt = params.issuedAt ?? now;
    this.dueDate = params.dueDate ?? new Date(now.getTime() + 14 * 86400000); // 14 days net
    this.lineItems = params.lineItems ?? [];
    this.subtotalCents = 0;
    this.discountTotalCents = 0;
    this.taxTotalCents = 0;
    this.totalCents = 0;
    this.amountPaidCents = 0;
    this.amountRemainingCents = 0;
    this.paymentAttempts = [];
    this.createdAt = now;
    this.updatedAt = now;

    this.recalculateTotals();
  }

  addLineItem(item: Omit<InvoiceLineItem, 'subtotalCents' | 'totalCents'>): void {
    if (this.status !== InvoiceStatus.DRAFT) {
      throw new Error(`Cannot add line items to non-draft invoice (${this.status})`);
    }

    const subtotal = item.quantity * item.unitPriceCents;
    const total = Math.max(0, subtotal - item.discountCents + item.taxCents);

    this.lineItems.push({
      ...item,
      subtotalCents: subtotal,
      totalCents: total,
    });

    this.recalculateTotals();
  }

  recalculateTotals(): void {
    let subtotal = 0;
    let discounts = 0;
    let tax = 0;

    for (const line of this.lineItems) {
      subtotal += line.subtotalCents;
      discounts += line.discountCents;
      tax += line.taxCents;
    }

    this.subtotalCents = subtotal;
    this.discountTotalCents = discounts;
    this.taxTotalCents = tax;
    this.totalCents = Math.max(0, subtotal - discounts + tax);
    this.amountRemainingCents = Math.max(0, this.totalCents - this.amountPaidCents);
    this.updatedAt = new Date();
  }

  finalize(): void {
    if (this.status !== InvoiceStatus.DRAFT) {
      throw new Error(`Cannot finalize invoice in status ${this.status}`);
    }
    if (this.lineItems.length === 0) {
      throw new Error('Cannot finalize an empty invoice with no line items');
    }

    this.recalculateTotals();

    // If total is 0, auto-mark paid
    if (this.totalCents === 0) {
      this.status = InvoiceStatus.PAID;
      this.paidAt = new Date();
      this.amountRemainingCents = 0;
    } else {
      this.status = InvoiceStatus.OPEN;
    }
    this.updatedAt = new Date();
  }

  recordPaymentAttempt(attempt: PaymentAttempt): void {
    this.paymentAttempts.push(attempt);
    if (attempt.status === 'SUCCESS') {
      this.amountPaidCents += attempt.amountCents;
      this.amountRemainingCents = Math.max(0, this.totalCents - this.amountPaidCents);
      if (this.amountRemainingCents === 0) {
        this.status = InvoiceStatus.PAID;
        this.paidAt = attempt.timestamp;
      }
    }
    this.updatedAt = new Date();
  }

  markUncollectible(): void {
    if (this.status !== InvoiceStatus.OPEN) {
      throw new Error(`Only open invoices can be marked uncollectible (current: ${this.status})`);
    }
    this.status = InvoiceStatus.UNCOLLECTIBLE;
    this.updatedAt = new Date();
  }

  voidInvoice(): void {
    if (this.status === InvoiceStatus.PAID) {
      throw new Error('Cannot void an invoice that has already been paid');
    }
    this.status = InvoiceStatus.VOID;
    this.voidedAt = new Date();
    this.amountRemainingCents = 0;
    this.updatedAt = new Date();
  }
}
