/**
 * @file miniapp-form-adapter.ts
 * @description WeChat MiniApp Form WXML & Controller code generator.
 * Emits declarative WXML form bindings with native WeChat MiniApp form controls,
 * runtime input validation, inline error messaging, and double-submit prevention.
 * Conforms to Batch 32 Skill 1210 (b32-form-binding-validation).
 */

import {
  UniversalFormIR,
  FieldControlIR,
  FormParseResult,
  FormEmitResult,
} from './form-ir-types';

export class MiniAppFormAdapter {
  /**
   * Parse MiniApp form into UniversalFormIR
   */
  public parse(sourceCode: string, formId: string = 'miniapp-form'): FormParseResult {
    const fields: FieldControlIR[] = [];
    const fieldRegex = /data-field="(\w+)"/g;
    let match: RegExpExecArray | null;

    while ((match = fieldRegex.exec(sourceCode)) !== null) {
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
      sourceFramework: 'miniapp-form',
      fields,
      validationTrigger: 'blur',
      revalidationTrigger: 'change',
    };

    return {
      success: true,
      formIR,
      errors: [],
      warnings: [],
      discoveredFramework: 'miniapp-form',
    };
  }

  /**
   * Emit MiniApp WXML template and JS/TS controller code from UniversalFormIR
   */
  public emit(formIR: UniversalFormIR): FormEmitResult {
    const wxmlLines: string[] = [];
    const tsLines: string[] = [];

    // --- WXML Template ---
    wxmlLines.push(`<!-- WeChat MiniApp Form Template: ${formIR.formId} -->`);
    wxmlLines.push(`<view class="form-container">`);
    wxmlLines.push(`  <view wx:if="{{submitError}}" class="form-alert error-banner">`);
    wxmlLines.push(`    <text>{{submitError}}</text>`);
    wxmlLines.push(`  </view>`);
    wxmlLines.push(`  <form bindsubmit="onFormSubmit">`);

    for (const item of formIR.fields) {
      if ('type' in item) {
        const field = item as FieldControlIR;
        const label = field.accessibility?.label || field.name;
        const isReq = field.validationRules.some((r) => r.type === 'required');

        wxmlLines.push(`    <view class="form-group" data-field="${field.name}">`);
        wxmlLines.push(`      <view class="label-wrapper">`);
        wxmlLines.push(`        <text class="field-label">${label}</text>`);
        if (isReq) {
          wxmlLines.push(`        <text class="required-star">*</text>`);
        }
        wxmlLines.push(`      </view>`);

        if (field.type === 'textarea') {
          wxmlLines.push(`      <textarea`);
          wxmlLines.push(`        class="form-control {{errors.${field.name} ? 'is-invalid' : ''}}"`);
          wxmlLines.push(`        value="{{formData.${field.name}}}"`);
          wxmlLines.push(`        data-field="${field.name}"`);
          wxmlLines.push(`        bindinput="onFieldInput"`);
          wxmlLines.push(`        bindblur="onFieldBlur"`);
          wxmlLines.push(`        disabled="{{isSubmitting}}"`);
          wxmlLines.push(`      />`);
        } else if (field.type === 'checkbox' || field.type === 'switch') {
          wxmlLines.push(`      <switch`);
          wxmlLines.push(`        checked="{{formData.${field.name}}}"`);
          wxmlLines.push(`        data-field="${field.name}"`);
          wxmlLines.push(`        bindchange="onSwitchChange"`);
          wxmlLines.push(`        disabled="{{isSubmitting}}"`);
          wxmlLines.push(`      />`);
        } else {
          const iptType = field.type === 'number' ? 'digit' : 'text';
          const isPsw = field.type === 'password';
          wxmlLines.push(`      <input`);
          wxmlLines.push(`        class="form-control {{errors.${field.name} ? 'is-invalid' : ''}}"`);
          wxmlLines.push(`        type="${iptType}"`);
          if (isPsw) {
            wxmlLines.push(`        password="true"`);
          }
          wxmlLines.push(`        value="{{formData.${field.name}}}"`);
          wxmlLines.push(`        data-field="${field.name}"`);
          wxmlLines.push(`        bindinput="onFieldInput"`);
          wxmlLines.push(`        bindblur="onFieldBlur"`);
          wxmlLines.push(`        disabled="{{isSubmitting}}"`);
          wxmlLines.push(`      />`);
        }

        wxmlLines.push(`      <view wx:if="{{errors.${field.name}}}" class="form-error-msg">`);
        wxmlLines.push(`        <text>{{errors.${field.name}}}</text>`);
        wxmlLines.push(`      </view>`);
        wxmlLines.push(`    </view>`);
      }
    }

    wxmlLines.push(`    <button`);
    wxmlLines.push(`      form-type="submit"`);
    wxmlLines.push(`      loading="{{isSubmitting}}"`);
    wxmlLines.push(`      disabled="{{isSubmitting}}"`);
    wxmlLines.push(`      class="submit-btn"`);
    wxmlLines.push(`    >`);
    wxmlLines.push(`      {{isSubmitting ? '提交中...' : '提交'}}`);
    wxmlLines.push(`    </button>`);
    wxmlLines.push(`  </form>`);
    wxmlLines.push(`</view>`);

    // --- Component Controller TypeScript ---
    tsLines.push(`/**`);
    tsLines.push(` * MiniApp Form Component Controller: ${formIR.formName}`);
    tsLines.push(` */`);
    tsLines.push(`Component({`);
    tsLines.push(`  data: {`);
    tsLines.push(`    isSubmitting: false,`);
    tsLines.push(`    submitError: '',`);
    tsLines.push(`    formData: {`);
    for (const item of formIR.fields) {
      if ('type' in item) {
        const field = item as FieldControlIR;
        tsLines.push(`      ${field.name}: ${field.defaultValueCode || "''"},`);
      }
    }
    tsLines.push(`    },`);
    tsLines.push(`    errors: {} as Record<string, string>,`);
    tsLines.push(`  },`);
    tsLines.push(`  methods: {`);
    tsLines.push(`    onFieldInput(e: any) {`);
    tsLines.push(`      const field = e.currentTarget.dataset.field;`);
    tsLines.push(`      const value = e.detail.value;`);
    tsLines.push(`      this.setData({`);
    tsLines.push(`        [\`formData.\${field}\`]: value,`);
    tsLines.push(`        [\`errors.\${field}\`]: '',`);
    tsLines.push(`      });`);
    tsLines.push(`    },`);
    tsLines.push(`    onFieldBlur(e: any) {`);
    tsLines.push(`      const field = e.currentTarget.dataset.field;`);
    tsLines.push(`      this.validateField(field);`);
    tsLines.push(`    },`);
    tsLines.push(`    onSwitchChange(e: any) {`);
    tsLines.push(`      const field = e.currentTarget.dataset.field;`);
    tsLines.push(`      this.setData({ [\`formData.\${field}\`]: e.detail.value });`);
    tsLines.push(`    },`);
    tsLines.push(`    validateField(field: string): boolean {`);
    tsLines.push(`      // Validation rules logic`);
    tsLines.push(`      const val = this.data.formData[field];`);
    tsLines.push(`      if (!val && val !== 0) {`);
    tsLines.push(`        this.setData({ [\`errors.\${field}\`]: '此字段为必填项' });`);
    tsLines.push(`        return false;`);
    tsLines.push(`      }`);
    tsLines.push(`      return true;`);
    tsLines.push(`    },`);
    tsLines.push(`    async onFormSubmit() {`);
    tsLines.push(`      if (this.data.isSubmitting) return;`);
    tsLines.push(`      let valid = true;`);
    for (const item of formIR.fields) {
      if ('type' in item) {
        const field = item as FieldControlIR;
        if (field.validationRules.some((r) => r.type === 'required')) {
          tsLines.push(`      if (!this.validateField('${field.name}')) valid = false;`);
        }
      }
    }
    tsLines.push(`      if (!valid) {`);
    tsLines.push(`        wx.showToast({ title: '请完善表单信息', icon: 'none' });`);
    tsLines.push(`        return;`);
    tsLines.push(`      }`);
    tsLines.push(`      this.setData({ isSubmitting: true, submitError: '' });`);
    tsLines.push(`      try {`);
    tsLines.push(`        this.triggerEvent('submit', this.data.formData);`);
    tsLines.push(`      } catch (err: any) {`);
    tsLines.push(`        this.setData({ submitError: err?.message || '提交失败' });`);
    tsLines.push(`      } finally {`);
    tsLines.push(`        this.setData({ isSubmitting: false });`);
    tsLines.push(`      }`);
    tsLines.push(`    },`);
    tsLines.push(`  },`);
    tsLines.push(`});`);

    const combinedOutput = `/* --- WXML --- */\n${wxmlLines.join('\n')}\n\n/* --- TS Controller --- */\n${tsLines.join('\n')}`;

    return {
      code: combinedOutput,
      fileName: `${formIR.formId}.wxml`,
      framework: 'miniapp-form',
      dependencies: [],
      notes: [`Generated MiniApp Form (WXML + TS) from UniversalFormIR: ${formIR.formId}`],
    };
  }

  private capitalize(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
}
