/**
 * @file zustand-adapter.ts
 * @description Zustand TypeScript AST parser and code emitter.
 * Parses `create<T>()(...)`, middleware chains (persist, devtools, immer),
 * state properties, actions, and getters, lifting to UniversalStoreIR.
 * Emits modern TypeScript Zustand stores with full typing.
 */

import * as ts from 'typescript';
import {
  UniversalStoreIR,
  StateFieldIR,
  StoreGetterIR,
  StoreMutationIR,
  StoreAsyncActionIR,
  StorePersistenceConfigIR,
  StoreParseResult,
  StoreEmitResult,
  StateTypeDescriptor,
} from './store-ir-types';

export class ZustandAdapter {
  /**
   * Parse a Zustand store source file into UniversalStoreIR
   */
  public parse(sourceCode: string, storeId: string = 'app-store'): StoreParseResult {
    const errors: string[] = [];
    const warnings: string[] = [];
    const sourceFile = ts.createSourceFile(
      'store.ts',
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    );

    const stateFields: StateFieldIR[] = [];
    const getters: StoreGetterIR[] = [];
    const mutations: StoreMutationIR[] = [];
    const actions: StoreAsyncActionIR[] = [];
    let persistenceConfig: StorePersistenceConfigIR | undefined;
    const middlewares: string[] = [];

    let storeName = 'useAppStore';

    const visit = (node: ts.Node) => {
      // Find `export const use... = create(...)`
      if (ts.isVariableDeclaration(node) && node.initializer) {
        const varName = node.name.getText(sourceFile);
        if (varName.startsWith('use')) {
          storeName = varName;
        }

        this.inspectCreateCall(
          node.initializer,
          sourceFile,
          stateFields,
          getters,
          mutations,
          actions,
          middlewares,
          (config) => {
            persistenceConfig = config;
          },
          errors,
          warnings
        );
      }
      ts.forEachChild(node, visit);
    };

    visit(sourceFile);

    const storeIR: UniversalStoreIR = {
      storeId,
      storeName,
      sourceFramework: 'zustand',
      architecture: 'standalone-store',
      stateFields,
      getters,
      mutations,
      actions,
      subscriptions: [],
      persistence: persistenceConfig,
      middleware: middlewares,
    };

    return {
      success: errors.length === 0,
      storeIR,
      errors,
      warnings,
      discoveredFramework: 'zustand',
    };
  }

