export class RetryDispatcherError extends Error {
  readonly code: "RETRY_DISPATCHER_CAPACITY_REACHED" | "RETRY_DISPATCHER_CLOSED";

  constructor(code: RetryDispatcherError["code"]) {
    super(code);
    this.code = code;
  }
}

type RetryTask = () => void | Promise<void>;
type TimerToken = unknown;

export type RetryDispatcherOptions = {
  capacity: number;
  maxConcurrent: number;
  maxDispatchPerTurn: number;
  now?: () => number;
  setTimer?: (callback: () => void, delayMs: number) => TimerToken;
  clearTimer?: (timer: TimerToken) => void;
  onTaskError?: (error: unknown, key: string) => void;
};

type PendingRetry = {
  key: string;
  dueAt: number;
  sequence: number;
  task: RetryTask;
};

export type RetryDispatcherSnapshot = {
  pending: number;
  running: number;
  timerArmed: boolean;
  capacity: number;
  maxConcurrent: number;
};

/**
 * A process-wide, bounded retry queue.  Pending work is deduplicated by key
 * and a single timer is always armed for the earliest due item.
 */
export class BoundedRetryDispatcher {
  readonly #capacity: number;
  readonly #maxConcurrent: number;
  readonly #maxDispatchPerTurn: number;
  readonly #now: () => number;
  readonly #setTimer: (callback: () => void, delayMs: number) => TimerToken;
  readonly #clearTimer: (timer: TimerToken) => void;
  readonly #onTaskError: (error: unknown, key: string) => void;
  readonly #pending = new Map<string, PendingRetry>();
  readonly #runningKeys = new Set<string>();
  #timer: TimerToken | undefined;
  #sequence = 0;
  #closed = false;

  constructor(options: RetryDispatcherOptions) {
    if (
      !Number.isSafeInteger(options.capacity)
      || options.capacity < 1
      || options.capacity > 100_000
      || !Number.isSafeInteger(options.maxConcurrent)
      || options.maxConcurrent < 1
      || options.maxConcurrent > options.capacity
      || !Number.isSafeInteger(options.maxDispatchPerTurn)
      || options.maxDispatchPerTurn < 1
      || options.maxDispatchPerTurn > options.capacity
    ) throw new Error("RETRY_DISPATCHER_CONFIGURATION_INVALID");
    this.#capacity = options.capacity;
    this.#maxConcurrent = options.maxConcurrent;
    this.#maxDispatchPerTurn = options.maxDispatchPerTurn;
    this.#now = options.now ?? Date.now;
    this.#setTimer = options.setTimer ?? ((callback, delayMs) => {
      const timer = setTimeout(callback, delayMs);
      timer.unref();
      return timer;
    });
    this.#clearTimer = options.clearTimer ?? ((timer) => clearTimeout(timer as NodeJS.Timeout));
    this.#onTaskError = options.onTaskError ?? ((error, key) => {
      console.error(`Retry dispatcher task failed for ${key}.`, error);
    });
  }

  schedule(key: string, delayMs: number, task: RetryTask): void {
    if (this.#closed) throw new RetryDispatcherError("RETRY_DISPATCHER_CLOSED");
    if (
      key.length < 1
      || key.length > 512
      || /[\0\r\n]/.test(key)
      || !Number.isFinite(delayMs)
      || delayMs < 0
      || delayMs > 24 * 60 * 60_000
    ) throw new Error("RETRY_DISPATCHER_ITEM_INVALID");
    if (!this.#pending.has(key) && this.#pending.size >= this.#capacity) {
      throw new RetryDispatcherError("RETRY_DISPATCHER_CAPACITY_REACHED");
    }
    this.#pending.set(key, {
      key,
      dueAt: this.#now() + Math.floor(delayMs),
      sequence: this.#sequence += 1,
      task,
    });
    this.#rearm();
  }

  cancel(key: string): boolean {
    const removed = this.#pending.delete(key);
    if (removed) this.#rearm();
    return removed;
  }

  close(): void {
    this.#closed = true;
    this.#pending.clear();
    if (this.#timer !== undefined) this.#clearTimer(this.#timer);
    this.#timer = undefined;
  }

  snapshot(): RetryDispatcherSnapshot {
    return {
      pending: this.#pending.size,
      running: this.#runningKeys.size,
      timerArmed: this.#timer !== undefined,
      capacity: this.#capacity,
      maxConcurrent: this.#maxConcurrent,
    };
  }

  #earliestDue(): PendingRetry | undefined {
    let earliest: PendingRetry | undefined;
    for (const item of this.#pending.values()) {
      if (this.#runningKeys.has(item.key)) continue;
      if (
        !earliest
        || item.dueAt < earliest.dueAt
        || (item.dueAt === earliest.dueAt && item.sequence < earliest.sequence)
      ) earliest = item;
    }
    return earliest;
  }

  #rearm(): void {
    if (this.#timer !== undefined) {
      this.#clearTimer(this.#timer);
      this.#timer = undefined;
    }
    if (this.#closed || this.#runningKeys.size >= this.#maxConcurrent) return;
    const earliest = this.#earliestDue();
    if (!earliest) return;
    const delay = Math.max(0, Math.min(2_147_483_647, earliest.dueAt - this.#now()));
    this.#timer = this.#setTimer(() => {
      this.#timer = undefined;
      this.#drain();
    }, delay);
  }

  #drain(): void {
    if (this.#closed) return;
    let dispatched = 0;
    while (
      this.#runningKeys.size < this.#maxConcurrent
      && dispatched < this.#maxDispatchPerTurn
    ) {
      const next = this.#earliestDue();
      if (!next || next.dueAt > this.#now()) break;
      this.#pending.delete(next.key);
      this.#runningKeys.add(next.key);
      dispatched += 1;
      void Promise.resolve()
        .then(next.task)
        .catch((error: unknown) => this.#onTaskError(error, next.key))
        .finally(() => {
          this.#runningKeys.delete(next.key);
          this.#rearm();
        });
    }
    this.#rearm();
  }
}

const globalDispatcherState = globalThis as typeof globalThis & {
  __elmosLocalQueueRetryDispatcher?: BoundedRetryDispatcher;
};

export const localQueueRetryDispatcher = globalDispatcherState.__elmosLocalQueueRetryDispatcher ??=
  new BoundedRetryDispatcher({
    capacity: 4_096,
    maxConcurrent: 8,
    maxDispatchPerTurn: 32,
  });
