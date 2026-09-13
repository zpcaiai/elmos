import * as crypto from 'crypto';

export interface CacheEntry<T> {
  value: T;
  computedDurationMs: number; // delta: time it took to compute the value
  expiresAtMs: number;        // expiry timestamp
}

export class XFetchCacheService {
  private cache = new Map<string, CacheEntry<unknown>>();
  private beta: number;

  constructor(beta = 1.0) {
    this.beta = beta;
  }

  /**
   * Evaluates XFetch probabilistic early expiration condition:
   * Condition to refresh early: now - (delta * beta * ln(rand())) > expiresAt
   */
  shouldRecomputeEarly(entry: CacheEntry<unknown>): boolean {
    const now = Date.now();
    if (now >= entry.expiresAtMs) {
      return true; // Already expired
    }

    // Generate uniform random float in (0, 1]
    const rand = Math.max(1e-10, Math.random());
    // -beta * delta * ln(rand)
    const earlyWindow = -(this.beta * entry.computedDurationMs * Math.log(rand));

    return now + earlyWindow >= entry.expiresAtMs;
  }

  async getOrCompute<T>(
    key: string,
    ttlMs: number,
    computeFn: () => Promise<T>
  ): Promise<T> {
    const entry = this.cache.get(key) as CacheEntry<T> | undefined;

    if (entry && !this.shouldRecomputeEarly(entry)) {
      return entry.value;
    }

    const start = Date.now();
    const value = await computeFn();
    const duration = Date.now() - start;

    this.cache.set(key, {
      value,
      computedDurationMs: Math.max(1, duration),
      expiresAtMs: Date.now() + ttlMs,
    });

    return value;
  }

  invalidate(key: string): void {
    this.cache.delete(key);
  }

  size(): number {
    return this.cache.size;
  }
}
