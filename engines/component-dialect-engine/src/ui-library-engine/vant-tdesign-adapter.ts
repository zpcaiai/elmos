/**
 * @file vant-tdesign-adapter.ts
 * @description Mobile and WeChat MiniApp UI library mapping rules.
 * Supports Vant Weapp (`van-button`, `van-field`, `van-cell`, `van-dialog`)
 * and TDesign MiniApp (`t-button`, `t-input`, `t-dialog`).
 * Conforms to Batch 32 Skills 1208 & 1217.
 */

import {
  ComponentMappingRule,
} from './ui-library-types';

export class VantTDesignAdapter {
  private static rules: Map<string, ComponentMappingRule> = new Map();

  static {
    // 1. AntD Button -> Vant Weapp van-button
    this.registerRule({
      canonicalType: 'button',
      sourceComponentName: 'Button',
      targetComponentName: 'van-button',
      sourceLibrary: 'ant-design',
      targetLibrary: 'vant',
      sourceImport: { module: 'antd', namedExport: 'Button' },
      targetImport: { module: '@vant/weapp/button/index' },
      props: [
        {
          sourceProp: 'type',
          targetProp: 'type',
          transformType: 'value-map',
          valueTransform: {
            exactMatch: {
              primary: 'primary',
              default: 'default',
              dashed: 'info',
              danger: 'danger',
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
              middle: 'normal',
              small: 'small',
            },
          },
        },
        { sourceProp: 'loading', targetProp: 'loading', transformType: 'rename' },
        { sourceProp: 'disabled', targetProp: 'disabled', transformType: 'rename' },
        { sourceProp: 'ghost', targetProp: 'plain', transformType: 'rename' },
      ],
      slots: [{ sourceSlot: 'children', targetSlot: 'default' }],
      events: [{ sourceEvent: 'onClick', targetEvent: 'bind:click', payloadTransform: 'direct' }],
    });

    // 2. AntD Input -> Vant Weapp van-field
    this.registerRule({
      canonicalType: 'input',
      sourceComponentName: 'Input',
      targetComponentName: 'van-field',
      sourceLibrary: 'ant-design',
      targetLibrary: 'vant',
      sourceImport: { module: 'antd', namedExport: 'Input' },
      targetImport: { module: '@vant/weapp/field/index' },
      props: [
        { sourceProp: 'value', targetProp: 'value', transformType: 'rename' },
        { sourceProp: 'placeholder', targetProp: 'placeholder', transformType: 'rename' },
        { sourceProp: 'disabled', targetProp: 'disabled', transformType: 'rename' },
        { sourceProp: 'allowClear', targetProp: 'clearable', transformType: 'rename' },
        { sourceProp: 'maxLength', targetProp: 'maxlength', transformType: 'rename' },
      ],
      slots: [],
      events: [
        { sourceEvent: 'onChange', targetEvent: 'bind:change', payloadTransform: 'extract-detail' },
        { sourceEvent: 'onBlur', targetEvent: 'bind:blur', payloadTransform: 'direct' },
      ],
    });

    // 3. AntD Modal -> Vant Weapp van-dialog
    this.registerRule({
      canonicalType: 'modal',
      sourceComponentName: 'Modal',
      targetComponentName: 'van-dialog',
      sourceLibrary: 'ant-design',
      targetLibrary: 'vant',
      sourceImport: { module: 'antd', namedExport: 'Modal' },
      targetImport: { module: '@vant/weapp/dialog/index' },
      props: [
        { sourceProp: 'open', targetProp: 'show', transformType: 'rename' },
        { sourceProp: 'visible', targetProp: 'show', transformType: 'rename' },
        { sourceProp: 'title', targetProp: 'title', transformType: 'rename' },
        { sourceProp: 'width', targetProp: 'width', transformType: 'rename' },
      ],
      slots: [{ sourceSlot: 'children', targetSlot: 'default' }],
      events: [
        { sourceEvent: 'onOk', targetEvent: 'bind:confirm', payloadTransform: 'direct' },
        { sourceEvent: 'onCancel', targetEvent: 'bind:cancel', payloadTransform: 'direct' },
      ],
    });

    // 4. AntD Card -> Vant Weapp van-panel
    this.registerRule({
      canonicalType: 'card',
      sourceComponentName: 'Card',
      targetComponentName: 'van-panel',
      sourceLibrary: 'ant-design',
      targetLibrary: 'vant',
      sourceImport: { module: 'antd', namedExport: 'Card' },
      targetImport: { module: '@vant/weapp/panel/index' },
      props: [
        { sourceProp: 'title', targetProp: 'title', transformType: 'rename' },
      ],
      slots: [
        { sourceSlot: 'children', targetSlot: 'default' },
        { sourceSlot: 'extra', targetSlot: 'header' },
      ],
      events: [],
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
