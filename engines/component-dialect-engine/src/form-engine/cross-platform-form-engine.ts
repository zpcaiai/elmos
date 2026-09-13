/**
 * @file cross-platform-form-engine.ts
 * @description Master orchestration engine for cross-platform form & validation migration.
 * Converts between Zod, React Hook Form, Vue 3 VeeValidate, Angular Reactive Forms, and MiniApp Forms.
 * Conforms to Batch 32 Skill 1210 (b32-form-binding-validation).
 */

import {
  UniversalFormIR,
  FormFramework,
  FormParseResult,
  FormEmitResult,
} from './form-ir-types';
import { ZodSchemaAdapter } from './zod-schema-adapter';
import { ReactHookFormAdapter } from './react-hook-form-adapter';
import { VeeValidateAdapter } from './vee-validate-adapter';
import { AngularReactiveFormsAdapter } from './angular-reactive-forms-adapter';
import { MiniAppFormAdapter } from './miniapp-form-adapter';

export class CrossPlatformFormEngine {
  private zodAdapter = new ZodSchemaAdapter();
  private rhfAdapter = new ReactHookFormAdapter();
  private veeAdapter = new VeeValidateAdapter();
  private angularAdapter = new AngularReactiveFormsAdapter();
  private miniappAdapter = new MiniAppFormAdapter();

  /**
   * Parse form code using the appropriate framework adapter
   */
  public parse(sourceCode: string, framework: FormFramework, formId?: string): FormParseResult {
    switch (framework) {
      case 'zod':
        return this.zodAdapter.parse(sourceCode, formId);
      case 'react-hook-form':
        return this.rhfAdapter.parse(sourceCode, formId);
      case 'vee-validate':
        return this.veeAdapter.parse(sourceCode, formId);
      case 'angular-reactive':
        return this.angularAdapter.parse(sourceCode, formId);
      case 'miniapp-form':
        return this.miniappAdapter.parse(sourceCode, formId);
      default:
        // Auto-discovery
        if (sourceCode.includes('z.object')) {
          return this.zodAdapter.parse(sourceCode, formId);
        } else if (sourceCode.includes('useForm') && sourceCode.includes('register')) {
          return this.rhfAdapter.parse(sourceCode, formId);
        } else if (sourceCode.includes('FormGroup') || sourceCode.includes('FormControl')) {
          return this.angularAdapter.parse(sourceCode, formId);
        } else {
          return this.miniappAdapter.parse(sourceCode, formId);
        }
    }
  }

  /**
   * Emit code for target form framework from UniversalFormIR
   */
  public emit(formIR: UniversalFormIR, targetFramework: FormFramework): FormEmitResult {
    switch (targetFramework) {
      case 'zod':
        return this.zodAdapter.emit(formIR);
      case 'react-hook-form':
        return this.rhfAdapter.emit(formIR);
      case 'vee-validate':
        return this.veeAdapter.emit(formIR);
      case 'angular-reactive':
        return this.angularAdapter.emit(formIR);
      case 'miniapp-form':
        return this.miniappAdapter.emit(formIR);
      default:
        throw new Error(`Unsupported form target framework: ${targetFramework}`);
    }
  }

  /**
   * Complete end-to-end form transformation
   */
  public transform(
    sourceCode: string,
    sourceFramework: FormFramework,
    targetFramework: FormFramework,
    formId?: string
  ): { emitResult: FormEmitResult; parseResult: FormParseResult } {
    const parseResult = this.parse(sourceCode, sourceFramework, formId);
    if (!parseResult.success || !parseResult.formIR) {
      throw new Error(`Failed to parse form: ${parseResult.errors.join(', ')}`);
    }

    const emitResult = this.emit(parseResult.formIR, targetFramework);
    return { emitResult, parseResult };
  }
}
