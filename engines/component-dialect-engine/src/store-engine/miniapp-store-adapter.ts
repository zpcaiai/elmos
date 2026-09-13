/**
 * @file miniapp-store-adapter.ts
 * @description WeChat MiniApp Observable State Store parser and code emitter.
 * Provides a lightweight reactive state management pattern for MiniApps with:
 * - EventEmitter state updates
 * - Selective `setData` binding to current active pages/components
 * - Native storage synchronization (`wx.setStorageSync` / `wx.getStorageSync`)
 * - Conforms to Batch 32 Skill 1209 (b32-state-management-lifecycle).
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
} from './store-ir-types';

export class MiniAppStoreAdapter {
  /**
   * Parse MiniApp store file into UniversalStoreIR
   */
  public parse(sourceCode: string, storeId: string = 'app-store'): StoreParseResult {
    const errors: string[] = [];
    const warnings: string[] = [];
    const sourceFile = ts.createSourceFile(
      'miniapp-store.ts',
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    );

    const stateFields: StateFieldIR[] = [];
    const getters: StoreGetterIR[] = [];
    const mutations: StoreMutationIR[] = [];
    const actions: StoreAsyncActionIR[] = [];

    const visit = (node: ts.Node) => {
      // Find `class ...Store` or `const store = new MiniAppStore({ state: ... })`
      if (ts.isClassDeclaration(node)) {
        for (const member of node.members) {
          if (ts.isPropertyDeclaration(member)) {
            const name = member.name.getText(sourceFile);
            if (name === 'state' && member.initializer && ts.isObjectLiteralExpression(member.initializer)) {
              for (const prop of member.initializer.properties) {
                if (ts.isPropertyAssignment(prop)) {
                  stateFields.push({
                    name: prop.name.getText(sourceFile),
                    type: { rawType: 'any', kind: 'custom', nullable: false, optional: false },
                    initialValueCode: prop.initializer.getText(sourceFile),
                    isPersisted: false,
                    isSensitive: false,
                  });
                }
              }
            }
          } else if (ts.isMethodDeclaration(member)) {
            const name = member.name.getText(sourceFile);
            const isAsync = member.modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword);
            if (isAsync) {
              actions.push({
                name,
                parameters: member.parameters.map((p) => ({
                  name: p.name.getText(sourceFile),
                  type: { rawType: p.type ? p.type.getText(sourceFile) : 'any', kind: 'custom', nullable: false, optional: false },
                })),
                returnType: { rawType: 'Promise<void>', kind: 'custom', nullable: false, optional: false },
                executionBodyCode: member.body ? member.body.getText(sourceFile) : '{}',
                dispatchedMutations: [],
              });
            } else {
              mutations.push({
                name,
                parameters: member.parameters.map((p) => ({
                  name: p.name.getText(sourceFile),
                  type: { rawType: p.type ? p.type.getText(sourceFile) : 'any', kind: 'custom', nullable: false, optional: false },
                })),
                mutationBodyCode: member.body ? member.body.getText(sourceFile) : '{}',
                affectedFields: [],
                isPure: false,
              });
            }
          }
        }
      }
      ts.forEachChild(node, visit);
    };

    visit(sourceFile);

    const storeIR: UniversalStoreIR = {
      storeId,
      storeName: `${storeId}Store`,
      sourceFramework: 'miniapp-store',
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
      discoveredFramework: 'miniapp-store',
    };
  }

  /**
   * Emit MiniApp reactive observable store TypeScript code from UniversalStoreIR
   */
  public emit(storeIR: UniversalStoreIR): StoreEmitResult {
    const lines: string[] = [];
    const className = `${this.capitalize(storeIR.storeName)}Store`;
    const typeName = `${this.capitalize(storeIR.storeName)}State`;

    lines.push(`/**`);
    lines.push(` * WeChat MiniApp Observable State Store`);
    lines.push(` * Automatically bridges state changes to active Page / Component setData()`);
    lines.push(` */\n`);

    lines.push(`type Listener<T> = (newState: T, oldState: T) => void;\n`);

    // State interface
    lines.push(`export interface ${typeName} {`);
    for (const field of storeIR.stateFields) {
      lines.push(`  ${field.name}: ${field.type.rawType};`);
    }
    lines.push(`}\n`);

    // Store Class
    lines.push(`export class ${className} {`);
    lines.push(`  private static instance: ${className};`);
    lines.push(`  private listeners: Set<Listener<${typeName}>> = new Set();`);
    lines.push(`  public state: ${typeName};\n`);

    // Constructor
    lines.push(`  private constructor() {`);
    lines.push(`    // Initial state`);
    lines.push(`    this.state = {`);
    for (const field of storeIR.stateFields) {
      lines.push(`      ${field.name}: ${field.initialValueCode},`);
    }
    lines.push(`    };`);

    if (storeIR.persistence) {
      lines.push(`    // Restore from wx.getStorageSync`);
      lines.push(`    try {`);
      lines.push(`      const cached = wx.getStorageSync('${storeIR.persistence.storageKey}');`);
      lines.push(`      if (cached && typeof cached === 'object') {`);
      lines.push(`        this.state = { ...this.state, ...cached };`);
      lines.push(`      }`);
      lines.push(`    } catch (e) {`);
      lines.push(`      console.warn('[MiniAppStore] Failed to restore cached state:', e);`);
      lines.push(`    }`);
    }
    lines.push(`  }\n`);

    // Singleton getInstance
    lines.push(`  public static getInstance(): ${className} {`);
    lines.push(`    if (!${className}.instance) {`);
    lines.push(`      ${className}.instance = new ${className}();`);
    lines.push(`    }`);
    lines.push(`    return ${className}.instance;`);
    lines.push(`  }\n`);

    // Subscribe / Unsubscribe
    lines.push(`  public subscribe(listener: Listener<${typeName}>): () => void {`);
    lines.push(`    this.listeners.add(listener);`);
    lines.push(`    return () => this.listeners.delete(listener);`);
    lines.push(`  }\n`);

    // Connect to Page / Component helper
    lines.push(`  public connect(pageOrComponent: any, keyMap?: Record<string, keyof ${typeName}>): () => void {`);
    lines.push(`    const update = (state: ${typeName}) => {`);
    lines.push(`      if (typeof pageOrComponent.setData !== 'function') return;`);
    lines.push(`      if (!keyMap) {`);
    lines.push(`        pageOrComponent.setData(state);`);
    lines.push(`      } else {`);
    lines.push(`        const diff: Record<string, any> = {};`);
    lines.push(`        for (const [targetKey, stateKey] of Object.entries(keyMap)) {`);
    lines.push(`          diff[targetKey] = state[stateKey];`);
    lines.push(`        }`);
    lines.push(`        pageOrComponent.setData(diff);`);
    lines.push(`      }`);
    lines.push(`    };`);
    lines.push(`    update(this.state);`);
    lines.push(`    return this.subscribe(update);`);
    lines.push(`  }\n`);

    // SetState
    lines.push(`  public setState(partial: Partial<${typeName}>): void {`);
    lines.push(`    const oldState = { ...this.state };`);
    lines.push(`    this.state = { ...this.state, ...partial };`);
    if (storeIR.persistence) {
      lines.push(`    try {`);
      lines.push(`      wx.setStorageSync('${storeIR.persistence.storageKey}', this.state);`);
      lines.push(`    } catch (err) {`);
      lines.push(`      console.error('[MiniAppStore] Failed to persist state:', err);`);
      lines.push(`    }`);
    }
    lines.push(`    for (const listener of this.listeners) {`);
    lines.push(`      listener(this.state, oldState);`);
    lines.push(`    }`);
    lines.push(`  }\n`);

    // Getters
    for (const getter of storeIR.getters) {
      lines.push(`  public get ${getter.name}(): ${getter.returnType.rawType} {`);
      lines.push(`    ${this.indent(getter.computationBodyCode, 4)}`);
      lines.push(`  }\n`);
    }

    // Synchronous Mutations
    for (const mutation of storeIR.mutations) {
      const pList = mutation.parameters.map((p) => `${p.name}: ${p.type.rawType}`).join(', ');
      lines.push(`  public ${mutation.name}(${pList}): void {`);
      lines.push(`    ${this.indent(mutation.mutationBodyCode, 4)}`);
      lines.push(`  }\n`);
    }

    // Async Actions
    for (const action of storeIR.actions) {
      const pList = action.parameters.map((p) => `${p.name}: ${p.type.rawType}`).join(', ');
      lines.push(`  public async ${action.name}(${pList}): ${action.returnType.rawType} {`);
      lines.push(`    ${this.indent(action.executionBodyCode, 4)}`);
      lines.push(`  }\n`);
    }

    lines.push(`}\n`);
    lines.push(`export const store = ${className}.getInstance();\n`);

    return {
      code: lines.join('\n'),
      fileName: `${storeIR.storeId}Store.ts`,
      framework: 'miniapp-store',
      dependencies: [],
      notes: [`Generated WeChat MiniApp observable store from UniversalStoreIR: ${storeIR.storeId}`],
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
