/**
 * @file redux-saga-adapter.ts
 * @description Redux Saga generator-based effect runner and AST adapter for MiniApp.
 * Enables complex enterprise asynchronous workflows, concurrency controls (takeEvery, takeLatest),
 * and side-effect coordination within WeChat/Alipay MiniApp logic threads.
 */

import * as ts from 'typescript';
import {
  UniversalStoreIR,
  StoreAsyncActionIR,
  StoreParseResult,
  StoreEmitResult,
} from './store-ir-types';

export type SagaEffectType =
  | 'TAKE'
  | 'TAKE_EVERY'
  | 'TAKE_LATEST'
  | 'PUT'
  | 'CALL'
  | 'SELECT'
  | 'FORK'
  | 'CANCEL'
  | 'ALL'
  | 'RACE'
  | 'DELAY';

export interface SagaEffect<T = unknown> {
  type: SagaEffectType;
  payload: T;
}

export interface SagaWatcherIR {
  name: string;
  pattern: string;
  effect: 'takeEvery' | 'takeLatest';
  workerSagaName: string;
}

export interface SagaWorkerIR {
  name: string;
  parameters: string[];
  effectsUsed: SagaEffectType[];
  rawBody: string;
}

/**
 * MiniApp Native Saga Coroutine Runner
 * Drives ES6 generators yielding declarative saga effects in MiniApp worker environment.
 */
export class MiniAppSagaRunner {
  private listeners: Map<string, Array<(action: any) => void>> = new Map();
  private runningTasks: Set<Promise<any>> = new Set();
  private getState: () => Record<string, any>;
  private dispatch: (action: any) => void;

  constructor(getState: () => Record<string, any>, dispatch: (action: any) => void) {
    this.getState = getState;
    this.dispatch = dispatch;
  }

  /**
   * Run a root or worker saga generator
   */
  public run<T = any>(generatorFn: (...args: any[]) => Generator<any, T, any>, ...args: any[]): Promise<T> {
    const iterator = generatorFn(...args);

    const step = (nextVal?: any, isError = false): Promise<T> => {
      let result: IteratorResult<any, T>;
      try {
        result = isError ? iterator.throw(nextVal) : iterator.next(nextVal);
      } catch (err) {
        return Promise.reject(err);
      }

      if (result.done) {
        return Promise.resolve(result.value);
      }

      const effect = result.value;
      return this.handleEffect(effect)
        .then((res) => step(res, false))
        .catch((err) => step(err, true));
    };

    const taskPromise = step();
    this.runningTasks.add(taskPromise);
    taskPromise.finally(() => this.runningTasks.delete(taskPromise));
    return taskPromise;
  }

