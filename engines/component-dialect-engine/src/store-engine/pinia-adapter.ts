/**
 * @file pinia-adapter.ts
 * @description Pinia AST parser and code emitter for Vue 3 state management.
 * Supports both Setup Stores (`defineStore(id, () => { ref, computed, function })`)
 * and Options Stores (`defineStore(id, { state, getters, actions })`).
 * Conforms to Batch 32 Skill 1209 (b32-state-management-lifecycle).
 */

import * as ts from 'typescript';
import {
  UniversalStoreIR,
  StateFieldIR,
  StoreGetterIR,
  StoreMutationIR,
  StoreAsyncActionIR,
  StoreParseResult,
  StoreEmitResult,
  StateTypeDescriptor,
} from './store-ir-types';

export class PiniaAdapter {
  /**
   * Parse Pinia store TypeScript source into UniversalStoreIR
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
    let storeName = storeId;

    const visit = (node: ts.Node) => {
      // Look for `defineStore('storeId', ...)`
      if (ts.isCallExpression(node)) {
        const fnName = node.expression.getText(sourceFile);
        if (fnName.includes('defineStore') && node.arguments.length >= 2) {
          const idArg = node.arguments[0];
          const secondArg = node.arguments[1];
          if (idArg && secondArg) {
            storeName = idArg.getText(sourceFile).replace(/['"]/g, '');

            if (ts.isArrowFunction(secondArg) || ts.isFunctionExpression(secondArg)) {
              // Setup store: () => { ... }
              this.parseSetupStore(secondArg, sourceFile, stateFields, getters, mutations, actions);
            } else if (ts.isObjectLiteralExpression(secondArg)) {
              // Options store: { state: ..., getters: ..., actions: ... }
              this.parseOptionsStore(secondArg, sourceFile, stateFields, getters, mutations, actions);
            }
          }
        }
      }
      ts.forEachChild(node, visit);
    };

    visit(sourceFile);

    const storeIR: UniversalStoreIR = {
      storeId: storeName,
      storeName: `use${this.capitalize(storeName)}Store`,
      sourceFramework: 'pinia',
      architecture: 'standalone-store',
      stateFields,
      getters,
      mutations,
      actions,
      subscriptions: [],
    };

    return {
      success: errors.length === 0,
      storeIR,
      errors,
      warnings,
      discoveredFramework: 'pinia',
    };
  }

  private parseSetupStore(
    fn: ts.FunctionLikeDeclarationBase,
    sourceFile: ts.SourceFile,
    stateFields: StateFieldIR[],
    getters: StoreGetterIR[],
    mutations: StoreMutationIR[],
    actions: StoreAsyncActionIR[]
  ) {
    if (!fn.body || !ts.isBlock(fn.body)) return;

    for (const stmt of fn.body.statements) {
      if (ts.isVariableStatement(stmt)) {
        for (const decl of stmt.declarationList.declarations) {
          const varName = decl.name.getText(sourceFile);
          if (decl.initializer && ts.isCallExpression(decl.initializer)) {
            const callee = decl.initializer.expression.getText(sourceFile);
            if (callee === 'ref') {
              const initArg = decl.initializer.arguments[0];
              const initVal = initArg ? initArg.getText(sourceFile) : 'undefined';
              stateFields.push({
                name: varName,
                type: initArg ? this.inferType(initArg) : { rawType: 'any', kind: 'custom', nullable: false, optional: false },
                initialValueCode: initVal,
                isPersisted: false,
                isSensitive: false,
              });
            } else if (callee === 'reactive') {
              stateFields.push({
                name: varName,
                type: { rawType: 'Record<string, unknown>', kind: 'object', nullable: false, optional: false },
                initialValueCode: decl.initializer.arguments[0]?.getText(sourceFile) || '{}',
                isPersisted: false,
                isSensitive: false,
              });
            } else if (callee === 'computed') {
              const compArg = decl.initializer.arguments[0];
              getters.push({
                name: varName,
                returnType: { rawType: 'unknown', kind: 'custom', nullable: false, optional: false },
                dependencies: [],
                computationBodyCode: compArg ? compArg.getText(sourceFile) : '() => {}',
                isMemoized: true,
              });
            }
          }
        }
      } else if (ts.isFunctionDeclaration(stmt) && stmt.name) {
        const fnName = stmt.name.getText(sourceFile);
        const isAsync = stmt.modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword);
        if (isAsync) {
          actions.push({
            name: fnName,
            parameters: stmt.parameters.map((p) => ({
              name: p.name.getText(sourceFile),
              type: { rawType: p.type ? p.type.getText(sourceFile) : 'any', kind: 'custom', nullable: false, optional: false },
            })),
            returnType: { rawType: 'Promise<void>', kind: 'custom', nullable: false, optional: false },
            executionBodyCode: stmt.body ? stmt.body.getText(sourceFile) : '{}',
            dispatchedMutations: [],
          });
        } else {
          mutations.push({
            name: fnName,
            parameters: stmt.parameters.map((p) => ({
              name: p.name.getText(sourceFile),
              type: { rawType: p.type ? p.type.getText(sourceFile) : 'any', kind: 'custom', nullable: false, optional: false },
            })),
            mutationBodyCode: stmt.body ? stmt.body.getText(sourceFile) : '{}',
            affectedFields: [],
            isPure: false,
          });
        }
      }
    }
  }

  private parseOptionsStore(
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
        if (propName === 'state') {
          // state: () => ({ ... })
          if (ts.isArrowFunction(prop.initializer) || ts.isFunctionExpression(prop.initializer)) {
            let body = prop.initializer.body;
            if (ts.isParenthesizedExpression(body)) body = body.expression;
            if (ts.isObjectLiteralExpression(body)) {
              for (const sProp of body.properties) {
                if (ts.isPropertyAssignment(sProp)) {
                  stateFields.push({
                    name: sProp.name.getText(sourceFile),
                    type: this.inferType(sProp.initializer),
                    initialValueCode: sProp.initializer.getText(sourceFile),
                    isPersisted: false,
                    isSensitive: false,
                  });
                }
              }
            }
          }
        } else if (propName === 'getters' && ts.isObjectLiteralExpression(prop.initializer)) {
          for (const gProp of prop.initializer.properties) {
            if (ts.isMethodDeclaration(gProp)) {
              getters.push({
                name: gProp.name.getText(sourceFile),
                returnType: { rawType: 'unknown', kind: 'custom', nullable: false, optional: false },
                dependencies: [],
                computationBodyCode: gProp.body ? gProp.body.getText(sourceFile) : '{}',
                isMemoized: true,
              });
            }
          }
        } else if (propName === 'actions' && ts.isObjectLiteralExpression(prop.initializer)) {
          for (const aProp of prop.initializer.properties) {
            if (ts.isMethodDeclaration(aProp)) {
              const aName = aProp.name.getText(sourceFile);
              const isAsync = aProp.modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword);
              if (isAsync) {
                actions.push({
                  name: aName,
                  parameters: aProp.parameters.map((p) => ({
                    name: p.name.getText(sourceFile),
                    type: { rawType: p.type ? p.type.getText(sourceFile) : 'any', kind: 'custom', nullable: false, optional: false },
                  })),
                  returnType: { rawType: 'Promise<void>', kind: 'custom', nullable: false, optional: false },
                  executionBodyCode: aProp.body ? aProp.body.getText(sourceFile) : '{}',
                  dispatchedMutations: [],
                });
              } else {
                mutations.push({
                  name: aName,
                  parameters: aProp.parameters.map((p) => ({
                    name: p.name.getText(sourceFile),
                    type: { rawType: p.type ? p.type.getText(sourceFile) : 'any', kind: 'custom', nullable: false, optional: false },
                  })),
                  mutationBodyCode: aProp.body ? aProp.body.getText(sourceFile) : '{}',
                  affectedFields: [],
                  isPure: false,
                });
              }
            }
          }
        }
      }
    }
  }

  private inferType(expr: ts.Expression): StateTypeDescriptor {
    if (ts.isStringLiteral(expr)) return { rawType: 'string', kind: 'primitive', nullable: false, optional: false };
    if (ts.isNumericLiteral(expr)) return { rawType: 'number', kind: 'primitive', nullable: false, optional: false };
    if (expr.kind === ts.SyntaxKind.TrueKeyword || expr.kind === ts.SyntaxKind.FalseKeyword) {
      return { rawType: 'boolean', kind: 'primitive', nullable: false, optional: false };
    }
    if (ts.isArrayLiteralExpression(expr)) return { rawType: 'unknown[]', kind: 'array', nullable: false, optional: false };
    return { rawType: 'any', kind: 'custom', nullable: false, optional: false };
  }

  /**
   * Emit modern Pinia Setup Store TypeScript code from UniversalStoreIR
   */
  public emit(storeIR: UniversalStoreIR): StoreEmitResult {
    const lines: string[] = [];
    lines.push(`import { defineStore } from 'pinia';`);
    lines.push(`import { ref, computed } from 'vue';\n`);

    const hookName = storeIR.storeName.startsWith('use') ? storeIR.storeName : `use${this.capitalize(storeIR.storeName)}Store`;
    const storeId = storeIR.storeId;

    lines.push(`export const ${hookName} = defineStore('${storeId}', () => {`);

    // State refs
    lines.push(`  // State`);
    for (const field of storeIR.stateFields) {
      lines.push(`  const ${field.name} = ref<${field.type.rawType}>(${field.initialValueCode});`);
    }
    lines.push(``);

    // Computed getters
    if (storeIR.getters.length > 0) {
      lines.push(`  // Getters`);
      for (const getter of storeIR.getters) {
        lines.push(`  const ${getter.name} = computed(() => {`);
        lines.push(`    ${this.indent(getter.computationBodyCode, 4)}`);
        lines.push(`  });`);
      }
      lines.push(``);
    }

    // Synchronous mutations
    if (storeIR.mutations.length > 0) {
      lines.push(`  // Mutations`);
      for (const mutation of storeIR.mutations) {
        const pList = mutation.parameters.map((p) => `${p.name}: ${p.type.rawType}`).join(', ');
        lines.push(`  function ${mutation.name}(${pList}) {`);
        lines.push(`    ${this.indent(mutation.mutationBodyCode, 4)}`);
        lines.push(`  }`);
      }
      lines.push(``);
    }

    // Async actions
    if (storeIR.actions.length > 0) {
      lines.push(`  // Actions`);
      for (const action of storeIR.actions) {
        const pList = action.parameters.map((p) => `${p.name}: ${p.type.rawType}`).join(', ');
        lines.push(`  async function ${action.name}(${pList}): ${action.returnType.rawType} {`);
        lines.push(`    ${this.indent(action.executionBodyCode, 4)}`);
        lines.push(`  }`);
      }
      lines.push(``);
    }

    // Return exposed members
    lines.push(`  return {`);
    for (const field of storeIR.stateFields) {
      lines.push(`    ${field.name},`);
    }
    for (const getter of storeIR.getters) {
      lines.push(`    ${getter.name},`);
    }
    for (const mutation of storeIR.mutations) {
      lines.push(`    ${mutation.name},`);
    }
    for (const action of storeIR.actions) {
      lines.push(`    ${action.name},`);
    }
    lines.push(`  };`);
    lines.push(`});\n`);

    return {
      code: lines.join('\n'),
      fileName: `${storeId}.ts`,
      framework: 'pinia',
      dependencies: [{ name: 'pinia', version: '^2.1.0', isDev: false }],
      notes: [`Generated Pinia Setup Store from UniversalStoreIR: ${storeIR.storeId}`],
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
