/**
 * @file zod-schema-adapter.ts
 * @description Zod Schema AST Parser and Code Emitter.
 * Parses `z.object({...})`, chaining validators (`min`, `max`, `email`, `regex`),
 * and `.refine()` / `.superRefine()`, lifting into UniversalFormIR.
 * Emits clean TypeScript Zod schemas.
 * Conforms to Batch 32 Skill 1210 (b32-form-binding-validation).
 */

import * as ts from 'typescript';
import {
  UniversalFormIR,
  FieldControlIR,
  ValidationRuleIR,
  FormParseResult,
  FormEmitResult,
} from './form-ir-types';

export class ZodSchemaAdapter {
  /**
   * Parse Zod schema TypeScript source into UniversalFormIR
   */
  public parse(sourceCode: string, formId: string = 'app-form'): FormParseResult {
    const errors: string[] = [];
    const warnings: string[] = [];
    const sourceFile = ts.createSourceFile(
      'schema.ts',
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    );

    const fields: FieldControlIR[] = [];
    const crossFieldRules: ValidationRuleIR[] = [];
    let formName = formId;

    const visit = (node: ts.Node) => {
      // Look for `export const ...Schema = z.object({ ... })`
      if (ts.isVariableDeclaration(node) && node.initializer) {
        const varName = node.name.getText(sourceFile);
        if (varName.toLowerCase().includes('schema') || varName.toLowerCase().includes('form')) {
          formName = varName;
        }

        this.inspectZodExpression(node.initializer, sourceFile, fields, crossFieldRules, errors);
      }
      ts.forEachChild(node, visit);
    };

    visit(sourceFile);

    const formIR: UniversalFormIR = {
      formId,
      formName,
      sourceFramework: 'zod',
      fields,
      crossFieldRules,
      validationTrigger: 'change',
      revalidationTrigger: 'change',
    };

    return {
      success: errors.length === 0,
      formIR,
      errors,
      warnings,
      discoveredFramework: 'zod',
    };
  }

