/**
 * @file enterprise-dynamic-state-engine.test.ts
 * @description Comprehensive unit & integration tests for Enterprise Dynamic State Management
 * across Redux Saga, Pinia plugins, MobX reactive proxies, and MiniApp setData architecture.
 */

import {
  MiniAppSagaRunner,
  SagaEffects,
  ReduxSagaAdapter,
  EnterprisePiniaStore,
  createMiniAppPersistedStatePlugin,
  createObservableProxy,
  autorun,
  reaction,
  MobXMiniAppBridge,
  MiniAppSetDataArchitecture,
} from '../src/store-engine';

describe('Enterprise Dynamic State Engine (M32)', () => {
  describe('Redux Saga Generator Coroutines & MiniAppSagaRunner', () => {
    it('should execute worker sagas yielding CALL, PUT, SELECT, and ALL', async () => {
      let state = { counter: 10, user: 'Stephen' };
      const dispatchedActions: any[] = [];

      const getState = () => state;
      const dispatch = (action: any) => {
        dispatchedActions.push(action);
        if (action.type === 'INCREMENT') {
          state = { ...state, counter: state.counter + 1 };
        }
      };

      const runner = new MiniAppSagaRunner(getState, dispatch);

      function* testWorker() {
        const currentUser = yield SagaEffects.select((s) => s.user);
        expect(currentUser).toBe('Stephen');

        const multiplied = yield SagaEffects.call((x: number, y: number) => x * y, 6, 7);
        expect(multiplied).toBe(42);

        yield SagaEffects.put({ type: 'INCREMENT' });

        const results = yield SagaEffects.all([
          SagaEffects.call(() => 'result_A'),
          SagaEffects.call(() => 'result_B'),
        ]);
        expect(results).toEqual(['result_A', 'result_B']);

        return 'DONE';
      }

      const finalVal = await runner.run(testWorker);
      expect(finalVal).toBe('DONE');
      expect(dispatchedActions).toEqual([{ type: 'INCREMENT' }]);
      expect(state.counter).toBe(11);
    });

    it('should parse Saga source and identify watchers and workers', () => {
      const adapter = new ReduxSagaAdapter();
      const sagaSource = `
        import { takeEvery, takeLatest, call, put } from 'redux-saga/effects';

        function* fetchUserData(action) {
          const res = yield call(fetch, '/api/user');
          yield put({ type: 'USER_SUCCESS', payload: res });
        }

        export function* watchUser() {
          yield takeLatest('FETCH_USER_REQUEST', fetchUserData);
        }
      `;

      const parsed = adapter.parse(sagaSource);
      expect(parsed.errors.length).toBe(0);
      expect(parsed.watchers.length).toBe(1);
      expect(parsed.watchers[0]?.pattern).toBe('FETCH_USER_REQUEST');
      expect(parsed.watchers[0]?.effect).toBe('takeLatest');
      expect(parsed.watchers[0]?.workerSagaName).toBe('fetchUserData');
    });
  });

  describe('Pinia & Vuex Advanced Plugins ($onAction, $patch, Persistence)', () => {
    it('should trigger $onAction before/after/error lifecycle hooks', async () => {
      const store = new EnterprisePiniaStore('cart', { items: [] as string[], count: 0 });
      const hookEvents: string[] = [];

      store.$onAction(({ name, after, onError }) => {
        hookEvents.push(`before:${name}`);
        after((result) => {
          hookEvents.push(`after:${name}:${result}`);
        });
        onError((err) => {
          hookEvents.push(`error:${name}:${err.message}`);
        });
      });

      store.registerAction('addItem', async (item: string) => {
        store.state.items.push(item);
        store.state.count++;
        return 'ITEM_ADDED';
      });

      const res = await store.dispatch('addItem', 'SKU_1001');
      expect(res).toBe('ITEM_ADDED');
      expect(store.state.items).toEqual(['SKU_1001']);
      expect(hookEvents).toEqual(['before:addItem', 'after:addItem:ITEM_ADDED']);
    });

    it('should support $patch both with partial object and mutator function', () => {
      const store = new EnterprisePiniaStore('user', { name: 'Alice', age: 25, role: 'user' });
      const mutationsCaptured: any[] = [];

      store.$subscribe((mutation, state) => {
        mutationsCaptured.push({ mutation, state: { ...state } });
      });

      // 1. Partial object patch
      store.$patch({ age: 26 });
      expect(store.state.age).toBe(26);

      // 2. Mutator function patch
      store.$patch((state) => {
        state.name = 'Bob';
        state.role = 'admin';
      });
      expect(store.state.name).toBe('Bob');
      expect(store.state.role).toBe('admin');
      expect(mutationsCaptured.length).toBe(2);
    });

    it('should connect to MiniApp setData and automatically sync mutations', () => {
      const store = new EnterprisePiniaStore('theme', { mode: 'light', primaryColor: '#1677ff' });
      const mockPage = {
        data: {},
        setData: jest.fn((patch) => {
          Object.assign(mockPage.data, patch);
        }),
      };

      const unbind = store.connectToMiniApp(mockPage);
      expect(mockPage.setData).toHaveBeenCalledWith({ mode: 'light', primaryColor: '#1677ff' });

      store.$patch({ mode: 'dark' });
      expect(mockPage.setData).toHaveBeenCalledWith({ mode: 'dark', primaryColor: '#1677ff' });

      unbind();
      store.$patch({ mode: 'sepia' });
      // Should not call after unbind
      expect(mockPage.data.mode).toBe('dark');
    });
  });

  describe('MobX Transparent Reactive Proxy (createObservableProxy, reaction, autorun)', () => {
    it('should transparently track property reads and fire autorun on mutation', () => {
      const rawState = { price: 100, quantity: 2 };
      const proxy = createObservableProxy(rawState);

      let computedTotal = 0;
      let runCount = 0;

      autorun(() => {
        runCount++;
        computedTotal = proxy.price * proxy.quantity;
      });

      expect(computedTotal).toBe(200);
      expect(runCount).toBe(1);

      proxy.price = 150;
      expect(computedTotal).toBe(300);
      expect(runCount).toBe(2);

      proxy.quantity = 4;
      expect(computedTotal).toBe(600);
      expect(runCount).toBe(3);
    });

    it('should fire reaction with new and old value', () => {
      const proxy = createObservableProxy({ user: { status: 'OFFLINE' } });
      const changes: Array<{ newVal: string; oldVal: string }> = [];

      reaction(
        () => proxy.user.status,
        (newVal, oldVal) => {
          changes.push({ newVal, oldVal });
        }
      );

      proxy.user.status = 'ONLINE';
      proxy.user.status = 'BUSY';

      expect(changes).toEqual([
        { newVal: 'ONLINE', oldVal: 'OFFLINE' },
        { newVal: 'BUSY', oldVal: 'ONLINE' },
      ]);
    });

    it('should automatically compute dirty paths and sync to MiniApp Page instance', (done) => {
      const bridge = new MobXMiniAppBridge({
        order: {
          items: [{ name: 'Book', qty: 1 }],
          shipping: { city: 'Hangzhou' },
        },
      });

      const mockPage = {
        data: {},
        setData: jest.fn((patch) => {
          Object.assign(mockPage.data, patch);
          expect(patch['order.items[0].qty']).toBe(3);
          done();
        }),
      };

      bridge.bindToMiniApp(mockPage);
      bridge.state.order.items[0]!.qty = 3;
    });
  });

  describe('MiniApp Granular Path-Diffing setData Architecture', () => {
    it('should compute minimal dot-delimited and bracket-delimited diff paths', () => {
      const arch = new MiniAppSetDataArchitecture();

      const oldState = {
        users: [
          { id: 1, name: 'Alice', active: true },
          { id: 2, name: 'Bob', active: false },
        ],
        settings: {
          theme: 'light',
          notifications: { email: true, sms: false },
        },
      };

      const newState = {
        users: [
          { id: 1, name: 'Alice', active: true },
          { id: 2, name: 'Bob', active: true }, // Changed active
        ],
        settings: {
          theme: 'dark', // Changed theme
          notifications: { email: true, sms: false },
        },
      };

      const diff = arch.computeDirtyDiff(oldState, newState);

      expect(diff).toEqual({
        'users[1].active': true,
        'settings.theme': 'dark',
      });
    });

    it('should chunk oversized payloads into multiple setData calls', () => {
      const arch = new MiniAppSetDataArchitecture({ maxPayloadBytes: 200 }); // Low limit for test
      const largePatch: Record<string, any> = {};

      for (let i = 0; i < 20; i++) {
        largePatch[`key_${i}`] = `some_long_payload_string_data_${i}`;
      }

      const mockInstance = {
        data: {},
        setData: jest.fn(),
      };

      arch.dispatchPatch(mockInstance, largePatch);

      expect(mockInstance.setData).toHaveBeenCalled();
      const metrics = arch.getMetrics();
      expect(metrics.warningsPayloadOver1MB).toBe(1);
      expect(metrics.chunkedCallCount).toBeGreaterThan(1);
    });
  });
});
