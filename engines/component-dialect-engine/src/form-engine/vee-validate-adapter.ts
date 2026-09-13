/**
 * @file vee-validate-adapter.ts
 * @description Vue 3 VeeValidate form generator and parser.
 * Generates modern Vue 3 `<script setup>` SFC with VeeValidate 4 `useForm`,
 * `defineField`, and accessible form templates.
 * Conforms to Batch 32 Skill 1210 (b32-form-binding-validation).
 */

import {
  UniversalFormIR,
  FieldControlIR,
  FormParseResult,
  FormEmitResult,
} from './form-ir-types';

export class VeeValidateAdapter {
  /**
   * Parse Vue 3 SFC using VeeValidate into UniversalFormIR
   */
  public parse(sourceCode: string, formId: string = 'vue-form'): FormParseResult {
    // Basic parser for Vue 3 SFC containing VeeValidate
    const fields: FieldControlIR[] = [];
    const defineFieldRegex = /const\s*\[\s*(\w+)/g;
    let match: RegExpExecArray | null;

    while ((match = defineFieldRegex.exec(sourceCode)) !== null) {
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
      sourceFramework: 'vee-validate',
      fields,
      validationTrigger: 'blur',
      revalidationTrigger: 'change',
    };

    return {
      success: true,
      formIR,
      errors: [],
      warnings: [],
      discoveredFramework: 'vee-validate',
    };
  }

  /**
   * Emit Vue 3 SFC with VeeValidate from UniversalFormIR
   */
  public emit(formIR: UniversalFormIR): FormEmitResult {
    const compName = `${this.capitalize(formIR.formName)}Component`;
    const schemaName = `${formIR.formName}Schema`;
    const lines: string[] = [];

    lines.push(`<template>`);
    lines.push(`  <form @submit.prevent="onSubmit" noValidate aria-label="${formIR.formName}">`);
    lines.push(`    <div v-if="submitError" role="alert" class="form-alert error-banner" aria-live="assertive">`);
    lines.push(`      {{ submitError }}`);
    lines.push(`    </div>\n`);

    for (const item of formIR.fields) {
      if ('type' in item) {
        const field = item as FieldControlIR;
        const fieldId = `field_${field.name}`;
        const errorId = `err_${field.name}`;
        const label = field.accessibility?.label || field.name;
        const isReq = field.validationRules.some((r) => r.type === 'required');

        lines.push(`    <div class="form-group" data-field="${field.name}">`);
        lines.push(`      <label for="${fieldId}">`);
        lines.push(`        ${label}${isReq ? ' <span aria-hidden="true">*</span>' : ''}`);
        lines.push(`      </label>`);

        if (field.type === 'textarea') {
          lines.push(`      <textarea`);
          lines.push(`        id="${fieldId}"`);
          lines.push(`        v-model="${field.name}"`);
          lines.push(`        v-bind="${field.name}Attrs"`);
          lines.push(`        :aria-invalid="!!errors.${field.name}"`);
          lines.push(`        :aria-describedby="errors.${field.name} ? '${errorId}' : undefined"`);
          lines.push(`        aria-required="${isReq}"`);
          lines.push(`        :disabled="isSubmitting"`);
          lines.push(`      />`);
        } else if (field.type === 'checkbox') {
          lines.push(`      <input`);
          lines.push(`        id="${fieldId}"`);
          lines.push(`        type="checkbox"`);
          lines.push(`        v-model="${field.name}"`);
          lines.push(`        v-bind="${field.name}Attrs"`);
          lines.push(`        :aria-invalid="!!errors.${field.name}"`);
          lines.push(`        :disabled="isSubmitting"`);
          lines.push(`      />`);
        } else {
          lines.push(`      <input`);
          lines.push(`        id="${fieldId}"`);
          lines.push(`        type="${field.type}"`);
          lines.push(`        v-model="${field.name}"`);
          lines.push(`        v-bind="${field.name}Attrs"`);
          lines.push(`        :aria-invalid="!!errors.${field.name}"`);
          lines.push(`        :aria-describedby="errors.${field.name} ? '${errorId}' : undefined"`);
          lines.push(`        aria-required="${isReq}"`);
          lines.push(`        :disabled="isSubmitting"`);
          lines.push(`      />`);
        }

        lines.push(`      <p v-if="errors.${field.name}" id="${errorId}" role="alert" class="form-error-msg" aria-live="polite">`);
        lines.push(`        {{ errors.${field.name} }}`);
        lines.push(`      </p>`);
        lines.push(`    </div>\n`);
      }
    }

    lines.push(`    <button type="submit" :disabled="isSubmitting" class="submit-btn">`);
    lines.push(`      {{ isSubmitting ? 'Submitting...' : 'Submit' }}`);
    lines.push(`    </button>`);
    lines.push(`  </form>`);
    lines.push(`</template>\n`);

    lines.push(`<script setup lang="ts">`);
    lines.push(`import { ref } from 'vue';`);
    lines.push(`import { useForm } from 'vee-validate';`);
    lines.push(`import { toTypedSchema } from '@vee-validate/zod';`);
    lines.push(`import { ${schemaName} } from './${schemaName}';\n`);

    lines.push(`const emit = defineEmits<{`);
    lines.push(`  (e: 'submit', values: any): void;`);
    lines.push(`}>();\n`);

    lines.push(`const submitError = ref<string | null>(null);`);
    lines.push(`const { errors, handleSubmit, isSubmitting, defineField } = useForm({`);
    lines.push(`  validationSchema: toTypedSchema(${schemaName}),`);
    lines.push(`});\n`);

    for (const item of formIR.fields) {
      if ('type' in item) {
        const field = item as FieldControlIR;
        lines.push(`const [${field.name}, ${field.name}Attrs] = defineField('${field.name}');`);
      }
    }

    lines.push(`\nconst onSubmit = handleSubmit(async (values) => {`);
    lines.push(`  try {`);
    lines.push(`    submitError.value = null;`);
    lines.push(`    emit('submit', values);`);
    lines.push(`  } catch (err: any) {`);
    lines.push(`    submitError.value = err?.message || 'Submission failed';`);
    lines.push(`  }`);
    lines.push(`});`);
    lines.push(`</script>\n`);

    return {
      code: lines.join('\n'),
      fileName: `${compName}.vue`,
      framework: 'vee-validate',
      dependencies: [
        { name: 'vee-validate', version: '^4.12.0', isDev: false },
        { name: '@vee-validate/zod', version: '^4.12.0', isDev: false },
        { name: 'zod', version: '^3.23.0', isDev: false },
      ],
      notes: [`Generated Vue 3 VeeValidate component from UniversalFormIR: ${formIR.formId}`],
    };
  }

  private capitalize(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
}
