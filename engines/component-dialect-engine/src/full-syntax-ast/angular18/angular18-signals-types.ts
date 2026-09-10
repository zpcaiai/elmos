/**
 * Complete AST type definitions for modern Angular 17/18 Signals and Built-in Control Flow.
 * 
 * Accurately models:
 * - Signals: signal<T>(), computed(), effect(), input(), input.required(), output(), model()
 * - New Built-in Control Flow: @if, @else if, @else, @for, @empty, @switch, @case, @default
 * - Deferred Loading: @defer, @placeholder, @loading, @error
 * - Standalone Components: standalone: true, imports: [...]
 */

export interface Angular18SignalInput {
  name: string;
  typeAnnotation: string;
  required: boolean;
  defaultValue?: string;
  alias?: string;
}

export interface Angular18SignalOutput {
  name: string;
  payloadType: string;
  alias?: string;
}

export interface Angular18SignalModel {
  name: string;
  typeAnnotation: string;
  defaultValue?: string;
}

export interface Angular18SignalState {
  name: string;
  typeAnnotation: string;
  initialValueExpr: string;
}

export interface Angular18SignalComputed {
  name: string;
  returnType: string;
  expressionOrBody: string;
}

export interface Angular18SignalEffect {
  id: string;
  bodyCode: string;
  hasCleanup: boolean;
  cleanupCode?: string;
}

export type Angular18ControlFlowNodeKind =
  | "element"
  | "text"
  | "interpolation"
  | "at_if"
  | "at_for"
  | "at_switch"
  | "at_defer"
  | "ng_content"
  | "component";

export interface Angular18Attribute {
  name: string;
  value: string;
  kind: "literal" | "property_binding" | "event_binding" | "two_way_binding" | "directive";
}

export interface Angular18DeferBlock {
  trigger?: string; // 'on viewport', 'on idle', 'on hover', 'when condition'
  prefetch?: string;
  mainBlock: Angular18TemplateNode[];
  placeholderBlock?: {
    minimum?: string;
    nodes: Angular18TemplateNode[];
  };
  loadingBlock?: {
    after?: string;
    minimum?: string;
    nodes: Angular18TemplateNode[];
  };
  errorBlock?: Angular18TemplateNode[];
}

export interface Angular18TemplateNode {
  id: string;
  kind: Angular18ControlFlowNodeKind;
  tag?: string;
  attributes?: Angular18Attribute[];
  text?: string;
  expression?: string;

  // @if (test) { ... } @else if { ... } @else { ... }
  ifControl?: {
    testExpr: string;
    asVariable?: string; // @if (user$ | async; as user)
    consequent: Angular18TemplateNode[];
    elseIfBranches?: {
      testExpr: string;
      asVariable?: string;
      consequent: Angular18TemplateNode[];
    }[];
    alternate?: Angular18TemplateNode[];
  };

  // @for (item of items; track item.id; let idx = $index; let c = $count) { ... } @empty { ... }
  forControl?: {
    itemName: string;
    sourceExpr: string;
    trackExpr: string;
    indexAlias?: string;
    countAlias?: string;
    body: Angular18TemplateNode[];
    emptyBlock?: Angular18TemplateNode[];
  };

  // @switch (condition) { @case (x) { ... } @default { ... } }
  switchControl?: {
    switchExpr: string;
    cases: {
      caseExpr: string;
      body: Angular18TemplateNode[];
    }[];
    defaultCase?: Angular18TemplateNode[];
  };

  // @defer
  deferBlock?: Angular18DeferBlock;

  children?: Angular18TemplateNode[];
}

export interface Angular18ComponentAst {
  className: string;
  selector: string;
  standalone: boolean;
  imports: string[];
  inputs: Angular18SignalInput[];
  outputs: Angular18SignalOutput[];
  models: Angular18SignalModel[];
  states: Angular18SignalState[];
  computed: Angular18SignalComputed[];
  effects: Angular18SignalEffect[];
  methods: {
    name: string;
    parameters: { name: string; type: string; defaultValue?: string }[];
    returnType: string;
    bodyCode: string;
    isAsync: boolean;
  }[];
  templateNodes: Angular18TemplateNode[];
  styles: string[];
}

export interface Angular18SignalItem {
  name: string;
  kind: 'writable' | 'computed';
  typeAnnotation?: string;
  initialValueExpr?: string;
  expressionOrBody?: string;
}

export interface Angular18ControlFlowBlock {
  type: 'if' | 'for' | 'switch' | 'defer';
  conditionCode?: string;
  trackExpression?: string;
  itemName?: string;
  sourceExpr?: string;
}

export interface Angular18ParseResult {
  success: boolean;
  component: Angular18ComponentDecl;
}

export interface Angular18ComponentDecl extends Angular18ComponentAst {
  name: string;
  success: boolean;
  component: Angular18ComponentDecl;
  signals: Angular18SignalItem[];
  controlFlowBlocks: Angular18ControlFlowBlock[];
}
