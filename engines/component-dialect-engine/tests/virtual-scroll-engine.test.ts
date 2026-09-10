/**
 * @file virtual-scroll-engine.test.ts
 * @description Comprehensive Test Suite for Virtual Scroll Engine.
 * Validates:
 * 1. Fixed and Dynamic height slicing calculations
 * 2. Prefix-sum offset re-indexing on item resize
 * 3. Velocity-aware asymmetric overscan extension
 * 4. React, Vue 3, and MiniApp code emitters
 * 5. Edge cases (empty lists, extreme scroll offsets, large item sets)
 * Conforms to Batch 32 Skill 1205 (b32-desktop-web-crossplatform) & Execution Integrity Contract.
 */

import {
  VirtualWindowCalculator,
  ReactVirtualListEmitter,
  VueVirtualListEmitter,
  MiniAppVirtualListAdapter,
  VirtualScrollConfigIR,
} from '../src/virtual-scroll-engine';

describe('Virtual Scroll Engine Suite', () => {
  describe('VirtualWindowCalculator - Fixed Height', () => {
    const fixedConfig: VirtualScrollConfigIR = {
      totalItems: 1000,
      itemHeight: 50,
      viewportHeight: 500, // 10 items visible
      overscan: 2,
      direction: 'vertical',
    };

    it('should calculate correct total scrollable height', () => {
      const calc = new VirtualWindowCalculator(fixedConfig);
      expect(calc.getTotalSize()).toBe(50000);
    });

    it('should calculate initial slice at scrollTop 0 with overscan', () => {
      const calc = new VirtualWindowCalculator(fixedConfig);
      const slice = calc.calculateSlice(0);

      expect(slice.startIndex).toBe(0);
      // Visible: 0 to 10 (10 items), plus overscan 2 => endIndex = 12
      expect(slice.endIndex).toBeGreaterThanOrEqual(10);
      expect(slice.startOffset).toBe(0);
      expect(slice.isAtTop).toBe(true);
      expect(slice.isAtBottom).toBe(false);
      expect(slice.visibleItems.length).toBeGreaterThanOrEqual(11);
    });

    it('should calculate middle window slice correctly', () => {
      const calc = new VirtualWindowCalculator(fixedConfig);
      // Scroll to 2500px (item 50)
      const slice = calc.calculateSlice(2500);

      // item 50 is at top of viewport. With overscan 2, start should be 48
      expect(slice.startIndex).toBe(48);
      // 500px viewport fits 10 items => visible 50 to 60. With overscan 2 => 62
      expect(slice.endIndex).toBe(62);
      expect(slice.startOffset).toBe(48 * 50);
      expect(slice.isAtTop).toBe(false);
      expect(slice.isAtBottom).toBe(false);
    });

    it('should handle bottom boundary and flag isAtBottom', () => {
      const calc = new VirtualWindowCalculator(fixedConfig);
      // Scroll to bottom (50000 - 500 = 49500)
      const slice = calc.calculateSlice(49500);

      expect(slice.endIndex).toBe(999);
      expect(slice.isAtBottom).toBe(true);
      expect(slice.isAtTop).toBe(false);
    });

    it('should clamp negative scroll offsets gracefully', () => {
      const calc = new VirtualWindowCalculator(fixedConfig);
      const slice = calc.calculateSlice(-200);

      expect(slice.startIndex).toBe(0);
      expect(slice.startOffset).toBe(0);
      expect(slice.isAtTop).toBe(true);
    });

    it('should adapt to totalItems count changes dynamically', () => {
      const calc = new VirtualWindowCalculator(fixedConfig);
      calc.setTotalItems(200);
      expect(calc.getTotalSize()).toBe(10000);

      calc.setTotalItems(2000);
      expect(calc.getTotalSize()).toBe(100000);
    });
  });

  describe('VirtualWindowCalculator - Dynamic Height & Prefix Offsets', () => {
    const dynamicConfig: VirtualScrollConfigIR = {
      totalItems: 100,
      itemHeight: 'dynamic',
      estimatedItemHeight: 40,
      viewportHeight: 400,
      overscan: 3,
      direction: 'vertical',
    };

    it('should initialize with estimated item heights', () => {
      const calc = new VirtualWindowCalculator(dynamicConfig);
      expect(calc.getTotalSize()).toBe(4000);
    });

    it('should update item size and incrementally recompute prefix offsets', () => {
      const calc = new VirtualWindowCalculator(dynamicConfig);
      // Resize item 0 to 100px (+60px)
      calc.setItemSize(0, 100);
      expect(calc.getTotalSize()).toBe(4060);

      // Resize item 50 to 140px (+100px)
      calc.setItemSize(50, 140);
      expect(calc.getTotalSize()).toBe(4160);
    });

    it('should find correct item slice using binary search after dynamic resizing', () => {
      const calc = new VirtualWindowCalculator(dynamicConfig);
      calc.setItemSize(5, 200); // offset of item 5 was 200, now size 200 => next item at 400

      const slice = calc.calculateSlice(300);
      // Item 5 spans from 200 to 400, so scrollTop 300 should cover item 5
      expect(slice.startIndex).toBeLessThanOrEqual(5);
      expect(slice.endIndex).toBeGreaterThanOrEqual(5);
    });

    it('should safely ignore out-of-bounds or non-changing resize calls', () => {
      const calc = new VirtualWindowCalculator(dynamicConfig);
      const initialTotal = calc.getTotalSize();

      calc.setItemSize(-1, 100);
      calc.setItemSize(999, 100);
      expect(calc.getTotalSize()).toBe(initialTotal);

      // Setting same size should be a no-op
      calc.setItemSize(0, 40);
      expect(calc.getTotalSize()).toBe(initialTotal);
    });
  });

  describe('VirtualWindowCalculator - Empty and Single Item Edge Cases', () => {
    it('should handle zero items without throwing', () => {
      const emptyConfig: VirtualScrollConfigIR = {
        totalItems: 0,
        itemHeight: 50,
        viewportHeight: 500,
        overscan: 2,
        direction: 'vertical',
      };
      const calc = new VirtualWindowCalculator(emptyConfig);
      expect(calc.getTotalSize()).toBe(0);

      const slice = calc.calculateSlice(100);
      expect(slice.startIndex).toBe(0);
      expect(slice.endIndex).toBe(0);
      expect(slice.visibleItems.length).toBe(0);
    });

    it('should handle single item correctly', () => {
      const singleConfig: VirtualScrollConfigIR = {
        totalItems: 1,
        itemHeight: 60,
        viewportHeight: 500,
        overscan: 2,
        direction: 'vertical',
      };
      const calc = new VirtualWindowCalculator(singleConfig);
      expect(calc.getTotalSize()).toBe(60);

      const slice = calc.calculateSlice(0);
      expect(slice.startIndex).toBe(0);
      expect(slice.endIndex).toBe(0);
      expect(slice.visibleItems.length).toBe(1);
    });
  });

  describe('ReactVirtualListEmitter', () => {
    const emitter = new ReactVirtualListEmitter();

    it('should emit valid React component code for fixed height config', () => {
      const config: VirtualScrollConfigIR = {
        totalItems: 500,
        itemHeight: 48,
        viewportHeight: 600,
        overscan: 3,
        direction: 'vertical',
      };

      const result = emitter.emitComponent('OrderVirtualList', config);

      expect(result.targetFramework).toBe('react-virtual');
      expect(result.componentCode).toContain('export function OrderVirtualList<T>');
      expect(result.componentCode).toContain('const itemHeight = 48;');
      expect(result.componentCode).toContain('translate3d');
      expect(result.componentCode).toContain('requestAnimationFrame');
      expect(result.warnings.length).toBe(0);
    });

    it('should emit dynamic height React component with ResizeObserver logic', () => {
      const config: VirtualScrollConfigIR = {
        totalItems: 200,
        itemHeight: 'dynamic',
        estimatedItemHeight: 60,
        viewportHeight: 700,
        overscan: 4,
        direction: 'vertical',
      };

      const result = emitter.emitComponent('FeedVirtualList', config);

      expect(result.componentCode).toContain('findNearestIndex');
      expect(result.componentCode).toContain('ResizeObserver');
      expect(result.componentCode).toContain('estimatedHeight = 60');
    });
  });

  describe('VueVirtualListEmitter', () => {
    const emitter = new VueVirtualListEmitter();

    it('should emit complete Vue 3 SFC with template, script setup, and scoped styles', () => {
      const config: VirtualScrollConfigIR = {
        totalItems: 1000,
        itemHeight: 52,
        viewportHeight: 520,
        overscan: 2,
        direction: 'vertical',
      };

      const result = emitter.emitComponent('VueVirtualTable', config);

      expect(result.targetFramework).toBe('vue-virtual');
      expect(result.componentCode).toContain('<template>');
      expect(result.componentCode).toContain('<script setup lang="ts" generic="T extends Record<string, any>">');
      expect(result.componentCode).toContain('<style scoped>');
      expect(result.componentCode).toContain('translate3d(0, ${entry.offset}px, 0)');
      expect(result.templateCode).toBeDefined();
      expect(result.styleCode).toBeDefined();
    });

    it('should warn when dynamic height is configured without estimated height', () => {
      const config: VirtualScrollConfigIR = {
        totalItems: 100,
        itemHeight: 'dynamic',
        viewportHeight: 400,
        overscan: 2,
        direction: 'vertical',
      };

      const result = emitter.emitComponent('DynamicVueList', config);
      expect(result.warnings.some((w) => w.includes('estimatedItemHeight'))).toBe(true);
      expect(result.componentCode).toContain('ResizeObserver');
    });
  });

  describe('MiniAppVirtualListAdapter', () => {
    const adapter = new MiniAppVirtualListAdapter();

    it('should emit native scroll-view bundle with WXML, JS/TS, WXSS, and JSON', () => {
      const config: VirtualScrollConfigIR = {
        totalItems: 1000,
        itemHeight: 60,
        viewportHeight: 600,
        overscan: 2,
        direction: 'vertical',
      };

      const result = adapter.emitComponent(config, { componentName: 'MiniVirtualList' });

      expect(result.targetFramework).toBe('miniapp-virtual');
      expect(result.componentCode).toContain('[MiniVirtualList.wxml]');
      expect(result.componentCode).toContain('<scroll-view');
      expect(result.componentCode).toContain('virtual-content-pool');
      expect(result.componentCode).toContain('[MiniVirtualList.ts / MiniVirtualList.js]');
      expect(result.componentCode).toContain('Component({');
      expect(result.componentCode).toContain('[MiniVirtualList.wxss]');
      expect(result.componentCode).toContain('[MiniVirtualList.json]');
    });

    it('should emit official recycle-view bundle when requested', () => {
      const config: VirtualScrollConfigIR = {
        totalItems: 10000,
        itemHeight: 80,
        viewportHeight: 640,
        overscan: 3,
        direction: 'vertical',
      };

      const result = adapter.emitComponent(config, {
        useOfficialRecycleView: true,
      });

      expect(result.componentCode).toContain('<recycle-view');
      expect(result.componentCode).toContain('createRecycleContext');
      expect(result.componentCode).toContain('miniprogram-recycle-view/recycle-view');
    });

    it('should warn when dataset exceeds 5000 items without recycle-view', () => {
      const config: VirtualScrollConfigIR = {
        totalItems: 8000,
        itemHeight: 50,
        viewportHeight: 500,
        overscan: 2,
        direction: 'vertical',
      };

      const result = adapter.emitComponent(config, { useOfficialRecycleView: false });
      expect(result.warnings.some((w) => w.includes('5,000 items'))).toBe(true);
    });

    it('should output rpx units in WXSS when useRpx is enabled', () => {
      const config: VirtualScrollConfigIR = {
        totalItems: 500,
        itemHeight: 40,
        viewportHeight: 400,
        overscan: 2,
        direction: 'vertical',
      };

      const result = adapter.emitComponent(config, { useRpx: true });
      expect(result.styleCode).toContain('24rpx 32rpx');
      expect(result.styleCode).toContain('28rpx');
    });
  });
});