  private inspectZodExpression(
    expr: ts.Expression,
    sourceFile: ts.SourceFile,
    fields: FieldControlIR[],
    crossFieldRules: ValidationRuleIR[],
    errors: string[]
  ) {
    let current: ts.Expression = expr;

    // Handle `.refine(...)` chains
    while (ts.isCallExpression(current)) {
      const call = current;
      if (ts.isPropertyAccessExpression(call.expression)) {
        const method = call.expression.name.getText(sourceFile);
        if (method === 'refine' || method === 'superRefine') {
          const messageArg = call.arguments[1];
          const msg = messageArg ? messageArg.getText(sourceFile).replace(/['"]/g, '') : 'Validation failed';
          const validatorArg = call.arguments[0];
          crossFieldRules.push({
            type: 'crossField',
            message: msg,
            customValidatorCode: validatorArg ? validatorArg.getText(sourceFile) : '',
          });
        } else if (method === 'object') {
          const objArg = call.arguments[0];
          if (objArg && ts.isObjectLiteralExpression(objArg)) {
            this.parseZodObjectProperties(objArg, sourceFile, fields);
          }
        }
        current = call.expression.expression;
      } else {
        break;
      }
    }
  }

  private parseZodObjectProperties(
    obj: ts.ObjectLiteralExpression,
    sourceFile: ts.SourceFile,
    fields: FieldControlIR[]
  ) {
    for (const prop of obj.properties) {
      if (ts.isPropertyAssignment(prop)) {
        const fieldName = prop.name.getText(sourceFile);
        const rules: ValidationRuleIR[] = [];
        let fieldType: FieldControlIR['type'] = 'text';

        let callExpr: ts.Expression = prop.initializer;

        // Traverse method calls e.g. z.string().min(1).email()
        while (ts.isCallExpression(callExpr)) {
          if (ts.isPropertyAccessExpression(callExpr.expression)) {
            const method = callExpr.expression.name.getText(sourceFile);
            const args = callExpr.arguments;

            if (method === 'string') {
              fieldType = 'text';
            } else if (method === 'number') {
              fieldType = 'number';
            } else if (method === 'boolean') {
              fieldType = 'checkbox';
            } else if (method === 'email') {
              fieldType = 'email';
              const msg = args[0] ? args[0].getText(sourceFile).replace(/['"]/g, '') : 'Invalid email address';
              rules.push({ type: 'email', message: msg });
            } else if (method === 'url') {
              const msg = args[0] ? args[0].getText(sourceFile).replace(/['"]/g, '') : 'Invalid URL';
              rules.push({ type: 'url', message: msg });
            } else if (method === 'min') {
              const val = args[0] ? Number(args[0].getText(sourceFile)) : 0;
              const msg = args[1] ? args[1].getText(sourceFile).replace(/['"]/g, '') : `Minimum value is ${val}`;
              if (fieldType === 'number') {
                rules.push({ type: 'min', value: val, message: msg });
              } else {
                if (val === 1) {
                  rules.push({ type: 'required', message: msg });
                } else {
                  rules.push({ type: 'minLength', value: val, message: msg });
                }
              }
            } else if (method === 'max') {
              const val = args[0] ? Number(args[0].getText(sourceFile)) : 0;
              const msg = args[1] ? args[1].getText(sourceFile).replace(/['"]/g, '') : `Maximum value is ${val}`;
              if (fieldType === 'number') {
                rules.push({ type: 'max', value: val, message: msg });
              } else {
                rules.push({ type: 'maxLength', value: val, message: msg });
              }
            } else if (method === 'regex') {
              const pattern = args[0] ? args[0].getText(sourceFile) : '';
              const msg = args[1] ? args[1].getText(sourceFile).replace(/['"]/g, '') : 'Invalid format';
              rules.push({ type: 'pattern', value: pattern, message: msg });
            }

            callExpr = callExpr.expression.expression;
          } else {
            break;
          }
        }

        fields.push({
          name: fieldName,
          type: fieldType,
          validationRules: rules,
          accessibility: {
            label: this.toHumanLabel(fieldName),
            ariaRequired: rules.some((r) => r.type === 'required'),
          },
        });
      }
    }
  }

  private toHumanLabel(key: string): string {
    return key
      .replace(/([A-Z])/g, ' $1')
      .replace(/_/g, ' ')
      .replace(/^\w/, (c) => c.toUpperCase())
      .trim();
  }

  /**
   * Emit Zod Schema TypeScript code from UniversalFormIR
   */
  public emit(formIR: UniversalFormIR): FormEmitResult {
    const lines: string[] = [];
    lines.push(`import { z } from 'zod';\n`);

    const schemaName = formIR.formName.endsWith('Schema') ? formIR.formName : `${formIR.formName}Schema`;
    const typeName = formIR.formName.replace(/Schema$/i, '') + 'FormData';

    lines.push(`export const ${schemaName} = z.object({`);

    for (const item of formIR.fields) {
      if ('type' in item) {
        const field = item as FieldControlIR;
        const zodChain = this.buildZodChain(field);
        lines.push(`  ${field.name}: ${zodChain},`);
      }
    }

    lines.push(`});\n`);

    lines.push(`export type ${typeName} = z.infer<typeof ${schemaName}>;\n`);

    return {
      code: lines.join('\n'),
      fileName: `${schemaName}.ts`,
      framework: 'zod',
      dependencies: [{ name: 'zod', version: '^3.23.0', isDev: false }],
      notes: [`Generated Zod schema from UniversalFormIR: ${formIR.formId}`],
    };
  }

  private buildZodChain(field: FieldControlIR): string {
    let chain = '';
    if (field.type === 'number') {
      chain = 'z.number()';
    } else if (field.type === 'checkbox' || field.type === 'switch') {
      chain = 'z.boolean()';
    } else if (field.type === 'date') {
      chain = 'z.date()';
    } else {
      chain = 'z.string()';
    }

    for (const rule of field.validationRules) {
      if (rule.type === 'required') {
        if (field.type === 'text' || field.type === 'email' || field.type === 'password' || field.type === 'textarea') {
          chain += `.min(1, { message: '${this.escapeStr(rule.message)}' })`;
        }
      } else if (rule.type === 'email') {
        chain += `.email({ message: '${this.escapeStr(rule.message)}' })`;
      } else if (rule.type === 'url') {
        chain += `.url({ message: '${this.escapeStr(rule.message)}' })`;
      } else if (rule.type === 'min' && typeof rule.value === 'number') {
        chain += `.min(${rule.value}, { message: '${this.escapeStr(rule.message)}' })`;
      } else if (rule.type === 'max' && typeof rule.value === 'number') {
        chain += `.max(${rule.value}, { message: '${this.escapeStr(rule.message)}' })`;
      } else if (rule.type === 'minLength' && typeof rule.value === 'number') {
        chain += `.min(${rule.value}, { message: '${this.escapeStr(rule.message)}' })`;
      } else if (rule.type === 'maxLength' && typeof rule.value === 'number') {
        chain += `.max(${rule.value}, { message: '${this.escapeStr(rule.message)}' })`;
      } else if (rule.type === 'pattern' && rule.value) {
        chain += `.regex(${rule.value}, { message: '${this.escapeStr(rule.message)}' })`;
      }
    }

    return chain;
  }

  private escapeStr(str: string): string {
    return str.replace(/'/g, "\\'");
  }
}
