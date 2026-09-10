/**
 * @file angular-reactive-forms-adapter.ts
 * @description Angular 17/18 Reactive Forms AST parser and code emitter.
 * Emits Standalone Components with typed `FormGroup`, `FormControl`, `Validators`,
 * and modern built-in `@if` template control flow.
 * Conforms to Batch 32 Skill 1210 (b32-form-binding-validation).
 */

import {
  UniversalFormIR,
  FieldControlIR,
  ValidationRuleIR,
  FormParseResult,
  FormEmitResult,
} from './form-ir-types';

export class AngularReactiveFormsAdapter {
  /**
   * Parse Angular component with FormGroup into UniversalFormIR
   */
  public parse(sourceCode: string, formId: string = 'angular-form'): FormParseResult {
    const fields: FieldControlIR[] = [];
    const controlRegex = /(\w+):\s*new\s*FormControl\s*\(([^)]*)\)/g;
    let match: RegExpExecArray | null;

    while ((match = controlRegex.exec(sourceCode)) !== null) {
      if (match[1]) {
        fields.push({
          name: match[1],
          type: 'text',
          validationRules: [],
          accessibility: { label: match[1] },
        });
      }
    }

    const formIR: UniversalFormIR = {
      formId,
      formName: `${this.capitalize(formId)}Form`,
      sourceFramework: 'angular-reactive',
      fields,
      validationTrigger: 'change',
      revalidationTrigger: 'change',
    };

