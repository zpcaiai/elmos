export enum AggregationType {
  SUM = 'SUM',
  MAX = 'MAX',
  LAST = 'LAST',
  UNIQUE_COUNT = 'UNIQUE_COUNT',
}

export interface MeterEvent {
  eventId: string;
  tenantId: string;
  customerId: string;
  subscriptionId: string;
  metricKey: string;
  value: number;
  uniqueProperty?: string;
  timestamp: Date;
  idempotencyKey: string;
  metadata?: Record<string, unknown>;
}

export interface AggregationWindow {
  windowStart: Date;
  windowEnd: Date;
  metricKey: string;
  aggregationType: AggregationType;
  aggregatedValue: number;
  sampleCount: number;
}

export class UsageRecordAggregate {
  tenantId: string;
  customerId: string;
  metricKey: string;
  aggregationType: AggregationType;
  events: MeterEvent[];
  seenIdempotencyKeys: Set<string>;
  uniqueIdentifiers: Set<string>;
  sumTotal: number;
  maxValue: number;
  lastValue: number;
  lastEventTimestamp?: Date;

  constructor(params: {
    tenantId: string;
    customerId: string;
    metricKey: string;
    aggregationType: AggregationType;
  }) {
    this.tenantId = params.tenantId;
    this.customerId = params.customerId;
    this.metricKey = params.metricKey;
    this.aggregationType = params.aggregationType;
    this.events = [];
    this.seenIdempotencyKeys = new Set<string>();
    this.uniqueIdentifiers = new Set<string>();
    this.sumTotal = 0;
    this.maxValue = Number.NEGATIVE_INFINITY;
    this.lastValue = 0;
  }

  recordEvent(event: MeterEvent): boolean {
    if (this.seenIdempotencyKeys.has(event.idempotencyKey)) {
      return false; // Duplicate event discarded
    }

    this.seenIdempotencyKeys.add(event.idempotencyKey);
    this.events.push(event);

    this.sumTotal += event.value;
    if (event.value > this.maxValue) {
      this.maxValue = event.value;
    }
    if (!this.lastEventTimestamp || event.timestamp >= this.lastEventTimestamp) {
      this.lastValue = event.value;
      this.lastEventTimestamp = event.timestamp;
    }
    if (event.uniqueProperty) {
      this.uniqueIdentifiers.add(event.uniqueProperty);
    }

    return true;
  }

  getAggregatedValue(): number {
    switch (this.aggregationType) {
      case AggregationType.SUM:
        return this.sumTotal;
      case AggregationType.MAX:
        return this.maxValue === Number.NEGATIVE_INFINITY ? 0 : this.maxValue;
      case AggregationType.LAST:
        return this.lastValue;
      case AggregationType.UNIQUE_COUNT:
        return this.uniqueIdentifiers.size;
      default:
        return this.sumTotal;
    }
  }

  getAggregatedValueForWindow(start: Date, end: Date): number {
    const windowEvents = this.events.filter(
      (e) => e.timestamp >= start && e.timestamp < end
    );

    if (windowEvents.length === 0) {
      return 0;
    }

    switch (this.aggregationType) {
      case AggregationType.SUM:
        return windowEvents.reduce((acc, curr) => acc + curr.value, 0);
      case AggregationType.MAX:
        return Math.max(...windowEvents.map((e) => e.value));
      case AggregationType.LAST: {
        windowEvents.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
        return windowEvents[0].value;
      }
      case AggregationType.UNIQUE_COUNT: {
        const uniqueSet = new Set<string>();
        for (const e of windowEvents) {
          if (e.uniqueProperty) {
            uniqueSet.add(e.uniqueProperty);
          }
        }
        return uniqueSet.size;
      }
    }
  }
}
