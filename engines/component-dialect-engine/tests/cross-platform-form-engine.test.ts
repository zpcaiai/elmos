/**
 * @file cross-platform-form-engine.test.ts
 * @description Comprehensive Jest test suite for the Cross-Platform Form & Validation Engine (Skill 1210).
 * Tests Zod, React Hook Form, Vue 3 VeeValidate, Angular Reactive Forms, and MiniApp forms.
 * Conforms to Batch 32 Skill 1210 (b32-form-binding-validation).
 */

import { CrossPlatformFormEngine } from '../src/form-engine/cross-platform-form-engine';
import { ZodSchemaAdapter } from '../src/form-engine/zod-schema-adapter';
import { ReactHookFormAdapter } from '../src/form-engine/react-hook-form-adapter';
import { VeeValidateAdapter } from '../src/form-engine/vee-validate-adapter';
import { AngularReactiveFormsAdapter } from '../src/form-engine/angular-reactive-forms-adapter';
import { MiniAppFormAdapter } from '../src/form-engine/miniapp-form-adapter';

describe('Cross-Platform Form & Validation Engine (Skill 1210)', () => {
  const formEngine = new CrossPlatformFormEngine();
  const zodAdapter = new ZodSchemaAdapter();
  const rhfAdapter = new ReactHookFormAdapter();
  const veeAdapter = new VeeValidateAdapter();
  const angularAdapter = new AngularReactiveFormsAdapter();
  const miniappAdapter = new MiniAppFormAdapter();

  const sampleZodSchema = `
import { z } from 'zod';

export const RegistrationSchema = z.object({
  username: z.string().min(3, 'Username must be at least 3 characters'),
  email: z.string().email('Invalid email address'),
  age: z.number().min(18, 'Must be at least 18 years old'),
  agreeToTerms: z.boolean(),
});
`;

  it('should parse Zod schema into UniversalFormIR', () => {
    const res = zodAdapter.parse(sampleZodSchema, 'registration');
    expect(res.success).toBe(true);
    expect(res.formIR).toBeDefined();

    const form = res.formIR!;
    expect(form.fields.length).toBe(4);

    const usernameField = form.fields.find((f) => 'name' in f && f.name === 'username');
    expect(usernameField).toBeDefined();
    if (usernameField && 'validationRules' in usernameField && usernameField.validationRules) {
      expect(usernameField.validationRules.some((r: any) => r.type === 'minLength')).toBe(true);
    }

    const emailField = form.fields.find((f) => 'name' in f && f.name === 'email');
    expect(emailField).toBeDefined();
    if (emailField && 'validationRules' in emailField && emailField.validationRules) {
      expect(emailField.validationRules.some((r: any) => r.type === 'email')).toBe(true);
    }
  });

  it('should emit Zod schema TypeScript code from UniversalFormIR', () => {
    const parseRes = zodAdapter.parse(sampleZodSchema, 'registration');
    const emitRes = zodAdapter.emit(parseRes.formIR!);

    expect(emitRes.framework).toBe('zod');
    expect(emitRes.code).toContain('z.object({');
    expect(emitRes.code).toContain('username: z.string().min(3');
    expect(emitRes.code).toContain('email: z.string().email(');
  });

  it('should emit accessible React Hook Form component from UniversalFormIR', () => {
    const parseRes = zodAdapter.parse(sampleZodSchema, 'registration');
    const emitRes = rhfAdapter.emit(parseRes.formIR!);

    expect(emitRes.framework).toBe('react-hook-form');
    expect(emitRes.code).toContain('useForm<');
    expect(emitRes.code).toContain('zodResolver(');
    expect(emitRes.code).toContain('aria-invalid=');
    expect(emitRes.code).toContain('aria-describedby=');
    expect(emitRes.code).toContain('register(');
  });

  it('should emit Vue 3 VeeValidate SFC from UniversalFormIR', () => {
    const parseRes = zodAdapter.parse(sampleZodSchema, 'registration');
    const emitRes = veeAdapter.emit(parseRes.formIR!);

    expect(emitRes.framework).toBe('vee-validate');
    expect(emitRes.code).toContain('<template>');
    expect(emitRes.code).toContain('useForm({');
    expect(emitRes.code).toContain('defineField(');
    expect(emitRes.code).toContain('toTypedSchema');
  });

  it('should emit Angular 18 Standalone Reactive Forms component from UniversalFormIR', () => {
    const parseRes = zodAdapter.parse(sampleZodSchema, 'registration');
    const emitRes = angularAdapter.emit(parseRes.formIR!);

    expect(emitRes.framework).toBe('angular-reactive');
    expect(emitRes.code).toContain('@Component');
    expect(emitRes.code).toContain('standalone: true');
    expect(emitRes.code).toContain('FormGroup');
    expect(emitRes.code).toContain('Validators.');
  });

  it('should emit WeChat MiniApp WXML form and controller from UniversalFormIR', () => {
    const parseRes = zodAdapter.parse(sampleZodSchema, 'registration');
    const emitRes = miniappAdapter.emit(parseRes.formIR!);

    expect(emitRes.framework).toBe('miniapp-form');
    expect(emitRes.code).toContain('bindsubmit="onFormSubmit"');
    expect(emitRes.code).toContain('data-field="username"');
    expect(emitRes.code).toContain('Component({');
  });

  it('should perform end-to-end form transformation via CrossPlatformFormEngine', () => {
    const res = formEngine.transform(sampleZodSchema, 'zod', 'react-hook-form', 'registration');
    expect(res.parseResult.success).toBe(true);
    expect(res.emitResult.framework).toBe('react-hook-form');
    expect(res.emitResult.code).toContain('RegistrationComponent');
  });
});
