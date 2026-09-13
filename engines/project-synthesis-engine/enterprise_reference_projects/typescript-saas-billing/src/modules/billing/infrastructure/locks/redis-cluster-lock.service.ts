export interface LockHandle {
  resourceKey: string;
  token: string;
  fencingToken: number;
  expiresAt: Date;
  stopHeartbeat(): void;
}

export class DistributedLockService {
  private activeLocks = new Map<string, { token: string; fencingToken: number; expiresAt: Date }>();
  private monotonicSequence = 0;

  async acquireLock(resourceKey: string, ttlMs = 10000): Promise<LockHandle> {
    const now = new Date();
    const existing = this.activeLocks.get(resourceKey);

    if (existing && existing.expiresAt > now) {
      throw new Error(`Lock on resource ${resourceKey} is currently held by another process`);
    }

    this.monotonicSequence += 1;
    const fencingToken = this.monotonicSequence;
    const token = `tok_${fencingToken}_${Date.now()}`;
    const expiresAt = new Date(Date.now() + ttlMs);

    this.activeLocks.set(resourceKey, { token, fencingToken, expiresAt });

    // Background renewal timer
    let heartbeatTimer: NodeJS.Timeout | null = null;
    const renewalInterval = Math.max(100, Math.floor(ttlMs / 3));

    heartbeatTimer = setInterval(() => {
      const cur = this.activeLocks.get(resourceKey);
      if (cur && cur.token === token) {
        cur.expiresAt = new Date(Date.now() + ttlMs);
      } else {
        if (heartbeatTimer) clearInterval(heartbeatTimer);
      }
    }, renewalInterval);

    return {
      resourceKey,
      token,
      fencingToken,
      expiresAt,
      stopHeartbeat: () => {
        if (heartbeatTimer) {
          clearInterval(heartbeatTimer);
          heartbeatTimer = null;
        }
      },
    };
  }

  async releaseLock(handle: LockHandle): Promise<boolean> {
    handle.stopHeartbeat();
    const cur = this.activeLocks.get(handle.resourceKey);
    if (cur && cur.token === handle.token) {
      this.activeLocks.delete(handle.resourceKey);
      return true;
    }
    return false;
  }
}
