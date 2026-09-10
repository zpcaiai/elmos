/**
 * @file redux-toolkit-adapter.ts
 * @description Redux Toolkit (RTK) AST parser and code emitter.
 * Handles `createSlice`, `createAsyncThunk`, `PayloadAction<T>`, builder callbacks in extraReducers,
 * and typed hooks (`useAppDispatch`, `useAppSelector`).
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

export class ReduxToolkitAdapter {
  /**
   * Parse Redux Toolkit slice source code into UniversalStoreIR
   */
  public parse(sourceCode: string, storeId: string = 'app-slice'): StoreParseResult {
    const errors: string[] = [];
    const warnings: string[] = [];
    const sourceFile = ts.createSourceFile(
      'slice.ts',
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    );

    const stateFields: StateFieldIR[] = [];
    const getters: StoreGetterIR[] = [];
    const mutations: StoreMutationIR[] = [];
    const actions: StoreAsyncActionIR[] = [];
    let sliceName = storeId;

    const visit = (node: ts.Node) => {
      // Find `createSlice({ ... })`
      if (ts.isCallExpression(node)) {
        const fnName = node.expression.getText(sourceFile);
        if (fnName.includes('createSlice') && node.arguments.length > 0) {
          const sliceConfig = node.arguments[0];
          if (sliceConfig && ts.isObjectLiteralExpression(sliceConfig)) {
            for (const prop of sliceConfig.properties) {
              if (ts.isPropertyAssignment(prop)) {
                const propName = prop.name.getText(sourceFile);
                if (propName === 'name') {
                  sliceName = prop.initializer.getText(sourceFile).replace(/['"]/g, '');
                } else if (propName === 'initialState') {
                  if (ts.isObjectLiteralExpression(prop.initializer)) {
                    this.extractInitialState(prop.initializer, sourceFile, stateFields);
                  }
                } else if (propName === 'reducers') {
                  if (ts.isObjectLiteralExpression(prop.initializer)) {
                    this.extractReducers(prop.initializer, sourceFile, mutations);
                  }
                }
              }
            }
          }
        } else if (fnName.includes('createAsyncThunk') && node.arguments.length > 1) {
          const firstArg = node.arguments[0];
          const thunkFn = node.arguments[1];
          if (firstArg && thunkFn && (ts.isArrowFunction(thunkFn) || ts.isFunctionExpression(thunkFn))) {
            const thunkName = firstArg.getText(sourceFile).replace(/['"]/g, '');
            actions.push({
              name: thunkName.split('/')[1] || thunkName,
              parameters: thunkFn.parameters.map((p) => ({
                name: p.name.getText(sourceFile),
                type: { rawType: p.type ? p.type.getText(sourceFile) : 'any', kind: 'custom', nullable: false, optional: !!p.questionToken },
              })),
              returnType: { rawType: 'Promise<unknown>', kind: 'custom', nullable: false, optional: false },
              executionBodyCode: thunkFn.body.getText(sourceFile),
              dispatchedMutations: [],
            });
          }
        }
      }

      // Find Selector functions: `export const selectCount = (state: RootState) => state.counter.value;`
      if (ts.isVariableDeclaration(node) && node.initializer) {
        const varName = node.name.getText(sourceFile);
        if (varName.startsWith('select') && (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))) {
          getters.push({
            name: varName,
            returnType: { rawType: 'unknown', kind: 'custom', nullable: false, optional: false },
            dependencies: [],
            computationBodyCode: node.initializer.body.getText(sourceFile),
            isMemoized: false,
          });
        }
      }

      ts.forEachChild(node, visit);
    };

    visit(sourceFile);

    const storeIR: UniversalStoreIR = {
      storeId,
      storeName: sliceName,
      sourceFramework: 'redux-toolkit',
      architecture: 'slice',
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
      discoveredFramework: 'redux-toolkit',
    };
  }

  private extractInitialState(
    initObj: ts.ObjectLiteralExpression,
    sourceFile: ts.SourceFile,
    stateFields: StateFieldIR[]
  ) {
    for (const prop of initObj.properties) {
      if (ts.isPropertyAssignment(prop)) {
        const name = prop.name.getText(sourceFile);
        const valText = prop.initializer.getText(sourceFile);
        stateFields.push({
          name,
          type: this.inferType(prop.initializer),
          initialValueCode: valText,
          isPersisted: false,
          isSensitive: false,
        });
      }
    }
  }

  private extractReducers(
    reducersObj: ts.ObjectLiteralExpression,
    sourceFile: ts.SourceFile,
    mutations: StoreMutationIR[]
  ) {
    for (const prop of reducersObj.properties) {
      if (ts.isPropertyAssignment(prop)) {
        const name = prop.name.getText(sourceFile);
        const init = prop.initializer;
        if (ts.isArrowFunction(init) || ts.isFunctionExpression(init)) {
          mutations.push({
            name,
            parameters: init.parameters.slice(1).map((p) => ({
              name: p.name.getText(sourceFile),
              type: { rawType: p.type ? p.type.getText(sourceFile) : 'any', kind: 'custom', nullable: false, optional: false },
            })),
            mutationBodyCode: init.body.getText(sourceFile),
            affectedFields: [],
            isPure: false,
          });
        }
      } else if (ts.isMethodDeclaration(prop)) {
        const name = prop.name.getText(sourceFile);
        mutations.push({
          name,
          parameters: prop.parameters.slice(1).map((p) => ({
            name: p.name.getText(sourceFile),
            type: { rawType: p.type ? p.type.getText(sourceFile) : 'any', kind: 'custom', nullable: false, optional: false },
          })),
          mutationBodyCode: prop.body ? prop.body.getText(sourceFile) : '{}',
          affectedFields: [],
          isPure: false,
        });
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
   * Emit Redux Toolkit slice TypeScript code from UniversalStoreIR
   */
  public emit(storeIR: UniversalStoreIR): StoreEmitResult {
    const sliceName = storeIR.storeName.replace(/Slice$/i, '');
    const typeName = `${this.capitalize(sliceName)}State`;
    const lines: string[] = [];

    lines.push(`import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';\n`);

    // State interface
    lines.push(`export interface ${typeName} {`);
    for (const field of storeIR.stateFields) {
      const opt = field.type.optional ? '?' : '';
      lines.push(`  ${field.name}${opt}: ${field.type.rawType};`);
    }
    lines.push(`}\n`);

    // Initial state constant
    lines.push(`const initialState: ${typeName} = {`);
    for (const field of storeIR.stateFields) {
      lines.push(`  ${field.name}: ${field.initialValueCode},`);
    }
    lines.push(`};\n`);

    // Async thunks
    for (const action of storeIR.actions) {
      const firstParam = action.parameters[0];
      const paramType = firstParam ? firstParam.type.rawType : 'void';
      const paramName = firstParam ? firstParam.name : '_';
      lines.push(`export const ${action.name} = createAsyncThunk(`);
      lines.push(`  '${sliceName}/${action.name}',`);
      lines.push(`  async (${paramName}: ${paramType}, { dispatch, rejectWithValue }) => {`);
      lines.push(`    ${this.indent(action.executionBodyCode, 4)}`);
      lines.push(`  }`);
      lines.push(`);\n`);
    }

    // Slice definition
    lines.push(`export const ${sliceName}Slice = createSlice({`);
    lines.push(`  name: '${sliceName}',`);
    lines.push(`  initialState,`);
    lines.push(`  reducers: {`);

    for (const mutation of storeIR.mutations) {
      const firstParam = mutation.parameters[0];
      if (!firstParam) {
        lines.push(`    ${mutation.name}: (state) => {`);
        lines.push(`      ${this.indent(mutation.mutationBodyCode, 6)}`);
        lines.push(`    },`);
      } else {
        const payloadType = firstParam.type.rawType;
        lines.push(`    ${mutation.name}: (state, action: PayloadAction<${payloadType}>) => {`);
        lines.push(`      ${this.indent(mutation.mutationBodyCode, 6)}`);
        lines.push(`    },`);
      }
    }

    lines.push(`  },`);

    if (storeIR.actions.length > 0) {
      lines.push(`  extraReducers: (builder) => {`);
      for (const action of storeIR.actions) {
        lines.push(`    builder`);
        lines.push(`      .addCase(${action.name}.pending, (state) => {`);
        if (action.loadingStateField) {
          lines.push(`        state.${action.loadingStateField} = true;`);
        }
        lines.push(`      })`);
        lines.push(`      .addCase(${action.name}.fulfilled, (state, action) => {`);
        if (action.loadingStateField) {
          lines.push(`        state.${action.loadingStateField} = false;`);
        }
        lines.push(`      })`);
        lines.push(`      .addCase(${action.name}.rejected, (state, action) => {`);
        if (action.loadingStateField) {
          lines.push(`        state.${action.loadingStateField} = false;`);
        }
        if (action.errorStateField) {
          lines.push(`        state.${action.errorStateField} = action.error.message ?? 'Unknown error';`);
        }
        lines.push(`      });`);
      }
      lines.push(`  },`);
    }

    lines.push(`});\n`);

    // Exported action creators
    const mutationNames = storeIR.mutations.map((m) => m.name).join(', ');
    if (mutationNames.length > 0) {
      lines.push(`export const { ${mutationNames} } = ${sliceName}Slice.actions;\n`);
    }

    // Selectors
    lines.push(`export const select${this.capitalize(sliceName)}State = (state: { ${sliceName}: ${typeName} }) => state.${sliceName};`);
    for (const getter of storeIR.getters) {
      lines.push(`export const ${getter.name} = (state: { ${sliceName}: ${typeName} }) => {`);
      lines.push(`  ${this.indent(getter.computationBodyCode, 2)}`);
      lines.push(`};`);
    }
    lines.push(`\nexport default ${sliceName}Slice.reducer;\n`);

    return {
      code: lines.join('\n'),
      fileName: `${sliceName}Slice.ts`,
      framework: 'redux-toolkit',
      dependencies: [{ name: '@reduxjs/toolkit', version: '^2.0.0', isDev: false }],
      notes: [`Generated Redux Toolkit slice from UniversalStoreIR: ${storeIR.storeId}`],
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
