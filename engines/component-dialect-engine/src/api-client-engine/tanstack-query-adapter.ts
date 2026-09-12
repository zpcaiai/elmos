/**
 * @file tanstack-query-adapter.ts
 * @description Full AST parser and code generator for TanStack Query v4/v5 (React Query & Vue Query).
 * Parses `useQuery()`, `useMutation()`, `useInfiniteQuery()`, and `queryClient.invalidateQueries()`,
 * and emits typed custom hooks and composables with automatic query key factories and cache invalidation.
 * Conforms to Batch 32 Skill 1202 (b32-api-client-data-cache).
 */

import * as ts from 'typescript';
import {
  UniversalApiClientIR,
  QueryOperationIR,
  MutationOperationIR,
  ApiClientTransformResult,
  ApiEndpointParamIR,
} from './api-client-ir-types';

export interface TanStackParsedHook {
  hookName: string;
  kind: 'query' | 'mutation' | 'infinite-query';
  queryKey?: string[];
  endpointPath?: string;
  invalidates?: string[][];
  hasOptimisticUpdate: boolean;
}

export class TanStackQueryAdapter {
  /**
   * Parse TypeScript source code containing TanStack Query hooks.
   */
  public parseSource(sourceCode: string, fileName: string = 'apiHooks.ts'): TanStackParsedHook[] {
    const sourceFile = ts.createSourceFile(
      fileName,
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    );

    const hooks: TanStackParsedHook[] = [];

    const visit = (node: ts.Node) => {
      if (ts.isFunctionDeclaration(node) && node.name && node.name.text.startsWith('use')) {
        const hook = this.inspectHookFunction(node, node.name.text, sourceFile);
        if (hook) hooks.push(hook);
      } else if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text.startsWith('use')) {
        if (node.initializer && (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))) {
          const hook = this.inspectHookFunction(node.initializer, node.name.text, sourceFile);
          if (hook) hooks.push(hook);
        }
      }

