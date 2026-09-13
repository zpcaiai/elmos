import { UsageAggregatorService } from '../src/modules/billing/domain/services/usage-aggregator.service';
import { AggregationType, MeterEvent } from '../src/modules/billing/domain/entities/usage-record.entity';

describe('UsageAggregatorService', () => {
  let service: UsageAggregatorService;

  beforeEach(() => {
    service = new UsageAggregatorService();
  });

  it('should sum values and reject duplicate idempotency keys', () => {
    const tenantId = 't_1';
    const customerId = 'c_1';
    const metricKey = 'api_calls';

    service.getOrCreateRecord(tenantId, customerId, metricKey, AggregationType.SUM);

    const event1: MeterEvent = {
      eventId: 'e_1',
      tenantId,
      customerId,
      subscriptionId: 's_1',
      metricKey,
      value: 100,
      timestamp: new Date(),
      idempotencyKey: 'idem_key_001',
    };

    const event2: MeterEvent = {
      eventId: 'e_2',
      tenantId,
      customerId,
      subscriptionId: 's_1',
      metricKey,
      value: 50,
      timestamp: new Date(),
      idempotencyKey: 'idem_key_002',
    };

    const duplicateEvent: MeterEvent = {
      eventId: 'e_3',
      tenantId,
      customerId,
      subscriptionId: 's_1',
      metricKey,
      value: 100,
      timestamp: new Date(),
      idempotencyKey: 'idem_key_001', // Duplicate key!
    };

    expect(service.ingestEvent(event1)).toBe(true);
    expect(service.ingestEvent(event2)).toBe(true);
    expect(service.ingestEvent(duplicateEvent)).toBe(false); // Discarded!

    const total = service.getAggregatedUsage(tenantId, customerId, metricKey);
    expect(total).toBe(150); // 100 + 50
  });

  it('should calculate unique count correctly', () => {
    const tenantId = 't_1';
    const customerId = 'c_1';
    const metricKey = 'active_devices';

    service.getOrCreateRecord(tenantId, customerId, metricKey, AggregationType.UNIQUE_COUNT);

    const events: MeterEvent[] = [
      {
        eventId: 'e_1',
        tenantId,
        customerId,
        subscriptionId: 's_1',
        metricKey,
        value: 1,
        uniqueProperty: 'device_iphone_12',
        timestamp: new Date(),
        idempotencyKey: 'k_1',
      },
      {
        eventId: 'e_2',
        tenantId,
        customerId,
        subscriptionId: 's_1',
        metricKey,
        value: 1,
        uniqueProperty: 'device_macbook_pro',
        timestamp: new Date(),
        idempotencyKey: 'k_2',
      },
      {
        eventId: 'e_3',
        tenantId,
        customerId,
        subscriptionId: 's_1',
        metricKey,
        value: 1,
        uniqueProperty: 'device_iphone_12', // Re-encountered device
        timestamp: new Date(),
        idempotencyKey: 'k_3',
      },
    ];

    service.ingestBatch(events);
    const uniqueCount = service.getAggregatedUsage(tenantId, customerId, metricKey);
    expect(uniqueCount).toBe(2);
  });
});
