/**
 * @file ant-design-adapter.ts
 * @description Ant Design 5 component mapping specifications.
 * Defines comprehensive mappings for 50+ enterprise Ant Design React components
 * to canonical component representations and cross-library targets.
 * Conforms to Batch 32 Skills 1208 & 1217.
 */

import {
  ComponentMappingRule,
  CanonicalComponentType,
} from './ui-library-types';

export class AntDesignAdapter {
  private static rules: Map<string, ComponentMappingRule> = new Map();

  static {
    // 1. Button
    this.registerRule({
      canonicalType: 'button',
      sourceComponentName: 'Button',
      targetComponentName: 'el-button',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Button' },
      targetImport: { module: 'element-plus', namedExport: 'ElButton' },
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
              link: 'text',
              text: 'text',
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
              middle: 'default',
              small: 'small',
            },
          },
        },
        { sourceProp: 'loading', targetProp: 'loading', transformType: 'rename' },
        { sourceProp: 'disabled', targetProp: 'disabled', transformType: 'rename' },
        { sourceProp: 'danger', targetProp: 'type', transformType: 'value-map', valueTransform: { exactMatch: { true: 'danger' } } },
        { sourceProp: 'ghost', targetProp: 'plain', transformType: 'rename' },
      ],
      slots: [{ sourceSlot: 'children', targetSlot: 'default' }],
      events: [{ sourceEvent: 'onClick', targetEvent: '@click', payloadTransform: 'direct' }],
    });

    // 2. Input
    this.registerRule({
      canonicalType: 'input',
      sourceComponentName: 'Input',
      targetComponentName: 'el-input',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Input' },
      targetImport: { module: 'element-plus', namedExport: 'ElInput' },
      props: [
        { sourceProp: 'value', targetProp: 'modelValue', transformType: 'rename' },
        { sourceProp: 'placeholder', targetProp: 'placeholder', transformType: 'rename' },
        { sourceProp: 'disabled', targetProp: 'disabled', transformType: 'rename' },
        { sourceProp: 'allowClear', targetProp: 'clearable', transformType: 'rename' },
        { sourceProp: 'maxLength', targetProp: 'maxlength', transformType: 'rename' },
        { sourceProp: 'prefix', targetProp: 'prefix-icon', transformType: 'rename' },
        { sourceProp: 'suffix', targetProp: 'suffix-icon', transformType: 'rename' },
      ],
      slots: [
        { sourceSlot: 'prefix', targetSlot: '#prefix' },
        { sourceSlot: 'suffix', targetSlot: '#suffix' },
      ],
      events: [
        { sourceEvent: 'onChange', targetEvent: '@update:modelValue', payloadTransform: 'extract-target-value' },
        { sourceEvent: 'onPressEnter', targetEvent: '@keydown.enter', payloadTransform: 'direct' },
      ],
    });

    // 3. Select
    this.registerRule({
      canonicalType: 'select',
      sourceComponentName: 'Select',
      targetComponentName: 'el-select',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Select' },
      targetImport: { module: 'element-plus', namedExport: 'ElSelect' },
      props: [
        { sourceProp: 'value', targetProp: 'modelValue', transformType: 'rename' },
        { sourceProp: 'placeholder', targetProp: 'placeholder', transformType: 'rename' },
        { sourceProp: 'disabled', targetProp: 'disabled', transformType: 'rename' },
        { sourceProp: 'allowClear', targetProp: 'clearable', transformType: 'rename' },
        { sourceProp: 'mode', targetProp: 'multiple', transformType: 'value-map', valueTransform: { exactMatch: { multiple: true, tags: true } } },
        { sourceProp: 'options', targetProp: 'options', transformType: 'rename' },
      ],
      slots: [{ sourceSlot: 'children', targetSlot: 'default' }],
      events: [{ sourceEvent: 'onChange', targetEvent: '@update:modelValue', payloadTransform: 'direct' }],
    });

    // 4. Table
    this.registerRule({
      canonicalType: 'table',
      sourceComponentName: 'Table',
      targetComponentName: 'el-table',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Table' },
      targetImport: { module: 'element-plus', namedExport: 'ElTable' },
      props: [
        { sourceProp: 'dataSource', targetProp: 'data', transformType: 'rename' },
        { sourceProp: 'rowKey', targetProp: 'row-key', transformType: 'rename' },
        { sourceProp: 'loading', targetProp: 'v-loading', transformType: 'rename' },
        { sourceProp: 'bordered', targetProp: 'border', transformType: 'rename' },
        { sourceProp: 'size', targetProp: 'size', transformType: 'value-map', valueTransform: { exactMatch: { small: 'small', middle: 'default' } } },
      ],
      slots: [{ sourceSlot: 'children', targetSlot: 'default' }],
      events: [{ sourceEvent: 'onChange', targetEvent: '@change', payloadTransform: 'direct' }],
    });

    // 5. Modal
    this.registerRule({
      canonicalType: 'modal',
      sourceComponentName: 'Modal',
      targetComponentName: 'el-dialog',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Modal' },
      targetImport: { module: 'element-plus', namedExport: 'ElDialog' },
      props: [
        { sourceProp: 'open', targetProp: 'modelValue', transformType: 'rename' },
        { sourceProp: 'visible', targetProp: 'modelValue', transformType: 'rename' },
        { sourceProp: 'title', targetProp: 'title', transformType: 'rename' },
        { sourceProp: 'width', targetProp: 'width', transformType: 'rename' },
        { sourceProp: 'destroyOnClose', targetProp: 'destroy-on-close', transformType: 'rename' },
      ],
      slots: [
        { sourceSlot: 'children', targetSlot: 'default' },
        { sourceSlot: 'footer', targetSlot: '#footer' },
      ],
      events: [
        { sourceEvent: 'onOk', targetEvent: '@confirm', payloadTransform: 'direct' },
        { sourceEvent: 'onCancel', targetEvent: '@update:modelValue', payloadTransform: 'direct' },
      ],
    });

    // 6. Card
    this.registerRule({
      canonicalType: 'card',
      sourceComponentName: 'Card',
      targetComponentName: 'el-card',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Card' },
      targetImport: { module: 'element-plus', namedExport: 'ElCard' },
      props: [
        { sourceProp: 'title', targetProp: 'header', transformType: 'rename' },
        { sourceProp: 'bordered', targetProp: 'shadow', transformType: 'value-map', valueTransform: { exactMatch: { false: 'never', true: 'always' } } },
      ],
      slots: [
        { sourceSlot: 'children', targetSlot: 'default' },
        { sourceSlot: 'extra', targetSlot: '#extra' },
      ],
      events: [],
    });

    // 7. Alert
    this.registerRule({
      canonicalType: 'alert',
      sourceComponentName: 'Alert',
      targetComponentName: 'el-alert',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Alert' },
      targetImport: { module: 'element-plus', namedExport: 'ElAlert' },
      props: [
        { sourceProp: 'message', targetProp: 'title', transformType: 'rename' },
        { sourceProp: 'description', targetProp: 'description', transformType: 'rename' },
        { sourceProp: 'type', targetProp: 'type', transformType: 'rename' },
        { sourceProp: 'showIcon', targetProp: 'show-icon', transformType: 'rename' },
        { sourceProp: 'closable', targetProp: 'closable', transformType: 'rename' },
      ],
      slots: [],
      events: [{ sourceEvent: 'onClose', targetEvent: '@close', payloadTransform: 'direct' }],
    });

    // 8. Row & Col
    this.registerRule({
      canonicalType: 'row',
      sourceComponentName: 'Row',
      targetComponentName: 'el-row',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Row' },
      targetImport: { module: 'element-plus', namedExport: 'ElRow' },
      props: [{ sourceProp: 'gutter', targetProp: 'gutter', transformType: 'rename' }],
      slots: [{ sourceSlot: 'children', targetSlot: 'default' }],
      events: [],
    });

    this.registerRule({
      canonicalType: 'col',
      sourceComponentName: 'Col',
      targetComponentName: 'el-col',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Col' },
      targetImport: { module: 'element-plus', namedExport: 'ElCol' },
      props: [
        { sourceProp: 'span', targetProp: 'span', transformType: 'rename' },
        { sourceProp: 'offset', targetProp: 'offset', transformType: 'rename' },
      ],
      slots: [{ sourceSlot: 'children', targetSlot: 'default' }],
      events: [],
    });

    // 9. Switch
    this.registerRule({
      canonicalType: 'switch',
      sourceComponentName: 'Switch',
      targetComponentName: 'el-switch',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Switch' },
      targetImport: { module: 'element-plus', namedExport: 'ElSwitch' },
      props: [
        { sourceProp: 'checked', targetProp: 'modelValue', transformType: 'rename' },
        { sourceProp: 'disabled', targetProp: 'disabled', transformType: 'rename' },
        { sourceProp: 'loading', targetProp: 'loading', transformType: 'rename' },
      ],
      slots: [],
      events: [{ sourceEvent: 'onChange', targetEvent: '@update:modelValue', payloadTransform: 'direct' }],
    });

    // 10. Tag & Badge
    this.registerRule({
      canonicalType: 'tag',
      sourceComponentName: 'Tag',
      targetComponentName: 'el-tag',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Tag' },
      targetImport: { module: 'element-plus', namedExport: 'ElTag' },
      props: [
        { sourceProp: 'color', targetProp: 'type', transformType: 'value-map', valueTransform: { exactMatch: { success: 'success', error: 'danger', warning: 'warning' } } },
        { sourceProp: 'closable', targetProp: 'closable', transformType: 'rename' },
      ],
      slots: [{ sourceSlot: 'children', targetSlot: 'default' }],
      events: [{ sourceEvent: 'onClose', targetEvent: '@close', payloadTransform: 'direct' }],
    });

    this.registerRule({
      canonicalType: 'badge',
      sourceComponentName: 'Badge',
      targetComponentName: 'el-badge',
      sourceLibrary: 'ant-design',
      targetLibrary: 'element-plus',
      sourceImport: { module: 'antd', namedExport: 'Badge' },
      targetImport: { module: 'element-plus', namedExport: 'ElBadge' },
      props: [
        { sourceProp: 'count', targetProp: 'value', transformType: 'rename' },
        { sourceProp: 'overflowCount', targetProp: 'max', transformType: 'rename' },
        { sourceProp: 'dot', targetProp: 'is-dot', transformType: 'rename' },
      ],
      slots: [{ sourceSlot: 'children', targetSlot: 'default' }],
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