      ts.forEachChild(node, visit);
    };

    visit(sourceFile);
    return hooks;
  }

  private inspectHookFunction(
    fnNode: ts.FunctionDeclaration | ts.ArrowFunction | ts.FunctionExpression,
    hookName: string,
    sourceFile: ts.SourceFile
  ): TanStackParsedHook | null {
    let hookKind: 'query' | 'mutation' | 'infinite-query' | null = null;
    let queryKey: string[] | undefined = undefined;
    let endpointPath: string | undefined = undefined;
    const invalidates: string[][] = [];
    let hasOptimisticUpdate = false;

    const walk = (n: ts.Node) => {
      if (ts.isCallExpression(n)) {
        const callName = n.expression.getText(sourceFile);

        if (callName === 'useQuery' || callName.endsWith('.useQuery')) {
          hookKind = 'query';
          queryKey = this.extractQueryKey(n, sourceFile);
        } else if (callName === 'useMutation' || callName.endsWith('.useMutation')) {
          hookKind = 'mutation';
        } else if (callName === 'useInfiniteQuery' || callName.endsWith('.useInfiniteQuery')) {
          hookKind = 'infinite-query';
          queryKey = this.extractQueryKey(n, sourceFile);
        } else if (callName.includes('invalidateQueries')) {
          const invKey = this.extractQueryKey(n, sourceFile);
          if (invKey) invalidates.push(invKey);
        }

        // Check for optimistic update handlers inside options object
        if (n.arguments.length > 0) {
          const lastArg = n.arguments[n.arguments.length - 1];
          if (lastArg && ts.isObjectLiteralExpression(lastArg)) {
            for (const prop of lastArg.properties) {
              if (ts.isPropertyAssignment(prop) && prop.name) {
                const propName = prop.name.getText(sourceFile);
                if (propName === 'onMutate') {
                  hasOptimisticUpdate = true;
                }
              }
            }
          }
        }
      }

      // Check string literals for api paths e.g. '/api/v1/...'
      if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) {
        if (n.text.startsWith('/api') || n.text.startsWith('http')) {
          endpointPath = n.text;
        }
      }

      ts.forEachChild(n, walk);
    };

    walk(fnNode);

    if (!hookKind) return null;

    return {
      hookName,
      kind: hookKind,
      queryKey,
      endpointPath,
      invalidates: invalidates.length > 0 ? invalidates : undefined,
      hasOptimisticUpdate,
    };
  }

  private extractQueryKey(callNode: ts.CallExpression, sourceFile: ts.SourceFile): string[] | undefined {
    // TanStack Query v5: useQuery({ queryKey: ['users', id], queryFn: ... })
    // TanStack Query v4: useQuery(['users', id], queryFn)
    if (callNode.arguments.length === 0) return undefined;

    const firstArg = callNode.arguments[0];
    if (firstArg && ts.isArrayLiteralExpression(firstArg)) {
      return firstArg.elements.map((e) => e.getText(sourceFile).replace(/['"`]/g, ''));
    }

    if (firstArg && ts.isObjectLiteralExpression(firstArg)) {
      for (const prop of firstArg.properties) {
        if (ts.isPropertyAssignment(prop) && prop.name) {
          const pName = prop.name.getText(sourceFile);
          if (pName === 'queryKey' && ts.isArrayLiteralExpression(prop.initializer)) {
            return prop.initializer.elements.map((e) => e.getText(sourceFile).replace(/['"`]/g, ''));
          }
        }
      }
    }

    return undefined;
  }

  /**
   * Emit production-ready TanStack Query React hooks.
   */
  public emitReactQueryHooks(clientIR: UniversalApiClientIR): ApiClientTransformResult {
    const lines: string[] = [
      `/**`,
      ` * Auto-generated TanStack React Query v5 API Hooks`,
      ` * Client: ${clientIR.clientName}`,
      ` */`,
      `import { useQuery, useMutation, useInfiniteQuery, useQueryClient, UseQueryOptions, UseMutationOptions } from '@tanstack/react-query';`,
      `import axios, { AxiosRequestConfig } from 'axios';`,
      '',
      `const BASE_URL = '${clientIR.baseUrl}';`,
      '',
      `// Axios instance with default configuration`,
      `export const apiClient = axios.create({`,
      `  baseURL: BASE_URL,`,
      `  timeout: ${clientIR.timeoutMs},`,
      `});`,
      '',
    ];

    // Query Keys Factory
    lines.push(`// Query Key Factory`);
    lines.push(`export const queryKeys = {`);
    for (const [qId, qOp] of Object.entries(clientIR.queries)) {
      const paramNames = qOp.parameters.filter((p) => p.in === 'path' || p.in === 'query').map((p) => `${p.name}: ${p.type}`);
      const keyArgs = qOp.queryKey.map((k) => (k.startsWith(':') ? k.slice(1) : `'${k}'`)).join(', ');
      lines.push(`  ${qId}: (${paramNames.join(', ')}) => [${keyArgs}] as const,`);
    }
    lines.push(`};`);
    lines.push('');

    // Emit Query Hooks
    let queriesCount = 0;
    for (const [qId, qOp] of Object.entries(clientIR.queries)) {
      queriesCount++;
      lines.push(this.emitSingleQueryHook(qId, qOp));
      lines.push('');
    }

    // Emit Mutation Hooks
    let mutationsCount = 0;
    let optimisticUpdatesCount = 0;
    let invalidationsCount = 0;

    for (const [mId, mOp] of Object.entries(clientIR.mutations)) {
      mutationsCount++;
      if (mOp.optimisticUpdates && mOp.optimisticUpdates.length > 0) {
        optimisticUpdatesCount += mOp.optimisticUpdates.length;
      }
      invalidationsCount += mOp.invalidatesQueryKeys.length;
      lines.push(this.emitSingleMutationHook(mId, mOp));
      lines.push('');
    }

    return {
      targetFramework: 'tanstack-query-react',
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

  private emitSingleQueryHook(id: string, qOp: QueryOperationIR): string {
    const lines: string[] = [];
    const hookName = `use${this.capitalize(qOp.name || id)}Query`;
    const paramsList = qOp.parameters.map((p) => `${p.name}${p.required ? '' : '?'}: ${p.type}`);
    const fnParams = paramsList.length > 0 ? `params: { ${paramsList.join(', ')} }, ` : '';

    if (qOp.isInfinitePagination && qOp.paginationConfig) {
      lines.push(`export function ${hookName}(`);
      lines.push(`  ${fnParams}options?: any`);
      lines.push(`) {`);
      lines.push(`  return useInfiniteQuery({`);
      lines.push(`    queryKey: queryKeys.${id}(${qOp.parameters.map((p) => `params.${p.name}`).join(', ')}),`);
      lines.push(`    queryFn: async ({ pageParam = 1 }) => {`);
      lines.push(`      const { data } = await apiClient.get<${qOp.responseType}>('${qOp.path}', {`);
      lines.push(`        params: { ...params, ${qOp.paginationConfig.pageParamName}: pageParam },`);
      lines.push(`      });`);
      lines.push(`      return data;`);
      lines.push(`    },`);
      lines.push(`    initialPageParam: 1,`);
      lines.push(`    getNextPageParam: ${qOp.paginationConfig.getNextPageParamExpr},`);
      lines.push(`    staleTime: ${qOp.staleTimeMs ?? 300000},`);
      lines.push(`    ...options,`);
      lines.push(`  });`);
      lines.push(`}`);
    } else {
      lines.push(`export function ${hookName}(`);
      lines.push(`  ${fnParams}options?: Omit<UseQueryOptions<${qOp.responseType}>, 'queryKey' | 'queryFn'>`);
      lines.push(`) {`);
      lines.push(`  return useQuery<${qOp.responseType}>({`);
      const keyCall = qOp.parameters.length > 0 ? `queryKeys.${id}(${qOp.parameters.map((p) => `params.${p.name}`).join(', ')})` : `queryKeys.${id}()`;
      lines.push(`    queryKey: ${keyCall},`);
      lines.push(`    queryFn: async () => {`);

      let urlExpr = `'${qOp.path}'`;
      for (const p of qOp.parameters.filter((param) => param.in === 'path')) {
        urlExpr = urlExpr.replace(`:${p.name}`, `\${params.${p.name}}`);
      }
      if (urlExpr.includes('${')) {
        urlExpr = `\`${urlExpr.slice(1, -1)}\``;
      }

      const queryParams = qOp.parameters.filter((p) => p.in === 'query');
      const axiosOptions = queryParams.length > 0 ? `, { params: { ${queryParams.map((p) => `${p.name}: params.${p.name}`).join(', ')} } }` : '';

      lines.push(`      const { data } = await apiClient.${qOp.method.toLowerCase()}<${qOp.responseType}>(${urlExpr}${axiosOptions});`);
      lines.push(`      return data;`);
      lines.push(`    },`);
      lines.push(`    staleTime: ${qOp.staleTimeMs ?? 60000},`);
      if (qOp.retryPolicy) {
        lines.push(`    retry: ${qOp.retryPolicy.maxRetries},`);
      }
      lines.push(`    ...options,`);
      lines.push(`  });`);
      lines.push(`}`);
    }

    return lines.join('\n');
  }

  private emitSingleMutationHook(id: string, mOp: MutationOperationIR): string {
    const lines: string[] = [];
    const hookName = `use${this.capitalize(mOp.name || id)}Mutation`;
    const bodyType = mOp.requestBodyType || 'void';

    lines.push(`export function ${hookName}(`);
    lines.push(`  options?: UseMutationOptions<${mOp.responseType}, Error, ${bodyType}>`);
    lines.push(`) {`);
    lines.push(`  const queryClient = useQueryClient();`);
    lines.push('');
    lines.push(`  return useMutation<${mOp.responseType}, Error, ${bodyType}>({`);
    lines.push(`    mutationFn: async (variables: ${bodyType}) => {`);

    const hasBody = mOp.method === 'POST' || mOp.method === 'PUT' || mOp.method === 'PATCH';
    const bodyParam = hasBody ? `, variables` : '';
    lines.push(`      const { data } = await apiClient.${mOp.method.toLowerCase()}<${mOp.responseType}>('${mOp.path}'${bodyParam});`);
    lines.push(`      return data;`);
    lines.push(`    },`);

    // Optimistic Updates
    if (mOp.optimisticUpdates && mOp.optimisticUpdates.length > 0) {
      lines.push(`    onMutate: async (newVariables) => {`);
      for (const opt of mOp.optimisticUpdates) {
        const keyArray = opt.targetQueryKey.map((k) => `'${k}'`).join(', ');
        lines.push(`      await queryClient.cancelQueries({ queryKey: [${keyArray}] });`);
        lines.push(`      const previousData = queryClient.getQueryData([${keyArray}]);`);
        lines.push(`      queryClient.setQueryData([${keyArray}], (old: any) => (${opt.updaterExpression})(old, newVariables));`);
        lines.push(`      return { previousData };`);
      }
      lines.push(`    },`);
      lines.push(`    onError: (err, newVariables, context: any) => {`);
      for (const opt of mOp.optimisticUpdates) {
        const keyArray = opt.targetQueryKey.map((k) => `'${k}'`).join(', ');
        lines.push(`      if (context?.previousData) {`);
        lines.push(`        queryClient.setQueryData([${keyArray}], context.previousData);`);
        lines.push(`      }`);
      }
      lines.push(`    },`);
    }

    // Cache Invalidation on success/settled
    if (mOp.invalidatesQueryKeys.length > 0) {
      lines.push(`    onSuccess: (data, variables, context) => {`);
      for (const invKey of mOp.invalidatesQueryKeys) {
        const keyArray = invKey.map((k) => `'${k}'`).join(', ');
        lines.push(`      queryClient.invalidateQueries({ queryKey: [${keyArray}] });`);
      }
      lines.push(`      options?.onSuccess?.(data, variables, context);`);
      lines.push(`    },`);
    }

    lines.push(`    ...options,`);
    lines.push(`  });`);
    lines.push(`}`);

    return lines.join('\n');
  }

  private capitalize(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
}
