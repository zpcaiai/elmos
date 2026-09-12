/**
 * WeChat MiniProgram Dual-Thread Runtime Bridge & Dirty Diff Patch Scheduler.
 * 
 * Manages dual-thread lifecycle synchronization (Worker/Logic <=> View/Render)
 * and implements microtask-debounced, path-based dirty diff patching
 * to minimize serialization overhead and prevent WeChat 1024KB payload warnings.
 */

export interface MiniAppInstanceBridge {
  data: Record<string, unknown>;
  setData(patch: Record<string, unknown>, callback?: () => void): void;
  triggerEvent?(name: string, detail?: unknown, options?: unknown): void;
  [key: string]: unknown;
}

export interface DirtyDiffPatch {
  path: string;
  value: unknown;
}

export interface PatchSchedulerStats {
  totalFlushes: number;
  totalKeysPatched: number;
  totalBytesSent: number;
  warningsOver1MB: number;
}

export class WeChatRuntimeBridge {
  private instance: MiniAppInstanceBridge;
  private previousState: Record<string, unknown> = {};
  private pendingChanges: Record<string, unknown> = {};
  private isFlushScheduled = false;
  private callbacks: (() => void)[] = [];
  private stats: PatchSchedulerStats = {
    totalFlushes: 0,
    totalKeysPatched: 0,
    totalBytesSent: 0,
    warningsOver1MB: 0,
  };

  constructor(instance: MiniAppInstanceBridge) {
    this.instance = instance;
    this.previousState = this.deepClone(instance.data || {});
  }

  /**
   * Schedules state updates with automatic microtask batching and path-based dirty diffing.
   */
  public enqueueUpdate(partialState: Record<string, unknown>, callback?: () => void): void {
    if (callback) {
      this.callbacks.push(callback);
    }

    // Merge into pending changes
    for (const [key, val] of Object.entries(partialState)) {
      this.pendingChanges[key] = val;
    }

    if (!this.isFlushScheduled) {
      this.isFlushScheduled = true;
      // Schedule batch flush in next microtask
      if (typeof queueMicrotask === "function") {
        queueMicrotask(() => this.flush());
      } else {
        Promise.resolve().then(() => this.flush());
      }
    }
  }

  /**
   * Synchronously flushes any pending state updates into a minimal path-based setData call.
   */
  public flush(): void {
    if (!this.isFlushScheduled && Object.keys(this.pendingChanges).length === 0) {
      return;
    }

    this.isFlushScheduled = false;
    const patch = this.computeDirtyDiff(this.previousState, this.pendingChanges);
    const keys = Object.keys(patch);

    if (keys.length > 0) {
      // Calculate payload size
      const payloadString = JSON.stringify(patch);
      const payloadBytes = new TextEncoder().encode(payloadString).length;

      this.stats.totalFlushes++;
      this.stats.totalKeysPatched += keys.length;
      this.stats.totalBytesSent += payloadBytes;

      if (payloadBytes > 1024 * 1024) {
        this.stats.warningsOver1MB++;
        console.warn(
          `[WeChatRuntimeBridge] setData payload exceeds 1024KB (${(payloadBytes / 1024).toFixed(1)}KB). Consider pagination or chunking.`
        );
      }

      // Update previous state with applied patch
      this.applyPatchToState(this.previousState, patch);
      this.pendingChanges = {};

      const currentCallbacks = [...this.callbacks];
      this.callbacks = [];

      this.instance.setData(patch, () => {
        for (const cb of currentCallbacks) {
          try {
            cb();
          } catch (err) {
            console.error("[WeChatRuntimeBridge] Error in setData callback:", err);
          }
        }
      });
    } else {
      // No dirty keys, run callbacks immediately
      const currentCallbacks = [...this.callbacks];
      this.callbacks = [];
      this.pendingChanges = {};
      for (const cb of currentCallbacks) {
        cb();
      }
    }
  }