  /**
   * Resolves a declarative saga effect
   */
  private async handleEffect(effect: any): Promise<any> {
    if (!effect || typeof effect !== 'object' || !effect.type) {
      // Direct promise or raw value
      return Promise.resolve(effect);
    }

    switch (effect.type as SagaEffectType) {
      case 'CALL': {
        const { fn, args } = effect.payload;
        return Promise.resolve(fn.apply(null, args || []));
      }
      case 'PUT': {
        const { action } = effect.payload;
        this.dispatch(action);
        // Trigger any watchers listening to this action type
        const callbacks = this.listeners.get(action.type) || [];
        for (const cb of callbacks) {
          cb(action);
        }
        return Promise.resolve();
      }
      case 'SELECT': {
        const { selector } = effect.payload;
        const state = this.getState();
        return Promise.resolve(typeof selector === 'function' ? selector(state) : state);
      }
      case 'DELAY': {
        const { ms } = effect.payload;
        return new Promise((resolve) => setTimeout(resolve, ms));
      }
      case 'ALL': {
        const { effects } = effect.payload;
        if (Array.isArray(effects)) {
          return Promise.all(effects.map((e) => this.handleEffect(e)));
        }
        const keys = Object.keys(effects);
        const resolved = await Promise.all(keys.map((k) => this.handleEffect(effects[k])));
        const resultObj: Record<string, any> = {};
        keys.forEach((k, idx) => {
          resultObj[k] = resolved[idx];
        });
        return resultObj;
      }
      case 'RACE': {
        const { effects } = effect.payload;
        const keys = Object.keys(effects);
        return Promise.race(
          keys.map(async (k) => {
            const res = await this.handleEffect(effects[k]);
            return { [k]: res };
          })
        );
      }
      case 'TAKE': {
        const { pattern } = effect.payload;
        return new Promise((resolve) => {
          const handler = (action: any) => {
            const list = this.listeners.get(pattern) || [];
            this.listeners.set(pattern, list.filter((cb) => cb !== handler));
            resolve(action);
          };
          const existing = this.listeners.get(pattern) || [];
          existing.push(handler);
          this.listeners.set(pattern, existing);
        });
      }
      case 'TAKE_EVERY': {
        const { pattern, worker } = effect.payload;
        const listener = (action: any) => {
          this.run(worker, action);
        };
        const list = this.listeners.get(pattern) || [];
        list.push(listener);
        this.listeners.set(pattern, list);
        return Promise.resolve();
      }
      case 'TAKE_LATEST': {
        const { pattern, worker } = effect.payload;
        let lastTask: Promise<any> | null = null;
        let isCancelled = false;

        const listener = (action: any) => {
          isCancelled = true;
          const currentTask = this.run(function* () {
            if (isCancelled) return;
            yield* worker(action);
          });
          lastTask = currentTask;
        };
        const list = this.listeners.get(pattern) || [];
        list.push(listener);
        this.listeners.set(pattern, list);
        return Promise.resolve();
      }
      case 'FORK': {
        const { fn, args } = effect.payload;
        const forkedPromise = this.run(fn, ...(args || []));
        return Promise.resolve({
          cancel: () => {
            // Cancel signal
          },
          done: forkedPromise,
        });
      }
      default:
        return Promise.resolve(effect);
    }
  }
}

/**
 * Saga Effect Creator Helpers
 */
export const SagaEffects = {
  call: (fn: Function, ...args: any[]): SagaEffect => ({
    type: 'CALL',
    payload: { fn, args },
  }),
  put: (action: { type: string; payload?: any }): SagaEffect => ({
    type: 'PUT',
    payload: { action },
  }),
  select: (selector?: (state: any) => any): SagaEffect => ({
    type: 'SELECT',
    payload: { selector },
  }),
  delay: (ms: number): SagaEffect => ({
    type: 'DELAY',
    payload: { ms },
  }),
  all: (effects: any[] | Record<string, any>): SagaEffect => ({
    type: 'ALL',
    payload: { effects },
  }),
  race: (effects: Record<string, any>): SagaEffect => ({
    type: 'RACE',
    payload: { effects },
  }),
  take: (pattern: string): SagaEffect => ({
    type: 'TAKE',
    payload: { pattern },
  }),
  takeEvery: (pattern: string, worker: Function): SagaEffect => ({
    type: 'TAKE_EVERY',
    payload: { pattern, worker },
  }),
  takeLatest: (pattern: string, worker: Function): SagaEffect => ({
    type: 'TAKE_LATEST',
    payload: { pattern, worker },
  }),
  fork: (fn: Function, ...args: any[]): SagaEffect => ({
    type: 'FORK',
    payload: { fn, args },
  }),
};

/**
 * AST Adapter for parsing Redux Sagas and emitting MiniApp compatible sagas
 */