  private inspectCreateCall(
    expr: ts.Expression,
    sourceFile: ts.SourceFile,
    stateFields: StateFieldIR[],
    getters: StoreGetterIR[],
    mutations: StoreMutationIR[],
    actions: StoreAsyncActionIR[],
    middlewares: string[],
    setPersistence: (p: StorePersistenceConfigIR) => void,
    errors: string[],
    warnings: string[]
  ) {
    const processExpression = (e: ts.Expression) => {
      if (!ts.isCallExpression(e)) return;

      const caller = e.expression;
      const callerText = caller.getText(sourceFile);

      if (callerText.includes('devtools')) {
        middlewares.push('devtools');
      }
      if (callerText.includes('immer')) {
        middlewares.push('immer');
      }
      if (callerText.includes('persist')) {
        middlewares.push('persist');
        const secondArg = e.arguments[1];
        if (secondArg && ts.isObjectLiteralExpression(secondArg)) {
          const persistOpts = secondArg as ts.ObjectLiteralExpression;
          let pName = 'app-storage';
          for (const prop of persistOpts.properties) {
            if (ts.isPropertyAssignment(prop) && prop.name.getText(sourceFile) === 'name') {
              pName = prop.initializer.getText(sourceFile).replace(/['"]/g, '');
            }
          }
          setPersistence({
            storage: 'localStorage',
            storageKey: pName,
            persistedFields: [],
          });
        }
      }

      // Check arguments for store initializer function or nested middleware
      for (const arg of e.arguments) {
        if (ts.isCallExpression(arg)) {
          processExpression(arg);
        } else if (ts.isArrowFunction(arg) || ts.isFunctionExpression(arg)) {
          let body = arg.body;
          if (ts.isParenthesizedExpression(body)) {
            body = body.expression;
          }
          if (ts.isObjectLiteralExpression(body)) {
            this.extractObjectMembers(body, sourceFile, stateFields, getters, mutations, actions);
          } else if (ts.isBlock(body)) {
            for (const stmt of body.statements) {
              if (ts.isReturnStatement(stmt) && stmt.expression) {
                let retExpr = stmt.expression;
                if (ts.isParenthesizedExpression(retExpr)) {
                  retExpr = retExpr.expression;
                }
                if (ts.isObjectLiteralExpression(retExpr)) {
                  this.extractObjectMembers(retExpr, sourceFile, stateFields, getters, mutations, actions);
                }
              }
            }
          }
        }
      }

      processExpression(caller);
    };

    processExpression(expr);
  }

  private extractObjectMembers(
    obj: ts.ObjectLiteralExpression,
    sourceFile: ts.SourceFile,
    stateFields: StateFieldIR[],
    getters: StoreGetterIR[],
    mutations: StoreMutationIR[],
    actions: StoreAsyncActionIR[]
  ) {
    for (const prop of obj.properties) {
      if (ts.isPropertyAssignment(prop)) {
        const propName = prop.name.getText(sourceFile);
        const init = prop.initializer;

        if (ts.isArrowFunction(init) || ts.isFunctionExpression(init)) {
          const fnText = init.getText(sourceFile);
          const isAsync = init.modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword) || fnText.includes('async ') || fnText.includes('await ');

          if (isAsync) {
            actions.push({
              name: propName,
              parameters: this.extractParams(init.parameters, sourceFile),
              returnType: { rawType: 'Promise<void>', kind: 'custom', nullable: false, optional: false },
              executionBodyCode: init.body.getText(sourceFile),
              dispatchedMutations: [],
            });
          } else {
            mutations.push({
              name: propName,
              parameters: this.extractParams(init.parameters, sourceFile),
              mutationBodyCode: init.body.getText(sourceFile),
              affectedFields: [],
              isPure: !fnText.includes('set('),
            });
          }
        } else {
          // Regular state field
          const rawVal = init.getText(sourceFile);
          stateFields.push({
            name: propName,
            type: this.inferTypeFromLiteral(init, sourceFile),
            initialValueCode: rawVal,
            isPersisted: false,
            isSensitive: false,
          });
        }
      } else if (ts.isMethodDeclaration(prop)) {
        const methodName = prop.name.getText(sourceFile);
        const isAsync = prop.modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword);

        if (isAsync) {
          actions.push({
            name: methodName,
            parameters: this.extractParams(prop.parameters, sourceFile),
            returnType: { rawType: 'Promise<void>', kind: 'custom', nullable: false, optional: false },
            executionBodyCode: prop.body ? prop.body.getText(sourceFile) : '{}',
            dispatchedMutations: [],
          });
        } else {
          mutations.push({
            name: methodName,
            parameters: this.extractParams(prop.parameters, sourceFile),
            mutationBodyCode: prop.body ? prop.body.getText(sourceFile) : '{}',
            affectedFields: [],
            isPure: false,
          });
        }
      } else if (ts.isGetAccessor(prop)) {
        getters.push({
          name: prop.name.getText(sourceFile),
          returnType: { rawType: 'unknown', kind: 'custom', nullable: false, optional: false },
          dependencies: [],
          computationBodyCode: prop.body ? prop.body.getText(sourceFile) : '{}',
          isMemoized: true,
        });
      }
    }
  }

  private extractParams(params: ts.NodeArray<ts.ParameterDeclaration>, sourceFile: ts.SourceFile) {
    return params.map((p) => ({
      name: p.name.getText(sourceFile),
      type: {
        rawType: p.type ? p.type.getText(sourceFile) : 'any',
        kind: 'custom' as const,
        nullable: false,
        optional: !!p.questionToken,
      },
    }));
  }

  private inferTypeFromLiteral(expr: ts.Expression, sourceFile: ts.SourceFile): StateTypeDescriptor {
    if (ts.isStringLiteral(expr)) {
      return { rawType: 'string', kind: 'primitive', nullable: false, optional: false };
    }
    if (ts.isNumericLiteral(expr)) {
      return { rawType: 'number', kind: 'primitive', nullable: false, optional: false };
    }
    if (expr.kind === ts.SyntaxKind.TrueKeyword || expr.kind === ts.SyntaxKind.FalseKeyword) {
      return { rawType: 'boolean', kind: 'primitive', nullable: false, optional: false };
    }
    if (ts.isArrayLiteralExpression(expr)) {
      return { rawType: 'unknown[]', kind: 'array', nullable: false, optional: false };
    }
    if (ts.isObjectLiteralExpression(expr)) {
      return { rawType: 'Record<string, unknown>', kind: 'object', nullable: false, optional: false };
    }
    return { rawType: 'unknown', kind: 'custom', nullable: false, optional: false };
  }

