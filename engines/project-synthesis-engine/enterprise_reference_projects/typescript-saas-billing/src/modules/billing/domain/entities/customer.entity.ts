export interface Address {
  line1: string;
  line2?: string;
  city: string;
  state: string;
  postalCode: string;
  country: string; // ISO 3166-1 alpha-2
}

export interface PaymentMethodRecord {
  methodId: string;
  type: 'CARD' | 'ACH' | 'SEPA' | 'BANK_TRANSFER';
  last4: string;
  brand?: string;
  expiryMonth?: number;
  expiryYear?: number;
  isDefault: boolean;
  gatewayToken: string;
  createdAt: Date;
}

export class CustomerAggregate {
  customerId: string;
  tenantId: string;
  email: string;
  name: string;
  currency: string;
  billingAddress?: Address;
  taxId?: string;
  taxExempt: boolean;
  creditBalanceCents: number; // Customer balance available to offset future invoices
  defaultPaymentMethodId?: string;
  paymentMethods: PaymentMethodRecord[];
  delinquencyCounter: number;
  metadata: Record<string, unknown>;
  createdAt: Date;
  updatedAt: Date;

  constructor(params: {
    customerId: string;
    tenantId: string;
    email: string;
    name: string;
    currency?: string;
    billingAddress?: Address;
    taxId?: string;
    taxExempt?: boolean;
    creditBalanceCents?: number;
  }) {
    const now = new Date();
    this.customerId = params.customerId;
    this.tenantId = params.tenantId;
    this.email = params.email;
    this.name = params.name;
    this.currency = (params.currency || 'USD').toUpperCase();
    this.billingAddress = params.billingAddress;
    this.taxId = params.taxId;
    this.taxExempt = params.taxExempt ?? false;
    this.creditBalanceCents = params.creditBalanceCents ?? 0;
    this.paymentMethods = [];
    this.delinquencyCounter = 0;
    this.metadata = {};
    this.createdAt = now;
    this.updatedAt = now;
  }

  addPaymentMethod(method: Omit<PaymentMethodRecord, 'createdAt'>): void {
    const record: PaymentMethodRecord = {
      ...method,
      createdAt: new Date(),
    };

    if (method.isDefault || this.paymentMethods.length === 0) {
      this.paymentMethods.forEach((m) => (m.isDefault = false));
      record.isDefault = true;
      this.defaultPaymentMethodId = record.methodId;
    }

    this.paymentMethods.push(record);
    this.updatedAt = new Date();
  }

  removePaymentMethod(methodId: string): void {
    this.paymentMethods = this.paymentMethods.filter((m) => m.methodId !== methodId);
    if (this.defaultPaymentMethodId === methodId) {
      this.defaultPaymentMethodId = this.paymentMethods[0]?.methodId;
      if (this.paymentMethods[0]) {
        this.paymentMethods[0].isDefault = true;
      }
    }
    this.updatedAt = new Date();
  }

  applyCredit(cents: number): void {
    if (cents <= 0) {
      throw new Error('Credit amount must be strictly positive');
    }
    this.creditBalanceCents += cents;
    this.updatedAt = new Date();
  }

  deductCredit(cents: number): number {
    if (cents <= 0) {
      throw new Error('Deduction amount must be strictly positive');
    }
    const applied = Math.min(this.creditBalanceCents, cents);
    this.creditBalanceCents -= applied;
    this.updatedAt = new Date();
    return applied;
  }

  recordPaymentFailure(): number {
    this.delinquencyCounter += 1;
    this.updatedAt = new Date();
    return this.delinquencyCounter;
  }

  resetDelinquency(): void {
    this.delinquencyCounter = 0;
    this.updatedAt = new Date();
  }
}