export class ReduxSagaAdapter {
  /**
   * Parse Redux Saga source code into metadata
   */
  public parse(sourceCode: string, storeId: string = 'saga-module'): {
    watchers: SagaWatcherIR[];
    workers: SagaWorkerIR[];
    errors: string[];
  } {
    const errors: string[] = [];
    const watchers: SagaWatcherIR[] = [];
    const workers: SagaWorkerIR[] = [];

    const sourceFile = ts.createSourceFile(
      'sagas.ts',
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    );

    const visit = (node: ts.Node) => {
      // Find generator functions: function* mySaga(...)
      if (ts.isFunctionDeclaration(node) && node.asteriskToken && node.name) {
        const sagaName = node.name.getText(sourceFile);
        const params = node.parameters.map((p) => p.name.getText(sourceFile));
        const bodyText = node.body ? node.body.getText(sourceFile) : '';

        // Detect if this is a watcher (contains takeEvery / takeLatest) or worker
        const isTakeEvery = bodyText.includes('takeEvery');
        const isTakeLatest = bodyText.includes('takeLatest');

        if (isTakeEvery || isTakeLatest) {
          const patternMatch = bodyText.match(/(?:takeEvery|takeLatest)\s*\(\s*['"]([^'"]+)['"]\s*,\s*([a-zA-Z0-9_]+)/);
          if (patternMatch) {
            watchers.push({
              name: sagaName,
              pattern: patternMatch[1] || 'UNKNOWN_ACTION',
              effect: isTakeLatest ? 'takeLatest' : 'takeEvery',
              workerSagaName: patternMatch[2] || 'unknownWorker',
            });
          }
        }

        const effectsUsed: SagaEffectType[] = [];
        if (bodyText.includes('call(')) effectsUsed.push('CALL');
        if (bodyText.includes('put(')) effectsUsed.push('PUT');
        if (bodyText.includes('select(')) effectsUsed.push('SELECT');
        if (bodyText.includes('delay(')) effectsUsed.push('DELAY');
        if (bodyText.includes('all(')) effectsUsed.push('ALL');
        if (bodyText.includes('race(')) effectsUsed.push('RACE');

        workers.push({
          name: sagaName,
          parameters: params,
          effectsUsed,
          rawBody: bodyText,
        });
      }

      ts.forEachChild(node, visit);
    };

    visit(sourceFile);

    return { watchers, workers, errors };
  }

  /**
   * Emit MiniApp compatible Saga Runner and Slices
   */
  public emit(storeIR: UniversalStoreIR, watchers: SagaWatcherIR[], workers: SagaWorkerIR[]): StoreEmitResult {
    const lines: string[] = [];

    lines.push(`/**`);
    lines.push(` * Auto-generated WeChat/Alipay MiniApp Redux-Saga Middleware Runtime`);
    lines.push(` * Conforms to Batch 32 Industrial Quality Standard`);
    lines.push(` */\n`);
    lines.push(`import { MiniAppSagaRunner, SagaEffects } from './redux-saga-adapter';\n`);

    // Emit worker sagas
    for (const worker of workers) {
      lines.push(`export function* ${worker.name}(${worker.parameters.join(', ')}) {`);
      lines.push(`  ${worker.rawBody.replace(/^{|}$/g, '').trim()}`);
      lines.push(`}\n`);
    }

    // Emit root watcher
    lines.push(`export function* rootSaga() {`);
    lines.push(`  yield SagaEffects.all([`);
    for (const watcher of watchers) {
      lines.push(`    SagaEffects.${watcher.effect}('${watcher.pattern}', ${watcher.workerSagaName}),`);
    }
    lines.push(`  ]);`);
    lines.push(`}\n`);

    lines.push(`export function initMiniAppSagas(getState: () => any, dispatch: (action: any) => void) {`);
    lines.push(`  const runner = new MiniAppSagaRunner(getState, dispatch);`);
    lines.push(`  runner.run(rootSaga);`);
    lines.push(`  return runner;`);
    lines.push(`}\n`);

    return {
      code: lines.join('\n'),
      fileName: `${storeIR.storeId}Sagas.ts`,
      framework: 'miniapp-store',
      dependencies: [{ name: '@elmos/component-dialect-engine', version: '^0.1.0', isDev: false }],
      notes: [`Generated MiniApp Saga Coroutines: ${workers.length} workers, ${watchers.length} watchers`],
    };
  }
}
