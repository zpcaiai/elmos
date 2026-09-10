/**
 * @file form-ir-types.ts
 * @description Universal Form & Validation IR contracts for cross-framework form migration.
 * Models field controls, validation rules, triggers, cross-field dependencies,
 * accessible ARIA bindings, submission lifecycle, and error state reconciliation.
 * Conforms to Batch 32 Skill 1210 (b32-form-binding-validation).
 */

export type FormFramework =
  | 'zod'
  | 'react-hook-form'
  | 'vee-validate'
  | 'angular-reactive'
  | 'miniapp-form'
  | 'universal';

export type ValidationTrigger = 'change' | 'blur' | 'submit' | 'manual';

export type ValidationRuleType =
  | 'required'
  | 'min'
  | 'max'
  | 'minLength'
  | 'maxLength'
  | 'pattern'
  | 'email'
  | 'url'
  | 'numeric'
  | 'integer'
  | 'custom'
  | 'customAsync'
  | 'crossField';

export interface ValidationRuleIR {
  type: ValidationRuleType;
  value?: string | number | boolean | RegExp;
  message: string;
  trigger?: ValidationTrigger;
  customValidatorCode?: string;
  dependsOnFields?: string[];
}

export interface FormAccessibilityIR {
  label: string;
  labelPosition?: 'top' | 'left' | 'inline' | 'floating';
  placeholder?: string;
  ariaRequired?: boolean;
  ariaDescribedBy?: string;
  ariaErrorMessage?: string;
  ariaInvalidBinding?: boolean;
  autocomplete?: string;
}

export interface FieldControlIR {
  name: string;
  label?: string;
  type: 'text' | 'password' | 'email' | 'number' | 'textarea' | 'select' | 'checkbox' | 'radio' | 'date' | 'file' | 'switch' | 'custom';
  defaultValueCode?: string;
  validationRules: ValidationRuleIR[];
  accessibility?: FormAccessibilityIR;
  isDisabled?: boolean;
  isReadonly?: boolean;
  isVisibleConditionCode?: string;
  transformCode?: string;
}

export interface FieldGroupIR {
  name: string;
  label?: string;
  fields: Array<FieldControlIR | FieldGroupIR | FormArrayIR>;
  validationRules?: ValidationRuleIR[];
}

export interface FormArrayIR {
  name: string;
  label?: string;
  elementTemplate: FieldControlIR | FieldGroupIR;
  minItems?: number;
  maxItems?: number;
  validationRules?: ValidationRuleIR[];
}

export interface FormSubmissionIR {
  endpoint?: string;
  method?: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  submitHandlerCode: string;
  csrfProtection: boolean;
  doubleSubmitPrevention: boolean;
  autoFocusFirstError: boolean;
  optimisticRollback: boolean;
  draftStorageKey?: string;
}

export interface UniversalFormIR {
  formId: string;
  formName: string;
  sourceFramework: FormFramework;
  description?: string;
  fields: Array<FieldControlIR | FieldGroupIR | FormArrayIR>;
  submission?: FormSubmissionIR;
  validationTrigger: ValidationTrigger;
  revalidationTrigger: ValidationTrigger;
  crossFieldRules?: ValidationRuleIR[];
  metadata?: Record<string, unknown>;
}

export interface FormParseResult {
  success: boolean;
  formIR?: UniversalFormIR;
  errors: string[];
  warnings: string[];
  discoveredFramework: FormFramework;
}

export interface FormEmitResult {
  code: string;
  fileName: string;
  framework: FormFramework;
  dependencies: Array<{ name: string; version: string; isDev: boolean }>;
  notes: string[];
}