  /**
   * Computes minimal path-based dirty diff between old state and new partial changes.
   * e.g. changes: { list: [a, b_new, c] } -> patch: { "list[1]": b_new }
   * e.g. changes: { user: { name: 'alice', age: 26 } } -> patch: { "user.age": 26 }
   */
  public computeDirtyDiff(
    base: Record<string, unknown>,
    changes: Record<string, unknown>
  ): Record<string, unknown> {
    const patch: Record<string, unknown> = {};

    for (const [key, newVal] of Object.entries(changes)) {
      const oldVal = base[key];
      this.diffRecursive(oldVal, newVal, key, patch);
    }

    return patch;
  }

  private diffRecursive(
    oldVal: unknown,
    newVal: unknown,
    currentPath: string,
    outPatch: Record<string, unknown>
  ): void {
    // 1. Exact equality (primitives, same reference)
    if (oldVal === newVal) {
      return;
    }

    // 2. Different types or null/undefined transition -> direct replace
    if (
      typeof oldVal !== typeof newVal ||
      oldVal === null ||
      newVal === null ||
      oldVal === undefined ||
      newVal === undefined
    ) {
      outPatch[currentPath] = newVal;
      return;
    }

    // 3. Array diffing
    if (Array.isArray(oldVal) && Array.isArray(newVal)) {
      if (oldVal.length !== newVal.length) {
        // If lengths differ, replacing the entire array is safer for WXML list indexing
        outPatch[currentPath] = newVal;
        return;
      }

      // Check item-by-item
      for (let i = 0; i < newVal.length; i++) {
        this.diffRecursive(oldVal[i], newVal[i], `${currentPath}[${i}]`, outPatch);
      }
      return;
    }

    // 4. Object diffing
    if (typeof oldVal === "object" && typeof newVal === "object") {
      const oldObj = oldVal as Record<string, unknown>;
      const newObj = newVal as Record<string, unknown>;

      const oldKeys = Object.keys(oldObj);
      const newKeys = Object.keys(newObj);

      // If keys were deleted, must replace whole object
      const hasDeletedKey = oldKeys.some((k) => !(k in newObj));
      if (hasDeletedKey) {
        outPatch[currentPath] = newVal;
        return;
      }

      for (const k of newKeys) {
        const subPath = `${currentPath}.${k}`;
        this.diffRecursive(oldObj[k], newObj[k], subPath, outPatch);
      }
      return;
    }

    // 5. Primitive changed value
    outPatch[currentPath] = newVal;
  }

  private applyPatchToState(target: Record<string, unknown>, patch: Record<string, unknown>): void {
    for (const [path, val] of Object.entries(patch)) {
      this.setValueByPath(target, path, this.deepClone(val));
    }
  }

  private setValueByPath(obj: Record<string, unknown>, path: string, val: unknown): void {
    // Parse path tokens e.g. "users[0].address.city" -> ["users", "0", "address", "city"]
    const tokens = path.replace(/\[(\w+)\]/g, ".$1").split(".");
    let curr: any = obj;

    for (let i = 0; i < tokens.length - 1; i++) {
      const token = tokens[i]!;
      if (!(token in curr) || curr[token] === null || typeof curr[token] !== "object") {
        const nextToken = tokens[i + 1]!;
        curr[token] = /^\d+$/.test(nextToken) ? [] : {};
      }
      curr = curr[token];
    }

    const lastToken = tokens[tokens.length - 1]!;
    curr[lastToken] = val;
  }

  private deepClone<T>(val: T): T {
    if (val === null || typeof val !== "object") return val;
    if (val instanceof Date) return new Date(val.getTime()) as any;
    if (Array.isArray(val)) return val.map((item) => this.deepClone(item)) as any;
    const copy: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(val as Record<string, unknown>)) {
      copy[k] = this.deepClone(v);
    }
    return copy as T;
  }

  public getStats(): PatchSchedulerStats {
    return { ...this.stats };
  }
}