  /**
   * Emit Zustand store TypeScript code from UniversalStoreIR
   */
  public emit(storeIR: UniversalStoreIR): StoreEmitResult {
    const typeName = `${this.capitalize(storeIR.storeName)}State`;
    const lines: string[] = [];

    // Imports
    const hasPersistence = !!storeIR.persistence;
    if (hasPersistence) {
      lines.push(`import { create } from 'zustand';`);
      lines.push(`import { persist, createJSONStorage } from 'zustand/middleware';\n`);
    } else {
      lines.push(`import { create } from 'zustand';\n`);
    }

    // State & Action Type Definition
    lines.push(`export interface ${typeName} {`);
    for (const field of storeIR.stateFields) {
      const opt = field.type.optional ? '?' : '';
      lines.push(`  ${field.name}${opt}: ${field.type.rawType};`);
    }
    for (const getter of storeIR.getters) {
      lines.push(`  ${getter.name}(): ${getter.returnType.rawType};`);
    }
    for (const mutation of storeIR.mutations) {
      const pList = mutation.parameters.map((p) => `${p.name}: ${p.type.rawType}`).join(', ');
      lines.push(`  ${mutation.name}(${pList}): void;`);
    }
    for (const action of storeIR.actions) {
      const pList = action.parameters.map((p) => `${p.name}: ${p.type.rawType}`).join(', ');
      lines.push(`  ${action.name}(${pList}): ${action.returnType.rawType};`);
    }
    lines.push(`}\n`);

    // Store Implementation
    const storeConst = storeIR.storeName.startsWith('use') ? storeIR.storeName : `use${this.capitalize(storeIR.storeName)}`;

    if (hasPersistence && storeIR.persistence) {
      lines.push(`export const ${storeConst} = create<${typeName}>()( `);
      lines.push(`  persist(`);
      lines.push(`    (set, get) => ({`);
    } else {
      lines.push(`export const ${storeConst} = create<${typeName}>((set, get) => ({`);
    }

    // Initial state properties
    for (const field of storeIR.stateFields) {
      lines.push(`      ${field.name}: ${field.initialValueCode},`);
    }

    // Getters
    for (const getter of storeIR.getters) {
      lines.push(`      ${getter.name}: () => {`);
      lines.push(`        ${this.indent(getter.computationBodyCode, 8)}`);
      lines.push(`      },`);
    }

    // Mutations
    for (const mutation of storeIR.mutations) {
      const pList = mutation.parameters.map((p) => p.name).join(', ');
      lines.push(`      ${mutation.name}: (${pList}) => {`);
      // If mutationBodyCode contains set(...), emit directly; otherwise wrap in set
      if (mutation.mutationBodyCode.includes('set(')) {
        lines.push(`        ${this.indent(mutation.mutationBodyCode, 8)}`);
      } else {
        lines.push(`        set((state) => {`);
        lines.push(`          ${this.indent(mutation.mutationBodyCode, 10)}`);
        lines.push(`        });`);
      }
      lines.push(`      },`);
    }

    // Actions
    for (const action of storeIR.actions) {
      const pList = action.parameters.map((p) => p.name).join(', ');
      lines.push(`      ${action.name}: async (${pList}) => {`);
      lines.push(`        ${this.indent(action.executionBodyCode, 8)}`);
      lines.push(`      },`);
    }

    if (hasPersistence && storeIR.persistence) {
      lines.push(`    }),`);
      lines.push(`    {`);
      lines.push(`      name: '${storeIR.persistence.storageKey}',`);
      if (storeIR.persistence.storage === 'sessionStorage') {
        lines.push(`      storage: createJSONStorage(() => sessionStorage),`);
      }
      lines.push(`    }`);
      lines.push(`  )`);
      lines.push(`);\n`);
    } else {
      lines.push(`  })`);
      lines.push(`);\n`);
    }

    return {
      code: lines.join('\n'),
      fileName: `${storeIR.storeId}.ts`,
      framework: 'zustand',
      dependencies: [{ name: 'zustand', version: '^4.5.0', isDev: false }],
      notes: [`Generated Zustand store from UniversalStoreIR: ${storeIR.storeId}`],
    };
  }

  private capitalize(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  private indent(text: string, spaces: number): string {
    const pad = ' '.repeat(spaces);
    return text
      .split('\n')
      .map((line) => (line.trim().length > 0 ? pad + line.trim() : ''))
      .join('\n');
  }
}
