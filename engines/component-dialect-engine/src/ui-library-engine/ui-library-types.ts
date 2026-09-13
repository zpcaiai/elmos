/**
 * @file ui-library-types.ts
 * @description Unified UI Component Library Taxonomy and Mapping Contracts.
 * Supports cross-library translation among Ant Design (React), Element Plus (Vue 3),
 * Vant Weapp / TDesign (MiniApp), and ArkUI native components.
 * Conforms to Batch 32 Skills 1208 & 1217 (b32-component-template-view-migration).
 */

export type UILibraryId =
  | 'ant-design'
  | 'element-plus'
  | 'vant'
  | 'vant-weapp'
  | 'tdesign-miniapp'
  | 'arkui-components'
  | 'material-ui'
  | 'generic-html';

export type CanonicalComponentCategory =
  | 'general'
  | 'layout'
  | 'navigation'
  | 'data-entry'
  | 'data-display'
  | 'feedback'
  | 'other';

export type CanonicalComponentType =
  | 'button'
  | 'icon'
  | 'typography'
  | 'divider'
  | 'row'
  | 'col'
  | 'space'
  | 'layout'
  | 'header'
  | 'sider'
  | 'content'
  | 'footer'
  | 'affix'
  | 'breadcrumb'
  | 'dropdown'
  | 'menu'
  | 'pagination'
  | 'steps'
  | 'tabs'
  | 'input'
  | 'textarea'
  | 'input-number'
  | 'select'
  | 'cascader'
  | 'checkbox'
  | 'radio'
  | 'switch'
  | 'slider'
  | 'date-picker'
  | 'time-picker'
  | 'upload'
  | 'rate'
  | 'form'
  | 'form-item'
  | 'avatar'
  | 'badge'
  | 'calendar'
  | 'card'
  | 'carousel'
  | 'collapse'
  | 'descriptions'
  | 'empty'
  | 'image'
  | 'list'
  | 'popover'
  | 'table'
  | 'tag'
  | 'timeline'
  | 'tooltip'
  | 'tree'
  | 'alert'
  | 'drawer'
  | 'message'
  | 'modal'
  | 'notification'
  | 'popconfirm'
  | 'progress'
  | 'result'
  | 'skeleton'
  | 'spin';

export interface PropValueTransformRule {
  exactMatch?: Record<string, string | number | boolean>;
  prefix?: string;
  suffix?: string;
  customTransformCode?: string;
}

export interface PropMappingRule {
  sourceProp: string;
  targetProp: string;
  transformType: 'rename' | 'value-map' | 'boolean-to-enum' | 'enum-to-boolean' | 'render-prop-to-slot' | 'remove';
  valueTransform?: PropValueTransformRule;
  defaultValue?: string | number | boolean;
  notes?: string;
}

export interface SlotMappingRule {
  sourceSlot: string; // e.g. 'children', 'extra', 'footer', 'title'
  targetSlot: string; // e.g. 'default', '#extra', 'slot="footer"'
  isScoped?: boolean;
  scopeParamName?: string;
}

export interface EventMappingRule {
  sourceEvent: string; // e.g. 'onClick', 'onChange', 'onSelect'
  targetEvent: string; // e.g. '@click', '@change', 'bindtap', 'bindchange'
  payloadTransform?: 'direct' | 'extract-detail' | 'extract-target-value' | 'custom';
  customHandlerSnippet?: string;
}

export interface ComponentMappingRule {
  canonicalType: CanonicalComponentType;
  sourceComponentName: string;
  targetComponentName: string;
  sourceLibrary: UILibraryId;
  targetLibrary: UILibraryId;
  sourceImport: { module: string; isDefault?: boolean; namedExport?: string };
  targetImport: { module: string; isDefault?: boolean; namedExport?: string };
  props: PropMappingRule[];
  slots: SlotMappingRule[];
  events: EventMappingRule[];
  wrapWithContainer?: string;
  notes?: string;
}

export interface UILibraryConversionResult {
  transformedCode: string;
  matchedComponents: Array<{
    source: string;
    target: string;
    canonicalType: CanonicalComponentType;
  }>;
  addedImports: Array<{ module: string; imports: string[] }>;
  removedImports: Array<{ module: string; imports: string[] }>;
  warnings: string[];
}
