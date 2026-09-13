/**
 * @file enterprise-mfe-and-subpackages.test.ts
 * @description Unit & integration tests for Enterprise Microfrontend Container, Sandbox Isolation,
 * Event Bus, MiniApp Subpackage Optimizer, and Benchmark Corpora.
 */

import {
  ProxySandbox,
  ScopedCssSandbox,
  MicroEventBus,
  EnterpriseMicroFrontendContainerEngine,
  MiniAppSubpackageOptimizer,
  EnterpriseLogisticsWmsCorpus,
  EnterpriseFinancialRetailCorpus,
} from '../src/mfe-container';

describe('Enterprise Microfrontend Container & MiniApp Subpackages (M32)', () => {
  describe('ProxySandbox JS Isolation', () => {
    it('should isolate variable mutations from global window and allow reading/writing inside active sandbox', () => {
      const sandbox = new ProxySandbox('sub-app-logistics');
      sandbox.activeSandbox();

      // Write to proxy window
      sandbox.proxy.token = 'bearer-token-12345';
      sandbox.proxy.userRole = 'LOGISTICS_MANAGER';

      expect(sandbox.proxy.token).toBe('bearer-token-12345');
      expect(sandbox.proxy.userRole).toBe('LOGISTICS_MANAGER');

      const modified = sandbox.getModifiedProperties();
      expect(modified.token).toBe('bearer-token-12345');
      expect(modified.userRole).toBe('LOGISTICS_MANAGER');

      // Verify global scope is NOT polluted
      expect((globalThis as any).token).toBeUndefined();
      expect((globalThis as any).userRole).toBeUndefined();

      // Self/window reference
      expect(sandbox.proxy.window).toBe(sandbox.proxy);
      expect(sandbox.proxy.self).toBe(sandbox.proxy);
      expect(sandbox.proxy.globalThis).toBe(sandbox.proxy);

      // Inactive sandbox prevents writing
      sandbox.inactiveSandbox();
      sandbox.proxy.unauthorizedMutation = 'should_not_set';
      expect(sandbox.proxy.unauthorizedMutation).toBeUndefined();
    });
  });

  describe('ScopedCssSandbox CSS Isolation', () => {
    it('should prefix selectors with container namespace and rewrite root/body', () => {
      const rawCss = `
        .header { background: #fff; }
        .btn, .link { color: blue; }
        body { margin: 0; }
        :root { --main-color: red; }
      `;

      const scoped = ScopedCssSandbox.prefixStyles(rawCss, '#subapp-viewport');
      expect(scoped).toContain('#subapp-viewport .header {');
      expect(scoped).toContain('#subapp-viewport .btn, #subapp-viewport .link {');
      expect(scoped).toContain('#subapp-viewport {'); // body rewritten
    });
  });

  describe('MicroEventBus Cross-App Communication & Leak Disposal', () => {
    it('should dispatch events and dispose listeners upon sub-app teardown', () => {
      const bus = MicroEventBus.getInstance();
      const messages: string[] = [];

      // App A subscribes
      bus.on(
        'ORDER_UPDATED',
        (payload: any) => {
          messages.push(`AppA received order: ${payload.id}`);
        },
        'app-wms'
      );

      // App B subscribes
      bus.on(
        'ORDER_UPDATED',
        (payload: any) => {
          messages.push(`AppB received order: ${payload.id}`);
        },
        'app-finance'
      );

      bus.emit('ORDER_UPDATED', { id: 'ORD-9988' });
      expect(messages).toEqual([
        'AppA received order: ORD-9988',
        'AppB received order: ORD-9988',
      ]);

      // Unmount App A
      bus.destroyAppListeners('app-wms');
      messages.length = 0;

      bus.emit('ORDER_UPDATED', { id: 'ORD-9989' });
      // Only App B should receive it
      expect(messages).toEqual(['AppB received order: ORD-9989']);

      // Cleanup App B
      bus.destroyAppListeners('app-finance');
    });
  });

  describe('EnterpriseMicroFrontendContainerEngine Host Orchestration', () => {
    it('should register, mount and unmount micro applications cleanly', async () => {
      const container = new EnterpriseMicroFrontendContainerEngine();
      container.registerApp({
        name: 'logistics-module',
        entry: '/logistics/index.js',
        container: '#mfe-root',
        activeRule: '/logistics',
      });

      expect(container.getActiveApp()).toBeNull();

      await container.mountApp('logistics-module', { theme: 'dark' });
      expect(container.getActiveApp()).toBe('logistics-module');

      const sandbox = container.getSandbox('logistics-module');
      expect(sandbox).toBeDefined();

      await container.unmountApp('logistics-module');
      expect(container.getActiveApp()).toBeNull();
    });
  });

  describe('MiniAppSubpackageOptimizer Architecture Partitioning', () => {
    it('should analyze page dependencies, extract shared modules, and build subpackages with preload rules', () => {
      const optimizer = new MiniAppSubpackageOptimizer();

      // Main tab bar pages
      optimizer.registerPage({
        path: 'pages/index/index',
        dependencies: ['utils/request.js', 'components/Navbar.vue', 'utils/logger.js'],
        isEntryPage: true,
        isTabBarPage: true,
      });

      optimizer.registerPage({
        path: 'pages/user/profile',
        dependencies: ['utils/request.js', 'components/Navbar.vue'],
        isTabBarPage: true,
      });

      // WMS feature subpackage
      optimizer.registerPage({
        path: 'packageWms/pages/scanner/index',
        dependencies: ['utils/request.js', 'packageWms/components/BleDriver.ts'],
        subpackageHint: 'packageWms',
      });

      optimizer.registerPage({
        path: 'packageWms/pages/signature/index',
        dependencies: ['utils/request.js', 'packageWms/components/CanvasSignature.ts'],
        subpackageHint: 'packageWms',
      });

      // Independent Subpackage for Payment
      optimizer.registerPage({
        path: 'packagePay/pages/checkout/index',
        dependencies: ['packagePay/utils/crypto.js'],
        subpackageHint: 'packagePay',
        isIndependent: true,
      });

      const structure = optimizer.optimize();

      // 1. Shared module extraction (used by >1 page)
      expect(structure.sharedMainPackageModules).toContain('utils/request.js');
      expect(structure.sharedMainPackageModules).toContain('components/Navbar.vue');

      // 2. Main package pages
      expect(structure.mainPackagePages).toContain('pages/index/index');
      expect(structure.mainPackagePages).toContain('pages/user/profile');

      // 3. Subpackages
      expect(structure.subPackages).toHaveLength(2);
      const wmsSub = structure.subPackages.find((s) => s.root === 'packageWms');
      expect(wmsSub).toBeDefined();
      expect(wmsSub?.pages).toEqual(['pages/scanner/index', 'pages/signature/index']);
      expect(wmsSub?.independent).toBe(false);

      const paySub = structure.subPackages.find((s) => s.root === 'packagePay');
      expect(paySub).toBeDefined();
      expect(paySub?.pages).toEqual(['pages/checkout/index']);
      expect(paySub?.independent).toBe(true);

      // 4. Preload rules
      expect(structure.preloadRules['pages/index/index']).toBeDefined();
      expect(structure.preloadRules['pages/index/index']!.packages).toContain('packageWms');

      // 5. app.json snippet
      const appJson = optimizer.generateAppJsonSnippet(structure);
      expect(appJson.pages).toEqual(structure.mainPackagePages);
      expect(appJson.subPackages).toEqual(structure.subPackages);
      expect(appJson.preloadRule).toEqual(structure.preloadRules);
    });
  });

  describe('Enterprise Turnkey Benchmark Corpus Integrity', () => {
    it('should validate EnterpriseLogisticsWmsCorpus components and state declarations', () => {
      expect(EnterpriseLogisticsWmsCorpus.name).toBe('EnterpriseLogisticsWmsMiniApp');
      expect(EnterpriseLogisticsWmsCorpus.components.length).toBeGreaterThanOrEqual(3);

      const scanner = EnterpriseLogisticsWmsCorpus.components.find((c) => c.name === 'WmsParcelScanner');
      expect(scanner).toBeDefined();
      expect(scanner?.sourceCode).toContain('@emotion/styled');
      expect(scanner?.sourceCode).toContain('WMS/START_BLE_SCAN');

      const signature = EnterpriseLogisticsWmsCorpus.components.find((c) => c.name === 'WmsCanvasSignOff');
      expect(signature).toBeDefined();
      expect(signature?.sourceCode).toContain('HTML5 Canvas / MiniApp Canvas 2D');

      const sagas = EnterpriseLogisticsWmsCorpus.components.find((c) => c.name === 'WmsSagaRoot');
      expect(sagas).toBeDefined();
      expect(sagas?.sourceCode).toContain('takeLatest');
      expect(sagas?.sourceCode).toContain('takeEvery');
    });

    it('should validate EnterpriseFinancialRetailCorpus components and WeChat Pay / Pinia declarations', () => {
      expect(EnterpriseFinancialRetailCorpus.name).toBe('EnterpriseFinancialRetailMiniApp');
      expect(EnterpriseFinancialRetailCorpus.components.length).toBeGreaterThanOrEqual(3);

      const cart = EnterpriseFinancialRetailCorpus.components.find((c) => c.name === 'FinancialCartStore');
      expect(cart).toBeDefined();
      expect(cart?.sourceCode).toContain('defineStore');
      expect(cart?.sourceCode).toContain('$onAction');

      const checkout = EnterpriseFinancialRetailCorpus.components.find((c) => c.name === 'RetailCartCheckout');
      expect(checkout).toBeDefined();
      expect(checkout?.sourceCode).toContain('cart.checkoutWithWeChatPay');
      expect(checkout?.sourceCode).toContain('cart.authorizePayScore');

      const mobx = EnterpriseFinancialRetailCorpus.components.find((c) => c.name === 'MobxRealtimeFxWidget');
      expect(mobx).toBeDefined();
      expect(mobx?.sourceCode).toContain('createObservableProxy');
    });
  });
});
