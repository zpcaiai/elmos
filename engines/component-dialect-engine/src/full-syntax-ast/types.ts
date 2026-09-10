/**
 * Canonical types and IR definitions for Full-Syntax AST Frontend Transpilation.
 * 
 * Supports full syntax across 6 major source frameworks:
 * - React (TSX / JSX)
 * - Vue 3 (SFC Composition API & <script setup>)
 * - Vue 2 (SFC Options API)
 * - Angular (TypeScript class & HTML templates)
 * - Svelte (SFC <script> & reactive templates)
 * - WeChat Mini Program (WXML + WXSS + JS/TS Component)
 * 
 * And 3 primary targets:
 * - Vue 3 (SFC <script setup lang="ts">)
 * - React (Modern TSX functional components)
 * - WeChat Mini Program (.wxml, .js, .wxss, .json)
 */

export type SourceFramework = "react" | "vue3" | "vue2" | "angular" | "angular18" | "svelte" | "svelte5" | "miniprogram" | "miniapp" | "arkui";
export type TargetFramework = "vue3" | "react" | "miniprogram" | "miniapp" | "arkui" | "flutter" | "svelte5" | "angular18";

export interface FullSyntaxProp {
  name: string;
  typeAnnotation: string;
  required: boolean;
  defaultValue?: string | number | boolean | null;
  isCallback: boolean;
  callbackSignature?: {
    params: { name: string; type: string }[];
    returnType: string;
  };
  isSlotProp?: boolean;
}

export interface FullSyntaxState {
  name: string;
  setterName?: string;
  initialValueExpr: string;
  typeAnnotation: string;
  isRef?: boolean;
  isDynamic?: boolean;
  description?: string;
}

export interface FullSyntaxComputed {
  name: string;
  returnType: string;
  dependencies: string[];
  expressionOrBody: string;
}

export interface FullSyntaxEffect {
  id: string;
  hookKind: "mount" | "unmount" | "update" | "watch" | "effect" | "layoutEffect";
  dependencies: string[];
  bodyCode: string;
  hasCleanup: boolean;
  cleanupCode?: string;
}

export interface FullSyntaxMethod {
  name: string;
  parameters: { name: string; type: string; defaultValue?: string }[];
  returnType: string;
  bodyCode: string;
  isAsync: boolean;
}

export interface FullSyntaxSlot {
  name: string; // 'default' or named slot
  slotProps: { name: string; type: string }[];
  fallbackNodes: FullSyntaxNode[];
}

export type FullSyntaxNodeKind =
  | "element"
  | "text"
  | "expression"
  | "conditional"
  | "condition"
  | "loop"
  | "component"
  | "slot_outlet"
  | "slot_projection"
  | "fragment";

export interface FullSyntaxAttr {
  name: string;
  value: string;
  isDynamic: boolean;
  expression?: string;
}

export interface FullSyntaxEvent {
  name: string; // 'click', 'change', 'input', 'submit', 'tap', etc.
  handlerNameOrExpr: string;
  args?: string[];
  modifiers?: string[]; // 'prevent', 'stop', etc.
}

export interface FullSyntaxNode {
  id: string;
  kind: FullSyntaxNodeKind;
  tag?: string; // HTML tag or Component name
  attrs?: FullSyntaxAttr[];
  events?: FullSyntaxEvent[];
  text?: string;
  expression?: string;
  condition?: {
    test: string;
    thenNode: FullSyntaxNode;
    elseNode?: FullSyntaxNode;
    elifBranches?: { test: string; node: FullSyntaxNode }[];
  };
  loop?: {
    sourceExpr: string;
    itemName: string;
    indexName?: string;
    keyExpr?: string;
    bodyNode: FullSyntaxNode;
  };
  slotName?: string;
  children?: FullSyntaxNode[];
  rawMarkup?: string;
}

export interface FullSyntaxStyle {
  scopedCss?: string;
  cssModules?: Record<string, string>;
  tailwindClasses?: string[];
  inlineStyles?: Record<string, string | number>;
}

export interface FullSyntaxComponentIR {
  schemaVersion: "2.0";
  componentName: string;
  sourceFramework: SourceFramework;
  targetFramework?: TargetFramework;
  description?: string;
  
  // Component interfaces & reactive state
  props: FullSyntaxProp[];
  states: FullSyntaxState[];
  computed: FullSyntaxComputed[];
  effects: FullSyntaxEffect[];
  methods: FullSyntaxMethod[];
  slots: FullSyntaxSlot[];
  refs: { name: string; type: string }[];

  // Render tree
  templateRoot: FullSyntaxNode;

  // Styling & assets
  styles: FullSyntaxStyle;

  // External integrations & shims
  containerApis: string[]; // ['window.location', 'localStorage', ...]
  thirdPartyComponents: string[]; // ['Button', 'Modal', 'Table', ...]
  rawSourceLinesCount: number;
  metadata: Record<string, unknown>;
}

export interface TranspilationResult {
  componentName: string;
  sourceFramework: SourceFramework;
  targetFramework: TargetFramework;
  success: boolean;
  outputFiles: Record<string, string>; // filename -> code content
  diagnostics: string[];
  ir: FullSyntaxComponentIR;
}
