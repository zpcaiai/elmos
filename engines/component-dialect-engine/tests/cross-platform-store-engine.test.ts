/**
 * @file cross-platform-store-engine.test.ts
 * @description Comprehensive Jest test suite for the Cross-Platform Store Engine (Skill 1209).
 * Tests Zustand, Redux Toolkit, Pinia, and MiniApp Store adapters and cross-framework transformation.
 * Conforms to Batch 32 Skill 1209 (b32-state-management-lifecycle).
 */

import { CrossPlatformStoreLowerer } from '../src/store-engine/cross-platform-store-lowerer';
import { ZustandAdapter } from '../src/store-engine/zustand-adapter';
import { ReduxToolkitAdapter } from '../src/store-engine/redux-toolkit-adapter';
import { PiniaAdapter } from '../src/store-engine/pinia-adapter';
import { MiniAppStoreAdapter } from '../src/store-engine/miniapp-store-adapter';

describe('Cross-Platform Store Engine (Skill 1209)', () => {
  const lowerer = new CrossPlatformStoreLowerer();
  const zustandAdapter = new ZustandAdapter();
  const rtkAdapter = new ReduxToolkitAdapter();
  const piniaAdapter = new PiniaAdapter();
  const miniappAdapter = new MiniAppStoreAdapter();

  const sampleZustandCode = `
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const useCartStore = create()(
  persist(
    (set, get) => ({
      items: [],
      totalPrice: 0,
      isOpen: false,
      addItem: (item) => {
        set((state) => ({ items: [...state.items, item] }));
      },
      clearCart: () => {
        set({ items: [], totalPrice: 0 });
      },
      checkout: async (paymentToken) => {
        set({ isOpen: false });
      },
    }),
    {
      name: 'cart-storage',
    }
  )
);
`;

  const sampleRTKCode = `
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';

export const fetchUser = createAsyncThunk(
  'user/fetchUser',
  async (userId: string) => {
    return { id: userId, name: 'John Doe' };
  }
);

export const userSlice = createSlice({
  name: 'user',
  initialState: {
    name: 'Guest',
    isLoggedIn: false,
    roles: ['viewer'],
  },
  reducers: {
    setLoggedIn: (state, action: PayloadAction<boolean>) => {
      state.isLoggedIn = action.payload;
    },
    logout: (state) => {
      state.isLoggedIn = false;
      state.name = 'Guest';
    },
  },
});
`;

  const samplePiniaCode = `
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export const useCounterStore = defineStore('counter', () => {
  const count = ref(10);
  const step = ref(1);

  const doubleCount = computed(() => count.value * 2);

  function increment() {
    count.value += step.value;
  }

  function decrement() {
    count.value -= step.value;
  }

  async function resetAsync() {
    count.value = 0;
  }

  return { count, step, doubleCount, increment, decrement, resetAsync };
});
`;

  describe('Zustand Adapter', () => {
    it('should parse Zustand store with middleware, state fields, mutations, and actions', () => {
      const res = zustandAdapter.parse(sampleZustandCode, 'cart');
      expect(res.success).toBe(true);
      expect(res.storeIR).toBeDefined();

      const ir = res.storeIR!;
      expect(ir.storeName).toBe('useCartStore');
      expect(ir.sourceFramework).toBe('zustand');
      expect(ir.stateFields.some((f) => f.name === 'totalPrice')).toBe(true);
      expect(ir.mutations.some((m) => m.name === 'clearCart')).toBe(true);
      expect(ir.actions.some((a) => a.name === 'checkout')).toBe(true);
      expect(ir.persistence).toBeDefined();
      expect(ir.persistence?.storageKey).toBe('cart-storage');
    });

    it('should emit valid Zustand store TypeScript code from UniversalStoreIR', () => {
      const parseRes = zustandAdapter.parse(sampleZustandCode, 'cart');
      const emitRes = zustandAdapter.emit(parseRes.storeIR!);

      expect(emitRes.framework).toBe('zustand');
      expect(emitRes.code).toContain('create<UseCartStoreState>');
      expect(emitRes.code).toContain('persist(');
      expect(emitRes.code).toContain('cart-storage');
    });
  });

  describe('Redux Toolkit Adapter', () => {
    it('should parse Redux Toolkit slice, reducers, and async thunks', () => {
      const res = rtkAdapter.parse(sampleRTKCode, 'user');
      expect(res.success).toBe(true);
      expect(res.storeIR).toBeDefined();

      const ir = res.storeIR!;
      expect(ir.storeName).toBe('user');
      expect(ir.sourceFramework).toBe('redux-toolkit');
      expect(ir.stateFields.some((f) => f.name === 'isLoggedIn')).toBe(true);
      expect(ir.mutations.some((m) => m.name === 'setLoggedIn')).toBe(true);
      expect(ir.actions.some((a) => a.name === 'fetchUser')).toBe(true);
    });

    it('should emit Redux Toolkit slice code from UniversalStoreIR', () => {
      const parseRes = rtkAdapter.parse(sampleRTKCode, 'user');
      const emitRes = rtkAdapter.emit(parseRes.storeIR!);

      expect(emitRes.framework).toBe('redux-toolkit');
      expect(emitRes.code).toContain('createSlice');
      expect(emitRes.code).toContain('createAsyncThunk');
      expect(emitRes.code).toContain('userSlice.reducer');
    });
  });

  describe('Pinia Adapter', () => {
    it('should parse Pinia Setup Store with refs, computeds, and functions', () => {
      const res = piniaAdapter.parse(samplePiniaCode, 'counter');
      expect(res.success).toBe(true);
      expect(res.storeIR).toBeDefined();

      const ir = res.storeIR!;
      expect(ir.storeId).toBe('counter');
      expect(ir.stateFields.some((f) => f.name === 'count')).toBe(true);
      expect(ir.getters.some((g) => g.name === 'doubleCount')).toBe(true);
      expect(ir.mutations.some((m) => m.name === 'increment')).toBe(true);
      expect(ir.actions.some((a) => a.name === 'resetAsync')).toBe(true);
    });

    it('should emit Pinia Setup Store code from UniversalStoreIR', () => {
      const parseRes = piniaAdapter.parse(samplePiniaCode, 'counter');
      const emitRes = piniaAdapter.emit(parseRes.storeIR!);

      expect(emitRes.framework).toBe('pinia');
      expect(emitRes.code).toContain("defineStore('counter'");
      expect(emitRes.code).toContain('ref<');
      expect(emitRes.code).toContain('computed(');
    });
  });

  describe('MiniApp Store Adapter', () => {
    it('should emit WeChat MiniApp Observable singleton store with storage sync', () => {
      const parseRes = zustandAdapter.parse(sampleZustandCode, 'cart');
      const emitRes = miniappAdapter.emit(parseRes.storeIR!);

      expect(emitRes.framework).toBe('miniapp-store');
      expect(emitRes.code).toContain('class UseCartStoreStore');
      expect(emitRes.code).toContain('wx.getStorageSync');
      expect(emitRes.code).toContain('wx.setStorageSync');
      expect(emitRes.code).toContain('connect(pageOrComponent');
    });
  });

  describe('CrossPlatformStoreLowerer End-to-End', () => {
    it('should transform Zustand store into Pinia store', () => {
      const result = lowerer.transform(sampleZustandCode, 'zustand', 'pinia', 'cart');
      expect(result.emitResult.framework).toBe('pinia');
      expect(result.emitResult.code).toContain('defineStore');
      expect(result.plan.steps.length).toBeGreaterThan(0);
    });

    it('should transform Pinia store into Redux Toolkit slice', () => {
      const result = lowerer.transform(samplePiniaCode, 'pinia', 'redux-toolkit', 'counter');
      expect(result.emitResult.framework).toBe('redux-toolkit');
      expect(result.emitResult.code).toContain('createSlice');
    });

    it('should transform Redux Toolkit slice into WeChat MiniApp store', () => {
      const result = lowerer.transform(sampleRTKCode, 'redux-toolkit', 'miniapp-store', 'user');
      expect(result.emitResult.framework).toBe('miniapp-store');
      expect(result.emitResult.code).toContain('UserStore.getInstance()');
    });
  });
});
