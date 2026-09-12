/**
 * @file nextjs-app-router-adapter.ts
 * @description Next.js 14/15/16 App Router parser and code emitter.
 * Translates Next.js directory-based routing conventions (`app/`, route groups `(auth)`,
 * dynamic segments `[id]`, catch-all segments `[...slug]`, layout, loading, error) into UniversalRouterIR.
 * Conforms to Batch 32 Skill 1207 (b32-route-navigation-deeplink).
 */

import {
  UniversalRouterIR,
  RouteNodeIR,
  RouteSegmentKind,
  RouteParamDescriptor,
  RouterParseResult,
  RouterEmitResult,
} from './router-ir-types';

export class NextJsAppRouterAdapter {
  /**
   * Parse a list of file paths from an `app/` directory into UniversalRouterIR
   */
  public parseFilePaths(filePaths: string[], routerId: string = 'next-app-router'): RouterParseResult {
    const rootRoutes: RouteNodeIR[] = [];
    const errors: string[] = [];
    const warnings: string[] = [];

    // Filter to page files
    const pageFiles = filePaths.filter((p) => p.endsWith('/page.tsx') || p.endsWith('/page.jsx') || p === 'page.tsx');

    for (const filePath of pageFiles) {
      const segments = filePath
        .replace(/^app\//, '')
        .replace(/\/?page\.[jt]sx$/, '')
        .split('/')
        .filter(Boolean);

      let currentPath = '';
      let currentChildren = rootRoutes;
      let parentNode: RouteNodeIR | undefined;

      if (segments.length === 0) {
        // Root page
        rootRoutes.push({
          id: 'root-page',
          path: '',
          fullPath: '/',
          segmentKind: 'static',
          componentIdentifier: 'RootPage',
          params: [],
          guards: [],
          children: [],
          isIndex: true,
        });
        continue;
      }

      for (let i = 0; i < segments.length; i++) {
        const seg = segments[i]!;
        const isLeaf = i === segments.length - 1;

        let kind: RouteSegmentKind = 'static';
        let cleanSeg = seg;
        const params: RouteParamDescriptor[] = [];

        if (seg.startsWith('(') && seg.endsWith(')')) {
          kind = 'route-group';
        } else if (seg.startsWith('[[...') && seg.endsWith(']]')) {
          kind = 'optional-catch-all';
          const pName = seg.slice(5, -2);
          params.push({ name: pName, kind, optional: true });
          cleanSeg = `:${pName}*`;
        } else if (seg.startsWith('[...') && seg.endsWith(']')) {
          kind = 'catch-all';
          const pName = seg.slice(4, -1);
          params.push({ name: pName, kind, optional: false });
          cleanSeg = `:${pName}+`;
        } else if (seg.startsWith('[') && seg.endsWith(']')) {
          kind = 'dynamic';
          const pName = seg.slice(1, -1);
          params.push({ name: pName, kind, optional: false });
          cleanSeg = `:${pName}`;
        }

        if (kind !== 'route-group') {
          currentPath += `/${cleanSeg}`;
        }

        let existing = currentChildren.find((r) => r.path === cleanSeg || r.id === seg);
        if (!existing) {
          existing = {
            id: seg,
            path: cleanSeg,
            fullPath: currentPath || '/',
            segmentKind: kind,
            componentIdentifier: isLeaf ? `${this.toPascalCase(seg)}Page` : 'Fragment',
            params,
            guards: [],
            children: [],
            isIndex: isLeaf,
          };
          currentChildren.push(existing);
        }

        parentNode = existing;
        currentChildren = existing.children;
      }
    }

    const routerIR: UniversalRouterIR = {
      routerId,
      sourceFramework: 'nextjs-app-router',
      routes: rootRoutes,
    };

    return {
      success: true,
      routerIR,
      errors,
      warnings,
      discoveredFramework: 'nextjs-app-router',
    };
  }

  /**
   * Emit Next.js App Router files from UniversalRouterIR
   */
  public emit(routerIR: UniversalRouterIR): RouterEmitResult {
    const files: RouterEmitResult['files'] = [];

    // Emit Root Layout
    files.push({
      filePath: 'app/layout.tsx',
      content: `export default function RootLayout({ children }: { children: React.ReactNode }) {\n  return (\n    <html lang="zh-CN">\n      <body>{children}</body>\n    </html>\n  );\n}\n`,
      role: 'layout-component',
    });

    const traverse = (node: RouteNodeIR, currentDir: string) => {
      let dir = currentDir;
      if (node.path && node.path !== '/') {
        let segDir = node.path;
        if (node.segmentKind === 'dynamic') {
          segDir = `[${node.params[0]?.name || 'id'}]`;
        } else if (node.segmentKind === 'catch-all') {
          segDir = `[...${node.params[0]?.name || 'slug'}]`;
        }
        dir = `${currentDir}/${segDir}`.replace(/^\/+/, '');
      }

      if (node.isIndex || node.children.length === 0) {
        files.push({
          filePath: `${dir}/page.tsx`,
          content: `export default function ${node.componentIdentifier}() {\n  return (\n    <main className="page-view" data-route="${node.fullPath}">\n      <h1>${node.componentIdentifier}</h1>\n    </main>\n  );\n}\n`,
          role: 'page-component',
        });
      }

      for (const child of node.children) {
        traverse(child, dir);
      }
    };

    for (const route of routerIR.routes) {
      traverse(route, 'app');
    }

    return {
      files,
      framework: 'nextjs-app-router',
      dependencies: [{ name: 'next', version: '^14.2.0', isDev: false }],
      notes: [`Generated Next.js App Router file tree from UniversalRouterIR: ${routerIR.routerId}`],
    };
  }

  private toPascalCase(str: string): string {
    return str
      .replace(/[^a-zA-Z0-9]/g, ' ')
      .split(' ')
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join('');
  }
}
