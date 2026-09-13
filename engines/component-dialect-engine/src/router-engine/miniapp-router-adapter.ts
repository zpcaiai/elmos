/**
 * @file miniapp-router-adapter.ts
 * @description WeChat MiniApp routing configuration and navigation helper generator.
 * Emits `app.json` page declarations, subpackages, and typed navigation wrapper utilities
 * (`wx.navigateTo`, `wx.redirectTo`, `wx.switchTab`, query param serialization).
 * Conforms to Batch 32 Skill 1207 (b32-route-navigation-deeplink).
 */

import {
  UniversalRouterIR,
  RouteNodeIR,
  RouterEmitResult,
} from './router-ir-types';

export class MiniAppRouterAdapter {
  /**
   * Emit MiniApp `app.json` routing configuration and navigation helper utility from UniversalRouterIR
   */
  public emit(routerIR: UniversalRouterIR): RouterEmitResult {
    const pages: string[] = [];
    const pathMapping: Record<string, string> = {};

    const collectPages = (nodes: RouteNodeIR[]) => {
      for (const node of nodes) {
        if (node.isIndex || node.children.length === 0) {
          const miniAppPage = this.formatMiniAppPagePath(node.fullPath);
          if (!pages.includes(miniAppPage)) {
            pages.push(miniAppPage);
            pathMapping[node.fullPath] = `/${miniAppPage}`;
          }
        }
        collectPages(node.children);
      }
    };

    collectPages(routerIR.routes);

    // MiniApp app.json config snippet
    const appJsonConfig = {
      pages,
      window: {
        backgroundTextStyle: 'light',
        navigationBarBackgroundColor: '#fff',
        navigationBarTitleText: 'MiniApp',
        navigationBarTextStyle: 'black',
      },
    };

    // MiniApp typed navigation helper TypeScript code
    const helperLines: string[] = [];
    helperLines.push(`/**`);
    helperLines.push(` * MiniApp Cross-Platform Navigation Router Utility`);
    helperLines.push(` */\n`);
    helperLines.push(`export const ROUTE_PATH_MAP: Record<string, string> = ${JSON.stringify(pathMapping, null, 2)};\n`);

    helperLines.push(`export interface NavigationOptions {`);
    helperLines.push(`  params?: Record<string, string | number | boolean>;`);
    helperLines.push(`  events?: Record<string, Function>;`);
    helperLines.push(`}\n`);

    helperLines.push(`export class MiniAppNavigator {`);
    helperLines.push(`  public static navigate(webPath: string, options?: NavigationOptions): Promise<any> {`);
    helperLines.push(`    const targetPath = ROUTE_PATH_MAP[webPath] || webPath;`);
    helperLines.push(`    const queryString = options?.params ? '?' + this.buildQuery(options.params) : '';`);
    helperLines.push(`    return new Promise((resolve, reject) => {`);
    helperLines.push(`      wx.navigateTo({`);
    helperLines.push(`        url: targetPath + queryString,`);
    helperLines.push(`        events: options?.events,`);
    helperLines.push(`        success: resolve,`);
    helperLines.push(`        fail: (err) => {`);
    helperLines.push(`          // Fallback to switchTab if page is in tabBar`);
    helperLines.push(`          wx.switchTab({`);
    helperLines.push(`            url: targetPath,`);
    helperLines.push(`            success: resolve,`);
    helperLines.push(`            fail: () => reject(err),`);
    helperLines.push(`          });`);
    helperLines.push(`        },`);
    helperLines.push(`      });`);
    helperLines.push(`    });`);
    helperLines.push(`  }\n`);

    helperLines.push(`  public static redirect(webPath: string, params?: Record<string, string | number | boolean>): Promise<any> {`);
    helperLines.push(`    const targetPath = ROUTE_PATH_MAP[webPath] || webPath;`);
    helperLines.push(`    const queryString = params ? '?' + this.buildQuery(params) : '';`);
    helperLines.push(`    return new Promise((resolve, reject) => {`);
    helperLines.push(`      wx.redirectTo({`);
    helperLines.push(`        url: targetPath + queryString,`);
    helperLines.push(`        success: resolve,`);
    helperLines.push(`        fail: reject,`);
    helperLines.push(`      });`);
    helperLines.push(`    });`);
    helperLines.push(`  }\n`);

    helperLines.push(`  public static back(delta: number = 1): Promise<any> {`);
    helperLines.push(`    return new Promise((resolve, reject) => {`);
    helperLines.push(`      wx.navigateBack({ delta, success: resolve, fail: reject });`);
    helperLines.push(`    });`);
    helperLines.push(`  }\n`);

    helperLines.push(`  private static buildQuery(params: Record<string, string | number | boolean>): string {`);
    helperLines.push(`    return Object.entries(params)`);
    helperLines.push(`      .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(String(v)))`);
    helperLines.push(`      .join('&');`);
    helperLines.push(`  }`);
    helperLines.push(`}\n`);

    return {
      files: [
        {
          filePath: 'app.json',
          content: JSON.stringify(appJsonConfig, null, 2),
          role: 'router-config',
        },
        {
          filePath: 'utils/navigator.ts',
          content: helperLines.join('\n'),
          role: 'navigation-hook',
        },
      ],
      framework: 'miniapp-router',
      dependencies: [],
      notes: [`Generated WeChat MiniApp app.json routes and navigator from UniversalRouterIR: ${routerIR.routerId}`],
    };
  }

  private formatMiniAppPagePath(webPath: string): string {
    const clean = webPath.replace(/^\/+/, '').replace(/:[a-zA-Z0-9_-]+/g, 'detail');
    if (!clean || clean === '') {
      return 'pages/index/index';
    }
    const parts = clean.split('/');
    if (parts.length === 1) {
      return `pages/${parts[0]}/index`;
    }
    return `pages/${parts.join('/')}`;
  }
}
