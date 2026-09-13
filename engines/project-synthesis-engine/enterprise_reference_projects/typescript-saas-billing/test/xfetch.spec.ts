import { XFetchCacheService } from '../src/modules/billing/infrastructure/locks/xfetch-stampede.service';

describe('XFetchCacheService', () => {
  let cache: XFetchCacheService;

  beforeEach(() => {
    cache = new XFetchCacheService(1.5);
  });

  it('should cache computation and serve cached value on subsequent calls', async () => {
    let computeCount = 0;
    const computeFn = async () => {
      computeCount++;
      return { data: 'heavy_aggregation_result' };
    };

    const res1 = await cache.getOrCompute('key_1', 5000, computeFn);
    expect(res1.data).toBe('heavy_aggregation_result');
    expect(computeCount).toBe(1);

    const res2 = await cache.getOrCompute('key_1', 5000, computeFn);
    expect(res2.data).toBe('heavy_aggregation_result');
    expect(computeCount).toBe(1); // Cached! Did not recompute
  });

  it('should invalidate cache upon request', async () => {
    let computeCount = 0;
    const computeFn = async () => {
      computeCount++;
      return { version: computeCount };
    };

    await cache.getOrCompute('key_inv', 5000, computeFn);
    expect(computeCount).toBe(1);

    cache.invalidate('key_inv');

    const res2 = await cache.getOrCompute('key_inv', 5000, computeFn);
    expect(res2.version).toBe(2);
    expect(computeCount).toBe(2);
  });
});
