/**
 * @file cross-platform-router-engine.test.ts
 * @description Comprehensive Jest test suite for the Cross-Platform Router Engine (Skill 1207).
 * Tests Next.js App Router, React Router v6, Vue Router 4, and MiniApp navigation translation.
 * Conforms to Batch 32 Skill 1207 (b32-route-navigation-deeplink).
 */

import { CrossPlatformRouterEngine } from '../src/router-engine/cross-platform-router-engine';
import { NextJsAppRouterAdapter } from '../src/router-engine/nextjs-app-router-adapter';
import { ReactRouterV6Adapter } from '../src/router-engine/react-router-v6-adapter';
import { VueRouter4Adapter } from '../src/router-engine/vue-router-4-adapter';
import { MiniAppRouterAdapter } from '../src/router-engine/miniapp-router-adapter';

describe('Cross-Platform Router Engine (Skill 1207)', () => {
  const routerEngine = new CrossPlatformRouterEngine();
  const nextAdapter = new NextJsAppRouterAdapter();
  const reactRouterAdapter = new ReactRouterV6Adapter();
  const vueRouterAdapter = new VueRouter4Adapter();
  const miniappAdapter = new MiniAppRouterAdapter();

  const sampleNextJsAppFiles = [
    'app/page.tsx',
    'app/dashboard/page.tsx',
    'app/dashboard/analytics/page.tsx',
    'app/users/[id]/page.tsx',
    'app/docs/[...slug]/page.tsx',
    'app/(auth)/login/page.tsx',
    'app/(auth)/register/page.tsx',
  ];

  it('should parse Next.js App Router filesystem structure into UniversalRouterIR', () => {
    const res = nextAdapter.parseFilePaths(sampleNextJsAppFiles, 'web-app');
    expect(res.success).toBe(true);
    expect(res.routerIR).toBeDefined();

    const ir = res.routerIR!;
    expect(ir.sourceFramework).toBe('nextjs-app-router');
    expect(ir.routes.length).toBeGreaterThan(0);

    // Root page
    expect(ir.routes.some((r) => r.isIndex)).toBe(true);

    // Dynamic segments
    const usersRoute = ir.routes.find((r) => r.path === 'users' || r.id === 'users');
    expect(usersRoute).toBeDefined();
    expect(usersRoute?.children.length).toBeGreaterThan(0);
    expect(usersRoute?.children[0]?.segmentKind).toBe('dynamic');
    expect(usersRoute?.children[0]?.params[0]?.name).toBe('id');
  });

  it('should emit Next.js App Router file tree from UniversalRouterIR', () => {
    const parseRes = nextAdapter.parseFilePaths(sampleNextJsAppFiles, 'web-app');
    const emitRes = nextAdapter.emit(parseRes.routerIR!);

    expect(emitRes.framework).toBe('nextjs-app-router');
    expect(emitRes.files.some((f) => f.filePath === 'app/layout.tsx')).toBe(true);
    expect(emitRes.files.some((f) => f.filePath.endsWith('page.tsx'))).toBe(true);
  });

  it('should emit React Router v6 configuration from UniversalRouterIR', () => {
    const parseRes = nextAdapter.parseFilePaths(sampleNextJsAppFiles, 'web-app');
    const emitRes = reactRouterAdapter.emit(parseRes.routerIR!);

    expect(emitRes.framework).toBe('react-router');
    const configFile = emitRes.files.find((f) => f.filePath === 'src/router.tsx');
    expect(configFile).toBeDefined();
    expect(configFile?.content).toContain('createBrowserRouter');
    expect(configFile?.content).toContain('RouterProvider');
    expect(configFile?.content).toContain('lazy(');
  });

  it('should emit Vue Router 4 configuration with navigation guards from UniversalRouterIR', () => {
    const parseRes = nextAdapter.parseFilePaths(sampleNextJsAppFiles, 'web-app');
    const emitRes = vueRouterAdapter.emit(parseRes.routerIR!);

    expect(emitRes.framework).toBe('vue-router');
    const configFile = emitRes.files.find((f) => f.filePath === 'src/router/index.ts');
    expect(configFile).toBeDefined();
    expect(configFile?.content).toContain('createRouter');
    expect(configFile?.content).toContain('createWebHistory');
    expect(configFile?.content).toContain('router.beforeEach');
  });

  it('should emit WeChat MiniApp app.json and typed navigator utility from UniversalRouterIR', () => {
    const parseRes = nextAdapter.parseFilePaths(sampleNextJsAppFiles, 'web-app');
    const emitRes = miniappAdapter.emit(parseRes.routerIR!);

    expect(emitRes.framework).toBe('miniapp-router');
    const appJsonFile = emitRes.files.find((f) => f.filePath === 'app.json');
    expect(appJsonFile).toBeDefined();

    const appJson = JSON.parse(appJsonFile!.content);
    expect(appJson.pages).toBeDefined();
    expect(appJson.pages.length).toBeGreaterThan(0);
    expect(appJson.pages).toContain('pages/index/index');

    const navFile = emitRes.files.find((f) => f.filePath === 'utils/navigator.ts');
    expect(navFile).toBeDefined();
    expect(navFile?.content).toContain('class MiniAppNavigator');
    expect(navFile?.content).toContain('wx.navigateTo');
  });

  it('should perform end-to-end migration from Next.js to MiniApp via CrossPlatformRouterEngine', () => {
    const emitRes = routerEngine.migrateFromNextJs(sampleNextJsAppFiles, 'miniapp-router', 'store-app');
    expect(emitRes.framework).toBe('miniapp-router');
    expect(emitRes.files.length).toBe(2);
  });
});
