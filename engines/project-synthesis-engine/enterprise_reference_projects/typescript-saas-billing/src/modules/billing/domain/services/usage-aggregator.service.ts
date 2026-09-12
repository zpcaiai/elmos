import { MeterEvent, UsageRecordAggregate, AggregationType } from '../entities/usage-record.entity';

export class UsageAggregatorService {
  private records: Map<string, UsageRecordAggregate> = new Map();

  private makeKey(tenantId: string, customerId: string, metricKey: string): string {
    return `${tenantId}:${customerId}:${metricKey}`;
  }

  getOrCreateRecord(
    tenantId: string,
    customerId: string,
    metricKey: string,
    aggregationType: AggregationType = AggregationType.SUM
  ): UsageRecordAggregate {
    const key = this.makeKey(tenantId, customerId, metricKey);
    let record = this.records.get(key);
    if (!record) {
      record = new UsageRecordAggregate({
        tenantId,
        customerId,
        metricKey,
        aggregationType,
      });
      this.records.set(key, record);
    }
    return record;
  }

  ingestEvent(event: MeterEvent): boolean {
    const record = this.getOrCreateRecord(event.tenantId, event.customerId, event.metricKey);
    return record.recordEvent(event);
  }

  ingestBatch(events: MeterEvent[]): { ingestedCount: number; duplicateCount: number } {
    let ingestedCount = 0;
    let duplicateCount = 0;

    for (const event of events) {
      const success = this.ingestEvent(event);
      if (success) {
        ingestedCount++;
      } else {
        duplicateCount++;
      }
    }

    return { ingestedCount, duplicateCount };
  }

  getAggregatedUsage(
    tenantId: string,
    customerId: string,
    metricKey: string,
    periodStart?: Date,
    periodEnd?: Date
  ): number {
    const key = this.makeKey(tenantId, customerId, metricKey);
    const record = this.records.get(key);
    if (!record) {
      return 0;
    }

    if (periodStart && periodEnd) {
      return record.getAggregatedValueForWindow(periodStart, periodEnd);
    }

    return record.getAggregatedValue();
  }
}
