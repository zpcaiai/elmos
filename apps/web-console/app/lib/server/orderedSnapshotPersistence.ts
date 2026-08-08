export type AtomicSnapshotWriter = (
  destination: string,
  snapshot: unknown,
) => Promise<void>;

/**
 * Serializes immutable snapshots per destination while allowing unrelated jobs
 * to persist concurrently. A later terminal state therefore cannot be
 * overwritten by an older, slower write that completed out of order.
 */
export class OrderedSnapshotPersistence {
  private readonly pending = new Map<string, Promise<void>>();
  private readonly writeSnapshot: AtomicSnapshotWriter;

  constructor(writeSnapshot: AtomicSnapshotWriter) {
    this.writeSnapshot = writeSnapshot;
  }

  async persist(destination: string, value: unknown): Promise<void> {
    const snapshot = structuredClone(value);
    const previous = this.pending.get(destination) ?? Promise.resolve();
    const current = previous
      .catch(() => undefined)
      .then(() => this.writeSnapshot(destination, snapshot));
    this.pending.set(destination, current);
    try {
      await current;
    } finally {
      if (this.pending.get(destination) === current) {
        this.pending.delete(destination);
      }
    }
  }
}
