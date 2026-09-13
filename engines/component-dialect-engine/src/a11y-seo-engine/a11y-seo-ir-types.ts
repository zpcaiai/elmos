/**
 * @file a11y-seo-ir-types.ts
 * @description Universal Accessibility (A11y) and Search Engine Optimization (SEO) IR Types.
 * Models WCAG 2.2 AA/AAA standards, ARIA roles/states, roving tabIndex focus traps,
 * Open Graph, Twitter Cards, JSON-LD Schema.org structured data, and WeChat MiniApp accessibility contracts.
 * Conforms to Batch 32 Skill 1221 (b32-accessibility-i18n-seo-visual-e2e).
 */

export type WcagComplianceLevel = 'A' | 'AA' | 'AAA';

export type AriaRole =
  | 'alert'
  | 'alertdialog'
  | 'banner'
  | 'button'
  | 'checkbox'
  | 'combobox'
  | 'dialog'
  | 'feed'
  | 'form'
  | 'grid'
  | 'heading'
  | 'link'
  | 'list'
  | 'listbox'
  | 'listitem'
  | 'main'
  | 'menu'
  | 'menubar'
  | 'menuitem'
  | 'navigation'
  | 'progressbar'
  | 'radio'
  | 'radiogroup'
  | 'region'
  | 'search'
  | 'separator'
  | 'slider'
  | 'spinbutton'
  | 'status'
  | 'tab'
  | 'tablist'
  | 'tabpanel'
  | 'textbox'
  | 'toolbar'
  | 'tooltip';

export interface AriaAttributesIR {
  role?: AriaRole;
  label?: string;
  labelledby?: string;
  describedby?: string;
  expanded?: boolean | string; // e.g. "isOpen"
  hidden?: boolean | string;
  selected?: boolean | string;
  checked?: boolean | 'mixed' | string;
  disabled?: boolean | string;
  invalid?: boolean | 'grammar' | 'spelling' | string;
  required?: boolean | string;
  live?: 'off' | 'polite' | 'assertive';
  atomic?: boolean;
  busy?: boolean | string;
  current?: 'page' | 'step' | 'location' | 'date' | 'time' | boolean | string;
  controls?: string;
  owns?: string;
  haspopup?: boolean | 'menu' | 'listbox' | 'tree' | 'grid' | 'dialog';
}

export interface FocusManagementIR {
  trapFocus?: boolean; // For modal dialogs
  autoFocus?: boolean;
  rovingTabIndex?: boolean; // For lists/menus/grids
  restoreFocusElementId?: string;
  skipLinkTargetId?: string;
}

export interface AccessibleNodeIR {
  id: string;
  componentTag: string;
  aria: AriaAttributesIR;
  focus?: FocusManagementIR;
  keyboardShortcuts?: Array<{ key: string; ctrl?: boolean; alt?: boolean; shift?: boolean; action: string }>;
  screenReaderText?: string;
  children?: AccessibleNodeIR[];
}

export interface OpenGraphMetadataIR {
  title: string;
  description: string;
  type: 'website' | 'article' | 'product' | 'profile' | 'video';
  url: string;
  image: string;
  imageAlt?: string;
  siteName?: string;
  locale?: string;
}

export interface TwitterCardMetadataIR {
  card: 'summary' | 'summary_large_image' | 'app' | 'player';
  site?: string;
  creator?: string;
  title: string;
  description: string;
  image?: string;
}

export interface JsonLdSchemaIR {
  context: 'https://schema.org';
  type: 'WebSite' | 'Product' | 'Article' | 'BreadcrumbList' | 'Organization' | 'FAQPage';
  data: Record<string, any>;
}

export interface UniversalSeoMetadataIR {
  title: string;
  titleTemplate?: string; // e.g. "%s | Elmos Store"
  description: string;
  keywords?: string[];
  canonicalUrl?: string;
  robots?: {
    index: boolean;
    follow: boolean;
    nocache?: boolean;
  };
  openGraph?: OpenGraphMetadataIR;
  twitter?: TwitterCardMetadataIR;
  jsonLdSchemas?: JsonLdSchemaIR[];
  alternateLanguages?: Array<{ hrefLang: string; href: string }>;
}

export interface WcagViolationRecord {
  ruleId: string;
  wcagCriterion: string; // e.g. "1.1.1 Non-text Content", "4.1.2 Name, Role, Value"
  severity: 'error' | 'warning' | 'info';
  elementId?: string;
  elementTag: string;
  message: string;
  suggestedFix: string;
  line?: number;
}

export interface WcagAuditReport {
  isCompliant: boolean;
  level: WcagComplianceLevel;
  totalViolations: number;
  errorsCount: number;
  warningsCount: number;
  violations: WcagViolationRecord[];
}
