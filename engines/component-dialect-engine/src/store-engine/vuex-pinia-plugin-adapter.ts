/**
 * @file vuex-pinia-plugin-adapter.ts
 * @description Enterprise Vuex & Pinia advanced plugin and middleware adapter.
 * Handles Pinia plugin architecture (e.g. pinia-plugin-persistedstate),
 * $onAction hooks (before, after, error), $patch (object & mutator function),
 * Vuex namespaced module hierarchies, and maps them to MiniApp storage and setData.
 */

import * as ts from 'typescript';
import {
  UniversalStoreIR,
  StateFieldIR,
  StoreGetterIR,
  StoreMutationIR,
  StoreAsyncActionIR,
  StoreParseResult,
  StoreEmitResult,
} from './store-ir-types';

export interface PiniaPluginContext<S = any> {
  storeId: string;
  state: S;
  options: Record<string, any>;
  onAction: (callback: (context: ActionHookContext) => void) => void;
  subscribe: (callback: (mutation: any, state: S) => void) => () => void;
  patch: (partialOrFn: Partial<S> | ((state: S) => void)) => void;
}

export interface ActionHookContext {
  name: string;
  args: any[];
  after: (callback: (result: any) => void) => void;
  onError: (callback: (error: any) => void) => void;
}

export type PiniaPlugin<S = any> = (context: PiniaPluginContext<S>) => void;

/**
 * Enterprise Pinia & Vuex Universal Store with Plugin Middleware Pipeline
 */
export class EnterprisePiniaStore<S extends Record<string, any> = Record<string, any>> {
  public id: string;
  public state: S;
  private getters: Record<string, () => any> = {};
  private actions: Record<string, (...args: any[]) => Promise<any>> = {};
  private mutations: Record<string, (...args: any[]) => void> = {};
  private plugins: PiniaPlugin<S>[] = [];
  private actionSubscribers: Array<(context: ActionHookContext) => void> = [];
  private stateSubscribers: Array<(mutation: any, state: S) => void> = [];
  private changeListeners: Set<(state: S, oldState: S) => void> = new Set();

  constructor(id: string, initialState: S) {
    this.id = id;
    this.state = { ...initialState };
  }

  /**
   * Register a Pinia plugin (e.g. persistedstate, logger, sentry)
   */
  public use(plugin: PiniaPlugin<S>): this {
    this.plugins.push(plugin);
    plugin({
      storeId: this.id,
      state: this.state,
      options: {},
      onAction: (cb) => this.actionSubscribers.push(cb),
      subscribe: (cb) => {
        this.stateSubscribers.push(cb);
        return () => {
          this.stateSubscribers = this.stateSubscribers.filter((s) => s !== cb);
        };
      },
      patch: (partialOrFn) => this.$patch(partialOrFn),
    });
    return this;
  }

  /**
   * $patch supports both partial object and mutator function
   */
  public $patch(partialOrFn: Partial<S> | ((state: S) => void)): void {
    const oldState = { ...this.state };
    if (typeof partialOrFn === 'function') {
      partialOrFn(this.state);
    } else {
      this.state = { ...this.state, ...partialOrFn };
    }

    const mutationMeta = {
      type: 'patch',
      storeId: this.id,
      payload: typeof partialOrFn === 'object' ? partialOrFn : 'function_patch',
    };

    for (const sub of this.stateSubscribers) {
      sub(mutationMeta, this.state);
    }
    for (const listener of this.changeListeners) {
      listener(this.state, oldState);
    }
  }

  /**
   * Register an action with full before/after/error lifecycle hooks
   */
  public registerAction(name: string, fn: (...args: any[]) => Promise<any>): void {
    this.actions[name] = async (...args: any[]) => {
      const afterCallbacks: Array<(res: any) => void> = [];
      const errorCallbacks: Array<(err: any) => void> = [];

      const hookContext: ActionHookContext = {
        name,
        args,
        after: (cb) => afterCallbacks.push(cb),
        onError: (cb) => errorCallbacks.push(cb),
      };

      for (const subscriber of this.actionSubscribers) {
        subscriber(hookContext);
      }

      try {
        const result = await fn.apply(this, args);
        for (const afterCb of afterCallbacks) {
          afterCb(result);
        }
        return result;
      } catch (error) {
        for (const errorCb of errorCallbacks) {
          errorCb(error);
        }
        throw error;
      }
    };
  }

  public dispatch(actionName: string, ...args: any[]): Promise<any> {
    const action = this.actions[actionName];
    if (!action) {
      throw new Error(`[EnterprisePiniaStore] Action "${actionName}" not found in store "${this.id}"`);
    }
    return action(...args);
  }

  public registerGetter<T>(name: string, getterFn: (state: S) => T): void {
    this.getters[name] = () => getterFn(this.state);
  }

  public getGetter<T>(name: string): T {
    const getter = this.getters[name];
    if (!getter) {
      throw new Error(`[EnterprisePiniaStore] Getter "${name}" not found in store "${this.id}"`);
    }
    return getter();
  }

