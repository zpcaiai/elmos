export class IngestMeterEventDto {
  customerId!: string;
  subscriptionId!: string;
  metricKey!: string;
  value!: number;
  uniqueProperty?: string;
  idempotencyKey!: string;
}

export class QueryUsageDto {
  customerId!: string;
  metricKey!: string;
  from?: string; // ISO date string
  to?: string;   // ISO date string
}