    return {
      success: true,
      formIR,
      errors: [],
      warnings: [],
      discoveredFramework: 'angular-reactive',
    };
  }

  /**
   * Emit Angular 17/18 Standalone component with ReactiveFormsModule from UniversalFormIR
   */
  public emit(formIR: UniversalFormIR): FormEmitResult {
    const compName = `${this.capitalize(formIR.formName)}Component`;
    const formVar = `${formIR.formId}Form`;
    const lines: string[] = [];

    lines.push(`import { Component, EventEmitter, Output } from '@angular/core';`);
    lines.push(`import { CommonModule } from '@angular/common';`);
    lines.push(`import { ReactiveFormsModule, FormGroup, FormControl, Validators } from '@angular/forms';\n`);

    lines.push(`@Component({`);
    lines.push(`  selector: 'app-${formIR.formId}',`);
    lines.push(`  standalone: true,`);
    lines.push(`  imports: [CommonModule, ReactiveFormsModule],`);
    lines.push(`  template: \``);
    lines.push(`    <form [formGroup]="${formVar}" (ngSubmit)="onSubmit()" noValidate aria-label="${formIR.formName}">`);
    lines.push(`      @if (submitError) {`);
    lines.push(`        <div role="alert" class="form-alert error-banner" aria-live="assertive">`);
    lines.push(`          {{ submitError }}`);
    lines.push(`        </div>`);
    lines.push(`      }\n`);

    for (const item of formIR.fields) {
      if ('type' in item) {
        const field = item as FieldControlIR;
        const fieldId = `field_${field.name}`;
        const errorId = `err_${field.name}`;
        const label = field.accessibility?.label || field.name;
        const isReq = field.validationRules.some((r) => r.type === 'required');

        lines.push(`      <div class="form-group" data-field="${field.name}">`);
        lines.push(`        <label for="${fieldId}">`);
        lines.push(`          ${label}${isReq ? ' <span aria-hidden="true">*</span>' : ''}`);
        lines.push(`        </label>`);

        if (field.type === 'textarea') {
          lines.push(`        <textarea`);
          lines.push(`          id="${fieldId}"`);
          lines.push(`          formControlName="${field.name}"`);
          lines.push(`          [attr.aria-invalid]="${formVar}.get('${field.name}')?.invalid && ${formVar}.get('${field.name}')?.touched"`);
          lines.push(`          [attr.aria-describedby]="${formVar}.get('${field.name}')?.invalid ? '${errorId}' : null"`);
          lines.push(`          aria-required="${isReq}"`);
          lines.push(`        ></textarea>`);
        } else if (field.type === 'checkbox') {
          lines.push(`        <input`);
          lines.push(`          id="${fieldId}"`);
          lines.push(`          type="checkbox"`);
          lines.push(`          formControlName="${field.name}"`);
          lines.push(`          [attr.aria-invalid]="${formVar}.get('${field.name}')?.invalid && ${formVar}.get('${field.name}')?.touched"`);
          lines.push(`        />`);
        } else {
          lines.push(`        <input`);
          lines.push(`          id="${fieldId}"`);
          lines.push(`          type="${field.type}"`);
          lines.push(`          formControlName="${field.name}"`);
          lines.push(`          [attr.aria-invalid]="${formVar}.get('${field.name}')?.invalid && ${formVar}.get('${field.name}')?.touched"`);
          lines.push(`          [attr.aria-describedby]="${formVar}.get('${field.name}')?.invalid ? '${errorId}' : null"`);
          lines.push(`          aria-required="${isReq}"`);
          lines.push(`        />`);
        }

        lines.push(`        @if (${formVar}.get('${field.name}')?.invalid && ${formVar}.get('${field.name}')?.touched) {`);
        lines.push(`          <p id="${errorId}" role="alert" class="form-error-msg" aria-live="polite">`);
        lines.push(`            Field is invalid`);
        lines.push(`          </p>`);
        lines.push(`        }`);
        lines.push(`      </div>\n`);
      }
    }

    lines.push(`      <button type="submit" [disabled]="${formVar}.invalid || isSubmitting" class="submit-btn">`);
    lines.push(`        {{ isSubmitting ? 'Submitting...' : 'Submit' }}`);
    lines.push(`      </button>`);
    lines.push(`    </form>`);
    lines.push(`  \`,`);
    lines.push(`})`);
    lines.push(`export class ${compName} {`);
    lines.push(`  @Output() formSubmit = new EventEmitter<any>();`);
    lines.push(`  public isSubmitting = false;`);
    lines.push(`  public submitError: string | null = null;\n`);

    lines.push(`  public ${formVar} = new FormGroup({`);
    for (const item of formIR.fields) {
      if ('type' in item) {
        const field = item as FieldControlIR;
        const validatorsStr = this.buildAngularValidators(field.validationRules);
        const defaultVal = field.defaultValueCode || "''";
        lines.push(`    ${field.name}: new FormControl(${defaultVal}, [${validatorsStr}]),`);
      }
    }
    lines.push(`  });\n`);

    lines.push(`  public onSubmit(): void {`);
    lines.push(`    if (this.${formVar}.invalid) {`);
    lines.push(`      this.${formVar}.markAllAsTouched();`);
    lines.push(`      return;`);
    lines.push(`    }`);
    lines.push(`    this.isSubmitting = true;`);
    lines.push(`    this.submitError = null;`);
    lines.push(`    try {`);
    lines.push(`      this.formSubmit.emit(this.${formVar}.value);`);
    lines.push(`    } catch (err: any) {`);
    lines.push(`      this.submitError = err?.message || 'Submission error';`);
    lines.push(`    } finally {`);
    lines.push(`      this.isSubmitting = false;`);
    lines.push(`    }`);
    lines.push(`  }`);
    lines.push(`}\n`);

    return {
      code: lines.join('\n'),
      fileName: `${compName}.ts`,
      framework: 'angular-reactive',
      dependencies: [{ name: '@angular/forms', version: '^18.0.0', isDev: false }],
      notes: [`Generated Angular Standalone Reactive Form from UniversalFormIR: ${formIR.formId}`],
    };
  }

  private buildAngularValidators(rules: ValidationRuleIR[]): string {
    const list: string[] = [];
    for (const rule of rules) {
      if (rule.type === 'required') {
        list.push('Validators.required');
      } else if (rule.type === 'email') {
        list.push('Validators.email');
      } else if (rule.type === 'min' && typeof rule.value === 'number') {
        list.push(`Validators.min(${rule.value})`);
      } else if (rule.type === 'max' && typeof rule.value === 'number') {
        list.push(`Validators.max(${rule.value})`);
      } else if (rule.type === 'minLength' && typeof rule.value === 'number') {
        list.push(`Validators.minLength(${rule.value})`);
      } else if (rule.type === 'maxLength' && typeof rule.value === 'number') {
        list.push(`Validators.maxLength(${rule.value})`);
      } else if (rule.type === 'pattern' && rule.value) {
        list.push(`Validators.pattern(${rule.value})`);
      }
    }
    return list.join(', ');
  }

  private capitalize(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
}
