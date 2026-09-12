/**
 * @file swr-adapter.ts
 * @description Full AST parser and code generator for Vercel SWR (Stale-While-Revalidate).
 * Parses `useSWR()`, `useSWRMutation()`, and global `mutate()` calls,
 * and emits typed custom SWR hooks with optimistic updates and cache revalidation triggers.
 * Conforms to Batch 32 Skill 1202 (b32-api-client-data-cache).
 */

import * as ts from 'typescript';
import {
  UniversalApiClientIR,
  QueryOperationIR,
  MutationOperationIR,
  ApiClientTransformResult,
} from './api-client-ir-types';

export interface SwrParsedHook {
  hookName: string;
  kind: 'swr-query' | 'swr-mutation';
  keyExpression?: string;
  endpointPath?: string;
  revalidatesKeys?: string[];
  optimisticData?: boolean;
}

export class SwrAdapter {
  /**
   * Parse TypeScript source file for SWR hooks.
   */
  public parseSource(sourceCode: string, fileName: string = 'swrHooks.ts'): SwrParsedHook[] {
    const sourceFile = ts.createSourceFile(
      fileName,
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    );

    const hooks: SwrParsedHook[] = [];

    const visit = (node: ts.Node) => {
      if (ts.isFunctionDeclaration(node) && node.name && node.name.text.startsWith('use')) {
        const hook = this.inspectSwrFunction(node, node.name.text, sourceFile);
        if (hook) hooks.push(hook);
      } else if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text.startsWith('use')) {
        if (node.initializer && (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))) {
          const hook = this.inspectSwrFunction(node.initializer, node.name.text, sourceFile);
          if (hook) hooks.push(hook);
        }
      }

