/**
 * @file cross-platform-router-engine.ts
 * @description Cross-Platform Routing & Navigation Migration Engine.
 * Converts routes between Next.js App Router, React Router, Vue Router 4, and MiniApp.
 * Conforms to Batch 32 Skill 1207 (b32-route-navigation-deeplink).
 */

import {
  UniversalRouterIR,
  RouteFramework,
  RouterEmitResult,
} from './router-ir-types';
import { NextJsAppRouterAdapter } from './nextjs-app-router-adapter';
import { ReactRouterV6Adapter } from './react-router-v6-adapter';
import { VueRouter4Adapter } from './vue-router-4-adapter';
import { MiniAppRouterAdapter } from './miniapp-router-adapter';

export class CrossPlatformRouterEngine {
  private nextAdapter = new NextJsAppRouterAdapter();
  private reactRouterAdapter = new ReactRouterV6Adapter();
  private vueRouterAdapter = new VueRouter4Adapter();
  private miniappRouterAdapter = new MiniAppRouterAdapter();

  /**
   * Ingest Next.js file structure into UniversalRouterIR
   */
  public parseNextJsAppRouter(filePaths: string[], routerId?: string): UniversalRouterIR {
    const res = this.nextAdapter.parseFilePaths(filePaths, routerId);
    if (!res.success || !res.routerIR) {
      throw new Error(`Failed to parse Next.js routes: ${res.errors.join(', ')}`);
    }
    return res.routerIR;
  }

  /**
   * Emit target routing code
   */
  public emit(routerIR: UniversalRouterIR, targetFramework: RouteFramework): RouterEmitResult {
    switch (targetFramework) {
      case 'nextjs-app-router':
        return this.nextAdapter.emit(routerIR);
      case 'react-router':
        return this.reactRouterAdapter.emit(routerIR);
      case 'vue-router':
        return this.vueRouterAdapter.emit(routerIR);
      case 'miniapp-router':
        return this.miniappRouterAdapter.emit(routerIR);
      default:
        throw new Error(`Unsupported route target framework: ${targetFramework}`);
    }
  }

  /**
   * Migrate Next.js App Router file paths to target framework
   */
  public migrateFromNextJs(filePaths: string[], targetFramework: RouteFramework, routerId?: string): RouterEmitResult {
    const routerIR = this.parseNextJsAppRouter(filePaths, routerId);
    return this.emit(routerIR, targetFramework);
  }
}
