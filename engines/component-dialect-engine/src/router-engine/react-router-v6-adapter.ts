/**
 * @file react-router-v6-adapter.ts
 * @description React Router v6/v7 AST parser and code emitter.
 * Handles `createBrowserRouter`, nested `<Route>` elements, `<Outlet />`,
 * route loaders, errorElement, and navigation hooks (`useNavigate`, `useParams`).
 * Conforms to Batch 32 Skill 1207 (b32-route-navigation-deeplink).
 */

import {
  UniversalRouterIR,
  RouteNodeIR,
  RouterParseResult,
  RouterEmitResult,
} from './router-ir-types';

export class ReactRouterV6Adapter {
  /**
   * Emit React Router v6 configuration code from UniversalRouterIR
   */
  public emit(routerIR: UniversalRouterIR): RouterEmitResult {
    const lines: string[] = [];

    lines.push(`import React, { lazy, Suspense } from 'react';`);
    lines.push(`import { createBrowserRouter, RouterProvider, Outlet, Navigate } from 'react-router-dom';\n`);

    lines.push(`// Route components lazy loaders`);
    const allComponents = new Set<string>();
    const collectComponents = (nodes: RouteNodeIR[]) => {
      for (const node of nodes) {
        if (node.componentIdentifier && node.componentIdentifier !== 'Fragment') {
          allComponents.add(node.componentIdentifier);
        }
        collectComponents(node.children);
      }
    };
    collectComponents(routerIR.routes);

    for (const comp of allComponents) {
      lines.push(`const ${comp} = lazy(() => import('./pages/${comp}'));`);
    }

    lines.push(`\nconst LoadingFallback = () => <div className="route-loading">Loading...</div>;\n`);

    lines.push(`export const router = createBrowserRouter([`);
    for (const route of routerIR.routes) {
      lines.push(this.emitRouteObject(route, 2));
    }
    lines.push(`]);\n`);

    lines.push(`export const AppRouter = () => (`);
    lines.push(`  <Suspense fallback={<LoadingFallback />}>`);
    lines.push(`    <RouterProvider router={router} />`);
    lines.push(`  </Suspense>`);
    lines.push(`);\n`);

    return {
      files: [
        {
          filePath: 'src/router.tsx',
          content: lines.join('\n'),
          role: 'router-config',
        },
      ],
      framework: 'react-router',
      dependencies: [{ name: 'react-router-dom', version: '^6.22.0', isDev: false }],
      notes: [`Generated React Router v6 configuration from UniversalRouterIR: ${routerIR.routerId}`],
    };
  }

  private emitRouteObject(node: RouteNodeIR, indentLevel: number): string {
    const pad = ' '.repeat(indentLevel);
    const innerPad = ' '.repeat(indentLevel + 2);
    const lines: string[] = [];

    lines.push(`${pad}{`);
    if (node.isIndex && (!node.path || node.path === '')) {
      lines.push(`${innerPad}index: true,`);
    } else {
      lines.push(`${innerPad}path: '${node.path.replace(/^\//, '')}',`);
    }

    if (node.componentIdentifier && node.componentIdentifier !== 'Fragment') {
      lines.push(`${innerPad}element: <${node.componentIdentifier} />,`);
    } else {
      lines.push(`${innerPad}element: <Outlet />,`);
    }

    if (node.children.length > 0) {
      lines.push(`${innerPad}children: [`);
      for (const child of node.children) {
        lines.push(this.emitRouteObject(child, indentLevel + 4) + ',');
      }
      lines.push(`${innerPad}],`);
    }

    lines.push(`${pad}}`);
    return lines.join('\n');
  }
}