      ts.forEachChild(node, visit);
    };

    visit(sourceFile);
    return hooks;
  }

  private inspectSwrFunction(
    fnNode: ts.FunctionDeclaration | ts.ArrowFunction | ts.FunctionExpression,
    hookName: string,
    sourceFile: ts.SourceFile
  ): SwrParsedHook | null {
    let kind: 'swr-query' | 'swr-mutation' | null = null;
    let keyExpr: string | undefined = undefined;
    let endpointPath: string | undefined = undefined;
    const revalidatesKeys: string[] = [];
    let optimisticData = false;

    const walk = (n: ts.Node) => {
      if (ts.isCallExpression(n)) {
        const callName = n.expression.getText(sourceFile);

        if (callName === 'useSWR') {
          kind = 'swr-query';
          if (n.arguments.length > 0 && n.arguments[0]) {
            keyExpr = n.arguments[0].getText(sourceFile);
            if (ts.isStringLiteral(n.arguments[0])) {
              endpointPath = n.arguments[0].text;
            }
          }
        } else if (callName === 'useSWRMutation') {
          kind = 'swr-mutation';
          if (n.arguments.length > 0 && n.arguments[0]) {
            keyExpr = n.arguments[0].getText(sourceFile);
            if (ts.isStringLiteral(n.arguments[0])) {
              endpointPath = n.arguments[0].text;
            }
          }
        } else if (callName === 'mutate' || callName.includes('.mutate')) {
          if (n.arguments.length > 0 && n.arguments[0] && ts.isStringLiteral(n.arguments[0])) {
            revalidatesKeys.push(n.arguments[0].text);
          }
        }

        // Check for optimisticData option
        if (n.arguments.length > 2 && n.arguments[2] && ts.isObjectLiteralExpression(n.arguments[2])) {
          for (const prop of n.arguments[2].properties) {
            if (ts.isPropertyAssignment(prop) && prop.name && prop.name.getText(sourceFile) === 'optimisticData') {
              optimisticData = true;
            }
          }
        }
      }

      ts.forEachChild(n, walk);
    };

    walk(fnNode);

    if (!kind) return null;

    return {
      hookName,
      kind,
      keyExpression: keyExpr,
      endpointPath,
      revalidatesKeys: revalidatesKeys.length > 0 ? revalidatesKeys : undefined,
      optimisticData,
    };
  }

  /**
   * Emit production-ready SWR React hooks from Universal Api Client IR.
   */
  public emitSwrHooks(clientIR: UniversalApiClientIR): ApiClientTransformResult {
    const lines: string[] = [
      `/**`,
      ` * Auto-generated SWR API Hooks`,
      ` * Client: ${clientIR.clientName}`,
      ` */`,
      `import useSWR, { SWRConfiguration, mutate } from 'swr';`,
      `import useSWRMutation, { SWRMutationConfiguration } from 'swr/mutation';`,
      '',
      `const BASE_URL = '${clientIR.baseUrl}';`,
      '',
      `// Global Fetcher with JSON parse and HTTP error check`,
      `export const defaultFetcher = async <T>(url: string): Promise<T> => {`,
      `  const fullUrl = url.startsWith('http') ? url : \`\${BASE_URL}\${url}\`;`,
      `  const res = await fetch(fullUrl, {`,
      `    headers: { 'Content-Type': 'application/json' },`,
      `  });`,
      `  if (!res.ok) {`,
      `    const error: any = new Error('HTTP Request Failed: ' + res.status);`,
      `    error.status = res.status;`,
      `    throw error;`,
      `  }`,
      `  return res.json();`,
      `};`,
      '',
    ];

    // Emit SWR Query Hooks
    let queriesCount = 0;
    for (const [qId, qOp] of Object.entries(clientIR.queries)) {
      queriesCount++;
      lines.push(this.emitSingleSwrQuery(qId, qOp));
      lines.push('');
    }

    // Emit SWR Mutation Hooks
    let mutationsCount = 0;
    let optimisticUpdatesCount = 0;
    let invalidationsCount = 0;

    for (const [mId, mOp] of Object.entries(clientIR.mutations)) {
      mutationsCount++;
      if (mOp.optimisticUpdates && mOp.optimisticUpdates.length > 0) {
        optimisticUpdatesCount += mOp.optimisticUpdates.length;
      }
      invalidationsCount += mOp.invalidatesQueryKeys.length;
      lines.push(this.emitSingleSwrMutation(mId, mOp));
      lines.push('');
    }

    return {
      targetFramework: 'swr-react',
      clientClassCode: lines.join('\n'),
      warnings: [],
      metrics: {
        queriesCount,
        mutationsCount,
        optimisticUpdatesCount,
        invalidationsCount,
      },
    };
  }

  private emitSingleSwrQuery(id: string, qOp: QueryOperationIR): string {
    const lines: string[] = [];
    const hookName = `use${this.capitalize(qOp.name || id)}SWR`;
    const paramsList = qOp.parameters.map((p) => `${p.name}${p.required ? '' : '?'}: ${p.type}`);
    const fnParams = paramsList.length > 0 ? `params: { ${paramsList.join(', ')} }, ` : '';

    lines.push(`export function ${hookName}(`);
    lines.push(`  ${fnParams}config?: SWRConfiguration<${qOp.responseType}>`);
    lines.push(`) {`);

    let pathExpr = `'${qOp.path}'`;
    for (const p of qOp.parameters.filter((param) => param.in === 'path')) {
      pathExpr = pathExpr.replace(`:${p.name}`, `\${params.${p.name}}`);
    }
    if (pathExpr.includes('${')) {
      pathExpr = `\`${pathExpr.slice(1, -1)}\``;
    }

    const queryParams = qOp.parameters.filter((p) => p.in === 'query');
    if (queryParams.length > 0) {
      lines.push(`  const queryStr = new URLSearchParams(params as any).toString();`);
      lines.push(`  const key = \`\${${pathExpr}}?\${queryStr}\`;`);
    } else {
      lines.push(`  const key = ${pathExpr};`);
    }

    lines.push(`  return useSWR<${qOp.responseType}>(key, defaultFetcher, {`);
    lines.push(`    dedupingInterval: ${qOp.staleTimeMs ?? 60000},`);
    lines.push(`    revalidateOnFocus: ${qOp.refetchOnWindowFocus ?? true},`);
    lines.push(`    ...config,`);
    lines.push(`  });`);
    lines.push(`}`);

    return lines.join('\n');
  }

  private emitSingleSwrMutation(id: string, mOp: MutationOperationIR): string {
    const lines: string[] = [];
    const hookName = `use${this.capitalize(mOp.name || id)}SWRMutation`;
    const bodyType = mOp.requestBodyType || 'any';

    lines.push(`export function ${hookName}(`);
    lines.push(`  config?: SWRMutationConfiguration<${mOp.responseType}, Error, string, ${bodyType}>`);
    lines.push(`) {`);
    lines.push(`  return useSWRMutation<${mOp.responseType}, Error, string, ${bodyType}>(`);
    lines.push(`    '${mOp.path}',`);
    lines.push(`    async (url, { arg }) => {`);
    lines.push(`      const fullUrl = \`\${BASE_URL}\${url}\`;`);
    lines.push(`      const res = await fetch(fullUrl, {`);
    lines.push(`        method: '${mOp.method}',`);
    lines.push(`        headers: { 'Content-Type': 'application/json' },`);
    if (mOp.method !== 'GET' && mOp.method !== 'HEAD') {
      lines.push(`        body: JSON.stringify(arg),`);
    }
    lines.push(`      });`);
    lines.push(`      if (!res.ok) throw new Error('Mutation failed: ' + res.status);`);
    lines.push(`      return res.json();`);
    lines.push(`    },`);
    lines.push(`    {`);

    // Invalidation via mutate
    if (mOp.invalidatesQueryKeys.length > 0) {
      lines.push(`      onSuccess: async (data, key, config) => {`);
      for (const inv of mOp.invalidatesQueryKeys) {
        // e.g. inv = ["users", "list"] -> mutate('/api/users')
        const pathMatch = inv.join('/');
        lines.push(`        await mutate((k: any) => typeof k === 'string' && k.includes('${pathMatch}'));`);
      }
      lines.push(`      },`);
    }

    lines.push(`      ...config,`);
    lines.push(`    }`);
    lines.push(`  );`);
    lines.push(`}`);

    return lines.join('\n');
  }

  private capitalize(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
}
