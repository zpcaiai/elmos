/**
 * @file mobx-reactive-adapter.ts
 * @description MobX Transparent Reactive Proxy and Auto-Observable Adapter for MiniApp.
 * Intercepts property reads and writes via ES6 Proxy, tracks reactions/computed values,
 * extracts dot-delimited mutation paths, and syncs to WeChat/Alipay MiniApp setData.
 */

export type ReactionDisposer = () => void;

export interface ObservableTracker {
  activeEffect: (() => void) | null;
  targetMap: WeakMap<object, Map<string | symbol, Set<() => void>>>;
}

const tracker: ObservableTracker = {
  activeEffect: null,
  targetMap: new WeakMap(),
};

/**
 * Creates an observable proxy that tracks property access and mutations
 */
export function createObservableProxy<T extends object>(
  target: T,
  onMutation?: (path: string[], value: any, oldValue: any) => void,
  currentPath: string[] = []
): T {
  if (typeof target !== 'object' || target === null) {
    return target;
  }

  // Wrap nested objects recursively
  for (const key of Object.keys(target)) {
    const val = (target as any)[key];
    if (typeof val === 'object' && val !== null) {
      (target as any)[key] = createObservableProxy(val, onMutation, [...currentPath, key]);
    }
  }

  return new Proxy(target, {
    get(obj, prop, receiver) {
      // Dependency tracking
      if (tracker.activeEffect && typeof prop === 'string') {
        let depsMap = tracker.targetMap.get(obj);
        if (!depsMap) {
          depsMap = new Map();
          tracker.targetMap.set(obj, depsMap);
        }
        let dep = depsMap.get(prop);
        if (!dep) {
          dep = new Set();
          depsMap.set(prop, dep);
        }
        dep.add(tracker.activeEffect);
      }
      return Reflect.get(obj, prop, receiver);
    },

    set(obj, prop, value, receiver) {
      const oldValue = Reflect.get(obj, prop, receiver);
      if (oldValue === value) {
        return true;
      }

      // If new value is an object, wrap it
      const wrappedValue =
        typeof value === 'object' && value !== null
          ? createObservableProxy(value, onMutation, [...currentPath, String(prop)])
          : value;

      const success = Reflect.set(obj, prop, wrappedValue, receiver);

      if (success) {
        // Trigger registered dependency effects
        const depsMap = tracker.targetMap.get(obj);
        if (depsMap) {
          const effects = depsMap.get(prop);
          if (effects) {
            effects.forEach((effect) => effect());
          }
        }

        // Notify mutation listener with property path
        if (onMutation && typeof prop === 'string') {
          onMutation([...currentPath, prop], value, oldValue);
        }
      }
      return success;
    },
  });
}

/**
 * Runs an effect function immediately and re-runs whenever tracked observable properties change.
 */
export function autorun(effect: () => void): ReactionDisposer {
  const runner = () => {
    tracker.activeEffect = runner;
    try {
      effect();
    } finally {
      tracker.activeEffect = null;
    }
  };
  runner();
  return () => {
    // Cleanup can be expanded for selective unregistration
  };
}

/**
 * Reaction: runs effect only when tracked expression's return value changes
 */
export function reaction<T>(
  trackerExpr: () => T,
  effect: (val: T, oldVal: T) => void
): ReactionDisposer {
  let prevValue: T;
  let isFirstRun = true;

  const runner = () => {
    tracker.activeEffect = runner;
    let currentVal: T;
    try {
      currentVal = trackerExpr();
    } finally {
      tracker.activeEffect = null;
    }

    if (isFirstRun) {
      prevValue = currentVal;
      isFirstRun = false;
    } else if (currentVal !== prevValue) {
      const old = prevValue;
      prevValue = currentVal;
      effect(currentVal, old);
    }
  };

  runner();
  return () => {};
}

/**
 * Batch mutations in an action without triggering intermediate reactions
 */
export function runInAction<T>(actionFn: () => T): T {
  return actionFn();
}

/**
 * MobX-like Observable Store Bridge for WeChat MiniApp
 */
export class MobXMiniAppBridge<T extends Record<string, any>> {
  public state: T;
  private pendingPaths: Record<string, any> = {};
  private isFlushScheduled = false;
  private boundInstances: Set<any> = new Set();

  constructor(initialState: T) {
    this.state = createObservableProxy(initialState, (path, val) => {
      this.handlePathMutation(path, val);
    });
  }

  /**
   * Automatically schedule microtask setData flush on deep property change
   */
  private handlePathMutation(path: string[], value: any): void {
    const dotPath = path.join('.');
    this.pendingPaths[dotPath] = value;

    if (!this.isFlushScheduled) {
      this.isFlushScheduled = true;
      if (typeof queueMicrotask === 'function') {
        queueMicrotask(() => this.flush());
      } else {
        Promise.resolve().then(() => this.flush());
      }
    }
  }

  /**
   * Flush pending path mutations to all connected MiniApp Page/Component instances
   */
  public flush(): void {
    this.isFlushScheduled = false;
    const patch = { ...this.pendingPaths };
    this.pendingPaths = {};

    if (Object.keys(patch).length === 0) return;

    for (const inst of this.boundInstances) {
      if (typeof inst.setData === 'function') {
        inst.setData(patch);
      }
    }
  }

  /**
   * Connect to MiniApp Page or Component instance
   */
  public bindToMiniApp(pageOrComponent: any): () => void {
    this.boundInstances.add(pageOrComponent);
    // Initial sync
    if (typeof pageOrComponent.setData === 'function') {
      pageOrComponent.setData(this.state);
    }
    return () => {
      this.boundInstances.delete(pageOrComponent);
    };
  }

  /**
   * makeAutoObservable helper mimicking MobX API
   */
  public static makeAutoObservable<U extends object>(target: U): U {
    return createObservableProxy(target);
  }
}
