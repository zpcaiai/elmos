export class GenerateInvoiceDto {
  customerId!: string;
  subscriptionId!: string;
  taxRatePercent?: number;
}

export class RecordPaymentDto {
  amountCents!: number;
  paymentMethodId!: string;
  gatewayTransactionId?: string;
}
