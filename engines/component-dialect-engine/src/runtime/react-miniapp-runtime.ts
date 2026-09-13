/**
 * Enterprise React -> WeChat MiniProgram Runtime Polyfill Layer
 * 
 * Provides a transactional React Hooks and state reconciliation engine
 * that runs natively inside WeChat MiniProgram Component instances.
 * Solves:
 * 1. Dual-thread asynchronous timing and race conditions
 * 2. Closure variable capture and isolation
 * 3. Atomic batched setData scheduling
 * 4. useEffect lifecycle management and cleanup
 */

export interface HookEffect {
  idx: number;
  effect: () => void | (() => void);
  deps?: unknown[];
  cleanup?: void | (() => void);
}

export interface MiniProgramComponentInstance {
  properties: Record<string, unknown>;
  data: Record<string, unknown>;
  setData(data: Record<string, unknown>, callback?: () => void): void;
  triggerEvent(name: string, detail?: unknown, options?: unknown): void;
  [key: string]: unknown;
}

export class ReactMiniAppHookContext {
  private instance: MiniProgramComponentInstance;
  private hookIndex = 0;
  private hooks: unknown[] = [];
  private effects: HookEffect[] = [];
  private cleanups: (() => void)[] = [];
  private pendingSetData: Record<string, unknown> = {};
  private scheduledFlush = false;
  private isMounted = false;

  constructor(instance: MiniProgramComponentInstance) {
    this.instance = instance;
  }

  public resetIndex(): void {
    this.hookIndex = 0;
  }

  public markMounted(): void {
    this.isMounted = true;
    this.flushEffects();
  }

  public markUnmounted(): void {
    this.isMounted = false;
    for (const cleanup of this.cleanups) {
      try {
        cleanup();
      } catch (err) {
        console.error("[ReactMiniAppRuntime] Error during effect cleanup:", err);
      }
    }
    this.cleanups = [];
    this.effects = [];
  }

  public useState<T>(initial: T | (() => T)): [T, (next: T | ((prev: T) => T)) => void] {
    const idx = this.hookIndex++;
    if (this.hooks[idx] === undefined) {
      this.hooks[idx] = typeof initial === "function" ? (initial as () => T)() : initial;
    }
    const currentState = this.hooks[idx] as T;

    const setState = (next: T | ((prev: T) => T)) => {
      const prev = this.hooks[idx] as T;
      const resolved = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
      if (!Object.is(prev, resolved)) {
        this.hooks[idx] = resolved;
        this.scheduleSetData(`_h${idx}`, resolved);
      }
    };

    return [currentState, setState];
  }

  public useEffect(effect: () => void | (() => void), deps?: unknown[]): void {
    const idx = this.hookIndex++;
    const old = this.hooks[idx] as { deps?: unknown[]; cleanup?: () => void } | undefined;
    const hasChanged = !old || !deps || deps.some((d, i) => !Object.is(d, old.deps?.[i]));

    if (hasChanged) {
      this.effects.push({ idx, effect, deps, cleanup: old?.cleanup });
    }
  }

  public useMemo<T>(factory: () => T, deps?: unknown[]): T {
    const idx = this.hookIndex++;
    const old = this.hooks[idx] as { value: T; deps?: unknown[] } | undefined;
    if (old && deps && deps.every((d, i) => Object.is(d, old.deps?.[i]))) {
      return old.value;
    }
    const value = factory();
    this.hooks[idx] = { value, deps };
    return value;
  }

  public useCallback<T extends (...args: unknown[]) => unknown>(callback: T, deps?: unknown[]): T {
    return this.useMemo(() => callback, deps);
  }

  public useRef<T>(initialValue: T): { current: T } {
    const idx = this.hookIndex++;
    if (!this.hooks[idx]) {
      this.hooks[idx] = { current: initialValue };
    }
    return this.hooks[idx] as { current: T };
  }

  public scheduleSetData(key: string, value: unknown): void {
    this.pendingSetData[key] = value;
    if (!this.scheduledFlush) {
      this.scheduledFlush = true;
      Promise.resolve().then(() => {
        this.flushPendingSetData();
      });
    }
  }

  public flushPendingSetData(): void {
    if (!this.scheduledFlush) return;
    const payload = this.pendingSetData;
    this.pendingSetData = {};
    this.scheduledFlush = false;

    if (Object.keys(payload).length > 0) {
      this.instance.setData(payload, () => {
        if (this.isMounted) {
          this.flushEffects();
        }
      });
    }
  }

  public flushEffects(): void {
    const toRun = [...this.effects];
    this.effects = [];

    for (const item of toRun) {
      if (item.cleanup) {
        try {
          item.cleanup();
          const cleanupIdx = this.cleanups.indexOf(item.cleanup);
          if (cleanupIdx !== -1) this.cleanups.splice(cleanupIdx, 1);
        } catch (err) {
          console.error("[ReactMiniAppRuntime] Error running previous cleanup:", err);
        }
      }
      try {
        const cleanup = item.effect();
        if (typeof cleanup === "function") {
          this.cleanups.push(cleanup);
          this.hooks[item.idx] = { deps: item.deps, cleanup };
        } else {
          this.hooks[item.idx] = { deps: item.deps };
        }
      } catch (err) {
        console.error("[ReactMiniAppRuntime] Error executing effect:", err);
        throw err;
      }
    }
  }
}

/**
 * Higher-order Component generator that connects a React-style component setup function
 * to a standard WeChat MiniProgram Component definition.
 */
export function createReactMiniAppBridge(definition: {
  properties?: Record<string, { type: unknown; value?: unknown }>;
  data?: Record<string, unknown>;
  setup: (props: Record<string, unknown>, hooks: ReactMiniAppHookContext) => Record<string, unknown>;
  methods?: Record<string, (...args: unknown[]) => unknown>;
}): Record<string, unknown> {
  return {
    options: {
      multipleSlots: true,
      addGlobalClass: true,
    },
    properties: definition.properties || {},
    data: definition.data || {},
    lifetimes: {
      attached(this: MiniProgramComponentInstance & { __reactContext?: ReactMiniAppHookContext }) {
        const ctx = new ReactMiniAppHookContext(this);
        this.__reactContext = ctx;

        try {
          ctx.resetIndex();
          const stateValues = definition.setup(this.properties, ctx);
          if (stateValues && typeof stateValues === "object") {
            this.setData(stateValues as Record<string, unknown>, () => {
              ctx.markMounted();
            });
          } else {
            ctx.markMounted();
          }
        } catch (err) {
          console.error(`[ReactMiniAppBridge] Error in component attached:`, err);
          throw err;
        }
      },
      ready(this: MiniProgramComponentInstance & { __reactContext?: ReactMiniAppHookContext }) {
        if (this.__reactContext) {
          this.__reactContext.flushEffects();
        }
      },
      detached(this: MiniProgramComponentInstance & { __reactContext?: ReactMiniAppHookContext }) {
        if (this.__reactContext) {
          this.__reactContext.markUnmounted();
          delete this.__reactContext;
        }
      },
    },
    methods: {
      ...definition.methods,
    },
  };
}
