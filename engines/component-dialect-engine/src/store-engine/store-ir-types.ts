/**
 * @file store-ir-types.ts
 * @description Universal State Store IR contracts for cross-platform state modernization.
 * Models state properties, computed getters, synchronous mutations, asynchronous thunk actions,
 * subscriptions/effects, and persistence configurations across Zustand, Redux Toolkit, Pinia,
 * and WeChat MiniApp stores.
 * Conforms to Batch 32 Skill 1209 (b32-state-management-lifecycle).
 */

export type StoreFramework =
  | 'zustand'
  | 'redux-toolkit'
  | 'pinia'
  | 'miniapp-store'
  | 'signals-store'
  | 'universal';

export type StateStorageTarget =
  | 'memory'
  | 'localStorage'
  | 'sessionStorage'
  | 'wx-storage'
  | 'indexedDB'
  | 'secure-storage';

export interface StateTypeDescriptor {
  rawType: string;
  kind: 'primitive' | 'object' | 'array' | 'union' | 'map' | 'set' | 'custom';
  nullable: boolean;
  optional: boolean;
  typeArguments?: StateTypeDescriptor[];
  properties?: Record<string, StateTypeDescriptor>;
}

export interface StateFieldIR {
  name: string;
  type: StateTypeDescriptor;
  initialValueCode: string;
  isPersisted: boolean;
  isSensitive: boolean;
  isDerived?: boolean;
  comment?: string;
}

export interface StoreGetterIR {
  name: string;
  returnType: StateTypeDescriptor;
  dependencies: string[];
  computationBodyCode: string;
  isMemoized: boolean;
  comment?: string;
}

export interface ActionParamIR {
  name: string;
  type: StateTypeDescriptor;
  optional?: boolean;
  defaultValueCode?: string;
}

export interface StoreMutationIR {
  name: string;
  parameters: ActionParamIR[];
  description?: string;
  mutationBodyCode: string;
  affectedFields: string[];
  isPure: boolean;
}

export interface OptimisticUpdateConfig {
  targetField: string;
  optimisticValueCode: string;
  rollbackValueCode: string;
}

export interface StoreAsyncActionIR {
  name: string;
  parameters: ActionParamIR[];
  returnType: StateTypeDescriptor;
  loadingStateField?: string;
  errorStateField?: string;
  optimisticUpdate?: OptimisticUpdateConfig;
  executionBodyCode: string;
  dispatchedMutations: string[];
  sideEffects?: string[];
  comment?: string;
}

export interface StoreSubscriptionIR {
  name: string;
  watchedFields: string[];
  handlerBodyCode: string;
  cleanupCode?: string;
  debounceMs?: number;
  fireImmediately?: boolean;
}

export interface StorePersistenceConfigIR {
  storage: StateStorageTarget;
  storageKey: string;
  persistedFields: string[]; // empty means all persisted
  version?: number;
  migrateFunctionCode?: string;
  syncAcrossTabs?: boolean;
}

export interface UniversalStoreIR {
  storeId: string;
  storeName: string;
  description?: string;
  sourceFramework: StoreFramework;
  architecture: 'slice' | 'standalone-store' | 'modular-namespace';
  stateFields: StateFieldIR[];
  getters: StoreGetterIR[];
  mutations: StoreMutationIR[];
  actions: StoreAsyncActionIR[];
  subscriptions: StoreSubscriptionIR[];
  persistence?: StorePersistenceConfigIR;
  middleware?: string[];
  metadata?: Record<string, unknown>;
}

export interface StoreParseResult {
  success: boolean;
  storeIR?: UniversalStoreIR;
  errors: string[];
  warnings: string[];
  discoveredFramework: StoreFramework;
}

export interface StoreEmitResult {
  code: string;
  fileName: string;
  framework: StoreFramework;
  dependencies: Array<{ name: string; version: string; isDev: boolean }>;
  notes: string[];
}

export interface StoreMigrationPlan {
  sourceFramework: StoreFramework;
  targetFramework: StoreFramework;
  storeId: string;
  steps: Array<{
    stepName: string;
    description: string;
    affectedConstructs: string[];
  }>;
  warnings: string[];
  unsupportedFeatures: string[];
}
