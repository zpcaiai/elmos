/**
 * @file hydration-engine.test.ts
 * @description Comprehensive unit test suite for Progressive Hydration and Micro-Frontend Engine.
 * Tests IslandArchitectureCompiler (partial hydration, client-only/idle/visible strategies),
 * HydrationMismatchRepairOracle (SSR vs CSR mismatch classification and automated repair advice),
 * and CrossPlatformMicroFrontendBridge (W3C Custom Element wrapping for React and Vue).
 * Conforms to Batch 32 Skill 1213.
 */

import {
  IslandArchitectureCompiler,
  HydrationMismatchRepairOracle,
  CrossPlatformMicroFrontendBridge,
  HydrationBoundaryIR,
} from '../src/hydration-engine';

describe('Hydration & Micro-Frontend Engine', () => {
  describe('IslandArchitectureCompiler', () => {
    const compiler = new IslandArchitectureCompiler();

    it('should compile HTML shell with island markers and client script loader', () => {
      const htmlBody = `
        <header>Static Header</header>
        <main>
          <!-- ELMOS_ISLAND:island_cart -->
          <article>Static Article Content</article>
          <!-- ELMOS_ISLAND:island_reviews -->
        </main>
      `;

      const islands: HydrationBoundaryIR[] = [
        {
          id: 'island_cart',
          componentName: 'ShoppingCart',
          entryFilePath: '/islands/ShoppingCart.js',
          strategy: 'client:load',
          priority: 1,
          props: { initialCount: 2 },
        },
        {
          id: 'island_reviews',
          componentName: 'ProductReviews',
          entryFilePath: '/islands/ProductReviews.js',
          strategy: 'client:visible',
          priority: 5,
          props: { productId: 42 },
        },
      ];

      const ir = compiler.compile('doc_product_page', htmlBody, islands);
      expect(ir.documentId).toBe('doc_product_page');
      expect(ir.islands.length).toBe(2);
      expect(ir.preloadLinks).toContain('/islands/ShoppingCart.js');
      expect(ir.preloadLinks).toContain('/islands/ProductReviews.js');

      // Check replaced island elements in static HTML shell
      expect(ir.staticHtmlShell).toContain('component-name="ShoppingCart"');
      expect(ir.staticHtmlShell).toContain('strategy="client:load"');
      expect(ir.staticHtmlShell).toContain('component-name="ProductReviews"');
      expect(ir.staticHtmlShell).toContain('strategy="client:visible"');

      // Check client script loader code
      expect(ir.scriptLoaderBundle).toContain('IntersectionObserver');
      expect(ir.scriptLoaderBundle).toContain('client:visible');
      expect(ir.scriptLoaderBundle).toContain('client:idle');
    });

    it('should generate client script loader handling streaming hydration and visibility triggers', () => {
      const islands: HydrationBoundaryIR[] = [
        {
          id: 'island_rec',
          componentName: 'RecommendedItems',
          entryFilePath: '/islands/RecommendedItems.js',
          strategy: 'client:idle',
          priority: 8,
          props: {},
        },
      ];

      const script = compiler.generateClientScriptLoader(islands);
      expect(script).toContain('requestIdleCallback');
      expect(script).toContain('elmos-island');
    });
  });

  describe('HydrationMismatchRepairOracle', () => {
    const oracle = new HydrationMismatchRepairOracle();

    it('should diagnose timestamp drift mismatch between server and client', () => {
      const result = oracle.diagnose(
        'div.timestamp',
        '2026-09-10 12:00:00 UTC',
        '2026-09-10 20:00:00 GMT+8'
      );

      expect(result.kind).toBe('timestamp-drift');
      expect(result.isFatal).toBe(false);
      expect(result.suggestedRepair).toBe('move-to-useEffect');
      expect(result.explanation).toContain('Timestamp formatted on server');
    });

    it('should diagnose random ID divergence', () => {
      const result = oracle.diagnose(
        'input#form_elem',
        'input_id_a8f921',
        'input_id_b4e109'
      );

      expect(result.kind).toBe('random-id-mismatch');
      expect(result.isFatal).toBe(false);
      expect(result.suggestedRepair).toBe('replace-with-stable-seed');
      expect(result.explanation).toContain('useId()');
    });

    it('should diagnose client-only node missing on server', () => {
      const result = oracle.diagnose(
        'div.local-storage-greeting',
        '',
        'Welcome back, Steve!'
      );

      expect(result.kind).toBe('client-only-node-missing');
      expect(result.isFatal).toBe(true);
      expect(result.suggestedRepair).toBe('move-to-useEffect');
      expect(result.explanation).toContain('isMounted');
    });

    it('should diagnose server HTML tag nesting mismatch', () => {
      const result = oracle.diagnose(
        'div.content-wrapper',
        '<div><div>nested</div></div>',
        '<p><div>nested</div></p>'
      );

      expect(result.kind).toBe('server-tag-mismatch');
      expect(result.isFatal).toBe(true);
      expect(result.suggestedRepair).toBe('suppressHydrationWarning');
      expect(result.explanation).toContain('HTML tag divergence');
    });
  });

  describe('CrossPlatformMicroFrontendBridge', () => {
    it('should emit W3C Custom Element wrapper for React micro-frontend', () => {
      const code = CrossPlatformMicroFrontendBridge.emitCustomElementWrapper({
        islandId: 'island_avatar',
        componentName: 'UserAvatar',
        sourceFramework: 'react',
        targetHostFramework: 'custom-elements',
        customTag: 'user-avatar-element',
        observedAttributes: ['user-id', 'size', 'theme'],
        emittedEvents: ['avatarClick', 'avatarLoad'],
      });

      expect(code).toContain('class UserAvatarElement extends HTMLElement');
      expect(code).toContain('observedAttributes');
      expect(code).toContain('"user-id"');
      expect(code).toContain('attachShadow({ mode: \'open\' })');
      expect(code).toContain('ReactDOM.createRoot');
      expect(code).toContain('customElements.define(\'user-avatar-element\', UserAvatarElement);');
    });

    it('should emit W3C Custom Element wrapper for Vue micro-frontend', () => {
      const code = CrossPlatformMicroFrontendBridge.emitCustomElementWrapper({
        islandId: 'island_order_table',
        componentName: 'OrderTable',
        sourceFramework: 'vue',
        targetHostFramework: 'custom-elements',
        customTag: 'order-table-element',
        observedAttributes: ['order-id', 'status'],
        emittedEvents: ['rowSelect'],
      });

      expect(code).toContain('class OrderTableElement extends HTMLElement');
      expect(code).toContain('Vue.createApp');
      expect(code).toContain('customElements.define(\'order-table-element\', OrderTableElement);');
    });
  });
});