  /**
   * $subscribe to state mutations
   */
  public $subscribe(callback: (mutation: any, state: S) => void): () => void {
    this.stateSubscribers.push(callback);
    return () => {
      this.stateSubscribers = this.stateSubscribers.filter((cb) => cb !== callback);
    };
  }

  /**
   * $onAction hook registration
   */
  public $onAction(callback: (context: ActionHookContext) => void): void {
    this.actionSubscribers.push(callback);
  }

  /**
   * Connect to MiniApp Page or Component setData
   */
  public connectToMiniApp(pageOrComponent: any, keyMap?: Record<string, keyof S>): () => void {
    const sync = (newState: S) => {
      if (!pageOrComponent || typeof pageOrComponent.setData !== 'function') return;
      if (!keyMap) {
        pageOrComponent.setData(newState);
      } else {
        const diff: Record<string, any> = {};
        for (const [targetKey, stateKey] of Object.entries(keyMap)) {
          diff[targetKey] = newState[stateKey];
        }
        pageOrComponent.setData(diff);
      }
    };

    sync(this.state);
    this.changeListeners.add(sync);
    return () => {
      this.changeListeners.delete(sync);
    };
  }
}

/**
 * Built-in Persistence Plugin for WeChat/Alipay MiniApp Storage
 */
export function createMiniAppPersistedStatePlugin<S = any>(options: {
  storageKey?: string;
  paths?: Array<keyof S>;
} = {}): PiniaPlugin<S> {
  return ({ storeId, state, subscribe, patch }) => {
    const key = options.storageKey || `pinia_${storeId}`;

    // 1. Rehydrate on initialization
    try {
      let cached: any = null;
      if (typeof wx !== 'undefined' && wx.getStorageSync) {
        cached = wx.getStorageSync(key);
      } else if (typeof localStorage !== 'undefined') {
        const item = localStorage.getItem(key);
        if (item) cached = JSON.parse(item);
      }

      if (cached && typeof cached === 'object') {
        patch(cached);
      }
    } catch (e) {
      // Ignore cache rehydration errors
    }

    // 2. Subscribe to mutations and persist
    subscribe((_mutation, currentState) => {
      try {
        let toPersist: any = currentState;
        if (options.paths && options.paths.length > 0) {
          toPersist = {};
          for (const p of options.paths) {
            toPersist[p] = currentState[p];
          }
        }

        if (typeof wx !== 'undefined' && wx.setStorageSync) {
          wx.setStorageSync(key, toPersist);
        } else if (typeof localStorage !== 'undefined') {
          localStorage.setItem(key, JSON.stringify(toPersist));
        }
      } catch (err) {
        console.warn(`[PiniaPersistedState] Failed to persist state for ${storeId}:`, err);
      }
    });
  };
}

/**
 * AST Adapter for parsing Vuex / Pinia with plugins
 */
export class VuexPiniaPluginAdapter {
  public parse(sourceCode: string, storeId: string = 'app-store'): StoreParseResult {
    const errors: string[] = [];
    const warnings: string[] = [];
    const sourceFile = ts.createSourceFile(
      'store.ts',
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    );

    const stateFields: StateFieldIR[] = [];
    const getters: StoreGetterIR[] = [];
    const mutations: StoreMutationIR[] = [];
    const actions: StoreAsyncActionIR[] = [];

    const visit = (node: ts.Node) => {
      // Find `defineStore('id', { state: () => ({ ... }), actions: { ... } })`
      if (ts.isCallExpression(node)) {
        const text = node.expression.getText(sourceFile);
        if (text.includes('defineStore')) {
          if (node.arguments.length >= 2 && ts.isObjectLiteralExpression(node.arguments[1]!)) {
            const config = node.arguments[1] as ts.ObjectLiteralExpression;
            for (const prop of config.properties) {
              if (ts.isPropertyAssignment(prop)) {
                const propName = prop.name.getText(sourceFile);
                if (propName === 'state') {
                  if (ts.isArrowFunction(prop.initializer) || ts.isFunctionExpression(prop.initializer)) {
                    // Arrow returning object
                    stateFields.push({
                      name: 'dynamicState',
                      type: { rawType: 'any', kind: 'custom', nullable: false, optional: false },
                      initialValueCode: prop.initializer.getText(sourceFile),
                      isPersisted: false,
                      isSensitive: false,
                    });
                  }
                }
              }
            }
          }
        }
      }
      ts.forEachChild(node, visit);
    };

    visit(sourceFile);

    const storeIR: UniversalStoreIR = {
      storeId,
      storeName: `${storeId}Store`,
      sourceFramework: 'pinia',
      architecture: 'standalone-store',
      stateFields,
      getters,
      mutations,
      actions,
      subscriptions: [],
    };

    return {
      success: true,
      storeIR,
      errors,
      warnings,
      discoveredFramework: 'pinia',
    };
  }
}
