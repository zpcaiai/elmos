/**
 * @file element-plus-adapter.ts
 * @description Element Plus component mapping specifications.
 * Defines mappings from Element Plus 2 components to Ant Design, Vant, and canonical IR.
 * Conforms to Batch 32 Skills 1208 & 1217.
 */

import {
  ComponentMappingRule,
} from './ui-library-types';

export class ElementPlusAdapter {
  private static rules: Map<string, ComponentMappingRule> = new Map();

  static {
    // 1. ElButton -> AntD Button
    this.registerRule({
      canonicalType: 'button',
      sourceComponentName: 'ElButton',
      targetComponentName: 'Button',
      sourceLibrary: 'element-plus',
      targetLibrary: 'ant-design',
      sourceImport: { module: 'element-plus', namedExport: 'ElButton' },
      targetImport: { module: 'antd', namedExport: 'Button' },
      props: [
        {
          sourceProp: 'type',
          targetProp: 'type',
          transformType: 'value-map',
          valueTransform: {
            exactMatch: {
              primary: 'primary',
              success: 'primary',
              warning: 'default',
              danger: 'primary',
              info: 'default',
              text: 'link',
            },
          },
        },
        {
          sourceProp: 'size',
          targetProp: 'size',
          transformType: 'value-map',
          valueTransform: {
            exactMatch: {
              large: 'large',
              default: 'middle',
              small: 'small',
            },
          },
        },
        { sourceProp: 'loading', targetProp: 'loading', transformType: 'rename' },
        { sourceProp: 'disabled', targetProp: 'disabled', transformType: 'rename' },
        { sourceProp: 'plain', targetProp: 'ghost', transformType: 'rename' },
      ],
      slots: [{ sourceSlot: 'default', targetSlot: 'children' }],
      events: [{ sourceEvent: '@click', targetEvent: 'onClick', payloadTransform: 'direct' }],
    });

    // 2. ElInput -> AntD Input
    this.registerRule({
      canonicalType: 'input',
      sourceComponentName: 'ElInput',
      targetComponentName: 'Input',
      sourceLibrary: 'element-plus',
      targetLibrary: 'ant-design',
      sourceImport: { module: 'element-plus', namedExport: 'ElInput' },
      targetImport: { module: 'antd', namedExport: 'Input' },
      props: [
        { sourceProp: 'modelValue', targetProp: 'value', transformType: 'rename' },
        { sourceProp: 'placeholder', targetProp: 'placeholder', transformType: 'rename' },
        { sourceProp: 'disabled', targetProp: 'disabled', transformType: 'rename' },
        { sourceProp: 'clearable', targetProp: 'allowClear', transformType: 'rename' },
        { sourceProp: 'maxlength', targetProp: 'maxLength', transformType: 'rename' },
      ],
      slots: [
        { sourceSlot: '#prefix', targetSlot: 'prefix' },
        { sourceSlot: '#suffix', targetSlot: 'suffix' },
      ],
      events: [{ sourceEvent: '@update:modelValue', targetEvent: 'onChange', payloadTransform: 'direct' }],
    });

    // 3. ElDialog -> AntD Modal
    this.registerRule({
      canonicalType: 'modal',
      sourceComponentName: 'ElDialog',
      targetComponentName: 'Modal',
      sourceLibrary: 'element-plus',
      targetLibrary: 'ant-design',
      sourceImport: { module: 'element-plus', namedExport: 'ElDialog' },
      targetImport: { module: 'antd', namedExport: 'Modal' },
      props: [
        { sourceProp: 'modelValue', targetProp: 'open', transformType: 'rename' },
        { sourceProp: 'title', targetProp: 'title', transformType: 'rename' },
        { sourceProp: 'width', targetProp: 'width', transformType: 'rename' },
        { sourceProp: 'destroy-on-close', targetProp: 'destroyOnClose', transformType: 'rename' },
      ],
      slots: [
        { sourceSlot: 'default', targetSlot: 'children' },
        { sourceSlot: '#footer', targetSlot: 'footer' },
      ],
      events: [
        { sourceEvent: '@confirm', targetEvent: 'onOk', payloadTransform: 'direct' },
        { sourceEvent: '@update:modelValue', targetEvent: 'onCancel', payloadTransform: 'direct' },
      ],
    });
  }

  private static registerRule(rule: ComponentMappingRule) {
    this.rules.set(rule.sourceComponentName, rule);
  }

  public static getRule(componentName: string): ComponentMappingRule | undefined {
    return this.rules.get(componentName);
  }

  public static getAllRules(): ComponentMappingRule[] {
    return Array.from(this.rules.values());
  }
}
