/**
 * Framework-neutral semantic IR for client component migration.
 *
 * `models.ts` is intentionally a small, closed model: it is the proof
 * boundary for automatic conversion.  This module is the larger contract
 * around that boundary.  It records the semantics a real migration has to
 * account for even when the source is not automatically convertible.
 *
 * The IR is deliberately typed rather than a bag of source AST nodes.  A
 * target adapter can therefore make an explicit decision for every semantic
 * domain, and a blocked construct can be handed to a human without silently
 * disappearing from the migration inventory.
 */
import * as crypto from "crypto";
import {
  ALL_FRAMEWORKS,
  AttrBinding,
  ComponentDef,
  ComponentArg,
  Expr,
  Framework,
  Literal,
  Node,
  PropDef,
  StateDef,
  Stmt,
  ValueShape,
} from "./models";
import { TARGET_ADAPTERS } from "./target-adapters";

export const CROSS_PLATFORM_IR_SCHEMA_VERSION = "1.0" as const;

export type SemanticCategory =
  | "render-tree"
  | "state-lifecycle"
  | "effects-and-resources"
  | "data-contracts"
  | "derived-collections"
  | "slots-and-composition"
  | "platform-semantics"
  | "styling"
  | "accessibility-and-i18n";

export type SemanticDisposition =
  | "AUTOMATIC"
  | "ADAPTER_REQUIRED"
  | "HAND_PORTED"
  | "BLOCKED"
  | "NOT_RUN";

export type IRExpression =
  | { kind: "reference"; name: string }
  | { kind: "member"; object: string; fields: string[] }
  | { kind: "literal"; value: Literal }
  | { kind: "binary"; operator: string; left: IRExpression; right: IRExpression }
  | { kind: "unary-not"; operand: IRExpression }
  | { kind: "call"; callee: string; args: IRExpression[]; purity: "pure" | "effectful" | "unknown" }
  | { kind: "collection"; operation: "filter" | "map" | "reduce" | "max" | "join"; source: IRExpression; details: Record<string, string | number | IRExpression> }
  | { kind: "object-lookup"; object: IRExpression; key: IRExpression }
  | { kind: "object-literal"; fields: { name: string; value: IRExpression }[] }
  | { kind: "array-literal"; items: IRExpression[] }
  | { kind: "ternary"; condition: IRExpression; then: IRExpression; else: IRExpression };

export type IRAction =
  | { kind: "set-state"; target: string; value: IRExpression }
  | { kind: "invoke-callback"; target: string; args: IRExpression[] };

export interface IRSourceTrace {
  sourceFile: string;
  componentName: string;
  canonicalPath: string;
  /** The current canonical parser does not yet carry node spans.  Null is
   * explicit so consumers cannot mistake component-level provenance for an
   * exact source range. */
  sourceRange: { start: number; end: number } | null;
  traceStatus: "COMPONENT_MODEL_ONLY" | "EXACT_SOURCE_RANGE";
}

export interface IRAttribute {
  name: string;
  value: string | IRExpression;
  binding: "static" | "dynamic";
  sourcePath: string;
}

export interface IRInteraction {
  id: string;
  event: string;
  actions: IRAction[];
  sourcePath: string;
}

export type IRRenderNode =
  | {
    kind: "element";
    tag: string;
    attributes: IRAttribute[];
    interactions: IRInteraction[];
    children: IRRenderNode[];
    sourcePath: string;
  }
  | { kind: "fragment"; children: IRRenderNode[]; sourcePath: string }
  | { kind: "text"; value: IRExpression; sourcePath: string }
  | { kind: "conditional"; condition: IRExpression; then: IRRenderNode; else: IRRenderNode | null; sourcePath: string }
  | { kind: "collection"; source: IRExpression; itemName: string; keyField: string | null; body: IRRenderNode; sourcePath: string }
  | { kind: "component"; name: string; props: { name: string; value: IRExpression }[]; sourcePath: string }
  | { kind: "slot"; name: string; required: boolean; sourcePath: string };

export interface IRStateVariable {
  name: string;
  ownership: "LOCAL_EPHEMERAL" | "SHARED" | "SERVER_OWNED" | "PERSISTED" | "DERIVED" | "SECURITY_SENSITIVE";
  shape: ValueShape;
  initial: { kind: "literal"; value: Literal } | { kind: "expression"; value: IRExpression };
  nullable: boolean;
  sourcePath: string;
}

export interface IRStateTransition {
  id: string;
  trigger: string;
  actions: IRAction[];
  ordering: "SOURCE_ORDERED";
  cancellation: "NOT_APPLICABLE" | "REQUIRED";
}

export interface IREffectContract {
  id: string;
  trigger: "MOUNT" | "DEPENDENCY_CHANGE" | "USER_EVENT" | "BACKGROUND" | "UNKNOWN";
  resource: "NETWORK" | "TIMER" | "SUBSCRIPTION" | "STORAGE" | "NATIVE_API" | "WORKER" | "UNKNOWN";
  cleanup: "REQUIRED" | "NOT_APPLICABLE" | "UNKNOWN";
  cancellation: "REQUIRED" | "NOT_APPLICABLE" | "UNKNOWN";
  status: "REPRESENTED" | "BLOCKED" | "NOT_CAPTURED";
  sourcePath: string;
}

export interface IRCollectionContract {
  name: string;
  ownership: "PROP" | "STATE" | "DERIVED" | "MODULE_CONSTANT";
  elementShape: ValueShape;
  identity: { strategy: "DECLARED_FIELD" | "PRIMITIVE_VALUE"; field: string | null };
  operations: ("filter" | "map" | "reduce" | "max" | "join")[];
  mutation: "READ_ONLY" | "UNKNOWN";
  sourcePath: string;
}

export interface IRSlotContract {
  name: string;
  ownership: "PARENT" | "CHILD";
  evaluation: "PARENT" | "CHILD" | "UNKNOWN";
  fallback: "EXPLICIT" | "NONE" | "UNKNOWN";
  status: "REPRESENTED" | "HAND_PORTED" | "BLOCKED";
  sourcePath: string;
}

export interface IRPlatformSemantic {
  id: string;
  domain: "HTML" | "SVG" | "TABLE" | "DISCLOSURE" | "DOCUMENT_ROOT" | "NATIVE" | "CSS_MODULE" | "SLOT";
  sourceName: string;
  requiredAdapter: string | null;
  disposition: SemanticDisposition;
  sourcePath: string;
}

export interface IRStylingContract {
  source: "CLASS_ATTRIBUTE" | "CSS_MODULE" | "INLINE_STYLE" | "UNKNOWN" | "NONE";
  tokens: string[];
  targetPolicy: "PRESERVE" | "ADAPTER_REQUIRED" | "HAND_PORTED" | "NOT_CAPTURED";
}

export interface IRAccessibilityContract {
  roles: string[];
  attributes: string[];
  focusable: boolean;
  keyboardEvents: string[];
  localization: "SOURCE_TEXT_ONLY" | "EXPLICIT_LOCALE" | "UNKNOWN";
}

export interface IRObligation {
  id: string;
  category: SemanticCategory;
  reasonCode: string;
  disposition: Exclude<SemanticDisposition, "AUTOMATIC">;
  description: string;
  sourcePath: string;
  requiredEvidence: string[];
}

export interface TargetAdapterPlan {
  targetFramework: Framework;
  adapterId: string;
  categoryModes: Record<SemanticCategory, "NATIVE" | "ADAPTER" | "HAND_PORTED" | "BLOCKED">;
  requiredRuntime: "BROWSER" | "ANDROID" | "IOS" | "HARMONYOS" | "FLUTTER" | "WECHAT_DEVTOOLS" | "ANGULAR_RUNTIME";
  syntaxEvidence: "AVAILABLE_HERE" | "EXTERNAL_TOOLCHAIN_REQUIRED";
  runtimeEvidence: "AVAILABLE_HERE" | "EXTERNAL_RUNTIME_REQUIRED";
}

export interface CrossPlatformComponentIR {
  schemaVersion: typeof CROSS_PLATFORM_IR_SCHEMA_VERSION;
  kind: "elmos.cross-platform-component-ir";
  componentId: string;
  source: {
    framework: Framework;
    file: string;
    componentName: string;
    parserProfile: "certified-component-v1";
  };
  sourceTrace: IRSourceTrace;
  renderTree: IRRenderNode;
  state: {
    variables: IRStateVariable[];
    transitions: IRStateTransition[];
    effects: IREffectContract[];
    cleanupObligations: string[];
  };
  interactions: IRInteraction[];
  collections: IRCollectionContract[];
  slots: IRSlotContract[];
  platformSemantics: IRPlatformSemantic[];
  styling: IRStylingContract;
  accessibility: IRAccessibilityContract;
  obligations: IRObligation[];
  targetAdapters: Record<Framework, TargetAdapterPlan>;
  /** The canonical model is a typed, framework-neutral input to adapters;
   * it is not a source AST and contains no executable source text. */
  canonical: ComponentDef;
  irDigest: string;
}

function expression(expr: Expr): IRExpression {
  switch (expr.kind) {
    case "ident": return { kind: "reference", name: expr.name };
    case "member": return { kind: "member", object: expr.object, fields: [expr.field] };
    case "path": return { kind: "member", object: expr.object, fields: [...expr.fields] };
    case "literal": return { kind: "literal", value: expr.literal };
    case "binary": return { kind: "binary", operator: expr.operator, left: expression(expr.left), right: expression(expr.right) };
    case "unaryNot": return { kind: "unary-not", operand: expression(expr.operand) };
    case "stringMethod": return { kind: "call", callee: `string.${expr.method}`, args: [expression(expr.receiver), ...expr.args.map(expression)], purity: "pure" };
    case "numericFunction": return { kind: "call", callee: `number.${expr.function}`, args: expr.args.map(expression), purity: "pure" };
    case "numericPredicate": return { kind: "call", callee: `number.${expr.predicate}`, args: [expression(expr.operand)], purity: "pure" };
    case "numberMethod": return { kind: "call", callee: `number.${expr.method}`, args: [expression(expr.receiver)], purity: "pure" };
    case "numberFormat": return { kind: "call", callee: `number-format.${expr.format}`, args: [expression(expr.operand)], purity: "pure" };
    case "cssModuleClass": return { kind: "call", callee: "css-module.class", args: [{ kind: "literal", value: { type: "string", value: expr.className } }], purity: "pure" };
    case "eventValue": return { kind: "reference", name: "$event.value" };
    case "regexTest": return { kind: "call", callee: "regex.test", args: [{ kind: "literal", value: { type: "string", value: expr.pattern } }, expression(expr.operand)], purity: "pure" };
    case "arrayLength": return { kind: "call", callee: "array.length", args: [expression(expr.operand)], purity: "pure" };
    case "percentageWidth": return { kind: "call", callee: "layout.percentage-width", args: [expression(expr.value)], purity: "pure" };
    case "styleObject": return { kind: "object-literal", fields: expr.fields.map((field) => ({ name: field.name, value: expression(field.value) })) };
    case "collectionFilter": return { kind: "collection", operation: "filter", source: expression(expr.source), details: { itemName: expr.itemName, predicate: expression(expr.predicate) } };
    case "collectionMap": return { kind: "collection", operation: "map", source: expression(expr.source), details: { itemName: expr.itemName, projection: expression(expr.projection) } };
    case "collectionReduce": return { kind: "collection", operation: "reduce", source: expression(expr.source), details: { accumulatorName: expr.accumulatorName, itemName: expr.itemName, reducer: expression(expr.reducer), initial: expression(expr.initial) } };
    case "collectionMax": return { kind: "collection", operation: "max", source: expression(expr.source), details: { itemName: expr.itemName, operand: expression(expr.operand) } };
    case "collectionJoin": return { kind: "collection", operation: "join", source: expression(expr.source), details: { separator: expression(expr.separator) } };
    case "objectLookup": return { kind: "object-lookup", object: expression(expr.object), key: expression(expr.key) };
    case "objectLiteral": return { kind: "object-literal", fields: expr.fields.map((field) => ({ name: field.name, value: expression(field.value) })) };
    case "arrayLiteral": return { kind: "array-literal", items: expr.items.map(expression) };
    case "ternary": return { kind: "ternary", condition: expression(expr.condition), then: expression(expr.then), else: expression(expr.else) };
  }
}

function attribute(attr: AttrBinding, sourcePath: string): IRAttribute {
  return attr.kind === "static"
    ? { name: attr.name, value: attr.value, binding: "static", sourcePath }
    : { name: attr.name, value: expression(attr.value), binding: "dynamic", sourcePath };
}

function action(statement: Stmt): IRAction {
  return statement.kind === "setState"
    ? { kind: "set-state", target: statement.target, value: expression(statement.value) }
    : { kind: "invoke-callback", target: statement.target, args: statement.args.map(expression) };
}

function renderNode(node: Node, sourcePath: string, interactions: IRInteraction[]): IRRenderNode {
  switch (node.kind) {
    case "element": {
      const elementInteractions = node.events.map((event, index) => {
        const interaction: IRInteraction = { id: `${sourcePath}/events/${index}`, event: event.name, actions: event.body.map(action), sourcePath: `${sourcePath}/events/${index}` };
        interactions.push(interaction);
        return interaction;
      });
      return {
        kind: "element",
        tag: node.tag,
        attributes: node.attrs.map((attr) => attribute(attr, sourcePath)),
        interactions: elementInteractions,
        children: node.children.map((child, index) => renderNode(child, `${sourcePath}/children/${index}`, interactions)),
        sourcePath,
      };
    }
    case "fragment": return { kind: "fragment", children: node.children.map((child, index) => renderNode(child, `${sourcePath}/children/${index}`, interactions)), sourcePath };
    case "text": return { kind: "text", value: expression(node.value), sourcePath };
    case "conditional": return { kind: "conditional", condition: expression(node.condition), then: renderNode(node.then, `${sourcePath}/then`, interactions), else: node.else === null ? null : renderNode(node.else, `${sourcePath}/else`, interactions), sourcePath };
    case "list": return { kind: "collection", source: expression(node.sourceExpression ?? { kind: "ident", name: node.source }), itemName: node.itemName, keyField: node.keyField ?? null, body: renderNode(node.body, `${sourcePath}/body`, interactions), sourcePath };
    case "component": return { kind: "component", name: node.name, props: node.props.map((prop) => ({ name: prop.name, value: expression(prop.value) })), sourcePath };
  }
}

function stateVariable(state: StateDef): IRStateVariable {
  const shape = state.stateShape ?? { kind: "primitive", primitive: state.stateType } satisfies ValueShape;
  const initial = "type" in state.initial
    ? { kind: "literal" as const, value: state.initial }
    : { kind: "expression" as const, value: expression(state.initial) };
  return { name: state.name, ownership: "LOCAL_EPHEMERAL", shape, initial, nullable: state.nullable === true || shape.nullable === true, sourcePath: `/state/${state.name}` };
}

function sourceFeatures(component: ComponentDef): Set<string> {
  const features = new Set<string>();
  const walk = (node: Node): void => {
    if (node.kind === "element") {
      const tag = node.tag as string;
      if (tag === "table" || tag === "tr" || tag === "td" || tag === "th") features.add("html-table");
      if (tag === "details") features.add("html-disclosure");
      if (tag === "svg") features.add("svg");
      node.children.forEach(walk);
      return;
    }
    if (node.kind === "fragment") node.children.forEach(walk);
    if (node.kind === "conditional") { walk(node.then); if (node.else) walk(node.else); }
    if (node.kind === "list") walk(node.body);
    if (node.kind === "component") features.add("component-composition");
  };
  walk(component.root);
  if (component.props.some((prop) => prop.kind === "data" && prop.valueShape?.kind === "slot")) features.add("slot-projection");
  return features;
}

function platformSemantics(component: ComponentDef, sourcePath: string): IRPlatformSemantic[] {
  const features = sourceFeatures(component);
  const result: IRPlatformSemantic[] = [];
  for (const [feature, domain] of [["html-table", "TABLE"], ["html-disclosure", "DISCLOSURE"], ["svg", "SVG"], ["slot-projection", "SLOT"]] as const) {
    if (features.has(feature)) result.push({ id: `${sourcePath}/platform/${feature}`, domain, sourceName: feature, requiredAdapter: null, disposition: "HAND_PORTED", sourcePath });
  }
  return result;
}

function styling(component: ComponentDef): IRStylingContract {
  const tokens: string[] = [];
  let source: IRStylingContract["source"] = "NONE";
  const walk = (node: Node): void => {
    if (node.kind === "element") {
      for (const attr of node.attrs) {
        if (attr.name === "class") source = "CLASS_ATTRIBUTE";
        if (attr.kind === "dynamic" && attr.value.kind === "cssModuleClass") {
          source = "CSS_MODULE";
          tokens.push(attr.value.className);
        }
      }
      node.children.forEach(walk);
    } else if (node.kind === "fragment") node.children.forEach(walk);
    else if (node.kind === "conditional") { walk(node.then); if (node.else) walk(node.else); }
    else if (node.kind === "list") walk(node.body);
  };
  walk(component.root);
  return { source, tokens: [...new Set(tokens)].sort(), targetPolicy: tokens.length > 0 ? "ADAPTER_REQUIRED" : "PRESERVE" };
}

function accessibility(component: ComponentDef): IRAccessibilityContract {
  const roles: string[] = [];
  const attrs: string[] = [];
  const keyboardEvents = new Set<string>();
  const walk = (node: Node): void => {
    if (node.kind === "element") {
      for (const attr of node.attrs) {
        if (attr.name === "role" && attr.kind === "static") roles.push(attr.value);
        if (attr.name.startsWith("aria-")) attrs.push(attr.name);
      }
      for (const event of node.events) if (event.name === "onClick" || event.name === "onSubmit") keyboardEvents.add(event.name);
      node.children.forEach(walk);
    } else if (node.kind === "fragment") node.children.forEach(walk);
    else if (node.kind === "conditional") { walk(node.then); if (node.else) walk(node.else); }
    else if (node.kind === "list") walk(node.body);
  };
  walk(component.root);
  return { roles: [...new Set(roles)].sort(), attributes: [...new Set(attrs)].sort(), focusable: roles.length > 0 || keyboardEvents.size > 0, keyboardEvents: [...keyboardEvents].sort(), localization: "SOURCE_TEXT_ONLY" };
}

function collections(component: ComponentDef): IRCollectionContract[] {
  const listProps = [...component.props, ...(component.lists ?? [])].filter((prop): prop is Extract<PropDef, { kind: "list" }> => prop.kind === "list");
  return listProps.map((list) => ({
    name: list.name,
    ownership: list.staticItems || list.staticValues ? "MODULE_CONSTANT" : component.state.some((state) => state.name === list.name) ? "STATE" : list.sourceExpression ? "DERIVED" : "PROP",
    elementShape: list.element.kind === "primitive" ? { kind: "primitive", primitive: list.element.primitive } : { kind: "object", fields: list.element.fields },
    identity: { strategy: list.element.kind === "primitive" ? "PRIMITIVE_VALUE" : "DECLARED_FIELD", field: list.keyField ?? null },
    operations: [],
    mutation: "READ_ONLY",
    sourcePath: `/collections/${list.name}`,
  }));
}

function obligationFor(code: string, reason: string, sourcePath: string): IRObligation {
  if (code.includes("TYPE") || code.includes("PROP")) return { id: `${sourcePath}/obligation/data-contract`, category: "data-contracts", reasonCode: code, disposition: "HAND_PORTED", description: reason, sourcePath, requiredEvidence: ["target-build", "browser-or-device", "independent-review"] };
  if (code.includes("TAG") || code.includes("ATTRIBUTE")) return { id: `${sourcePath}/obligation/platform`, category: "platform-semantics", reasonCode: code, disposition: "HAND_PORTED", description: reason, sourcePath, requiredEvidence: ["target-build", "browser-or-device", "accessibility-review"] };
  if (code.includes("STATEMENT") || code.includes("HOOK") || code.includes("EXPRESSION")) return { id: `${sourcePath}/obligation/effect`, category: "effects-and-resources", reasonCode: code, disposition: "BLOCKED", description: reason, sourcePath, requiredEvidence: ["controlled-network", "cancellation-cleanup", "independent-review"] };
  return { id: `${sourcePath}/obligation/unknown`, category: "render-tree", reasonCode: code, disposition: "BLOCKED", description: reason, sourcePath, requiredEvidence: ["target-build", "browser-or-device", "independent-review"] };
}

function digest(value: Omit<CrossPlatformComponentIR, "irDigest">): string {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
}

export function buildCrossPlatformIR(component: ComponentDef, sourceFramework: Framework, sourceFile = `${component.name}.source`): CrossPlatformComponentIR {
  const sourcePath = `/components/${component.name}`;
  const interactions: IRInteraction[] = [];
  const renderTree = renderNode(component.root, `${sourcePath}/render`, interactions);
  const features = sourceFeatures(component);
  const semantics = platformSemantics(component, sourcePath);
  const slots: IRSlotContract[] = component.props
    .filter((prop) => prop.kind === "data" && prop.valueShape?.kind === "slot")
    .map((prop) => ({ name: prop.name, ownership: "PARENT", evaluation: "PARENT", fallback: "NONE", status: "HAND_PORTED", sourcePath: `${sourcePath}/props/${prop.name}` }));
  const obligations: IRObligation[] = semantics.map((semantic) => ({
    id: semantic.id,
    category: semantic.domain === "SLOT" ? "slots-and-composition" : "platform-semantics",
    reasonCode: `CROSS_PLATFORM_${semantic.sourceName.toUpperCase().replaceAll("-", "_")}`,
    disposition: semantic.disposition === "HAND_PORTED" ? "HAND_PORTED" : "BLOCKED",
    description: `source semantic ${semantic.sourceName} needs an exact target adapter or human port`,
    sourcePath: semantic.sourcePath,
    requiredEvidence: ["target-build", "browser-or-device", "independent-review"],
  }));
  const canonicalWithoutDigest: Omit<CrossPlatformComponentIR, "irDigest"> = {
    schemaVersion: CROSS_PLATFORM_IR_SCHEMA_VERSION,
    kind: "elmos.cross-platform-component-ir",
    componentId: `${sourceFramework}:${sourceFile}:${component.name}`,
    source: { framework: sourceFramework, file: sourceFile, componentName: component.name, parserProfile: "certified-component-v1" },
    sourceTrace: { sourceFile, componentName: component.name, canonicalPath: sourcePath, sourceRange: null, traceStatus: "COMPONENT_MODEL_ONLY" },
    renderTree,
    state: {
      variables: component.state.map(stateVariable),
      transitions: interactions.flatMap((interaction) => interaction.actions.length === 0 ? [] : [{ id: `${interaction.id}/transition`, trigger: interaction.event, actions: interaction.actions, ordering: "SOURCE_ORDERED" as const, cancellation: "NOT_APPLICABLE" as const }]),
      effects: [],
      cleanupObligations: [],
    },
    interactions,
    collections: collections(component),
    slots,
    platformSemantics: semantics,
    styling: styling(component),
    accessibility: accessibility(component),
    obligations,
    targetAdapters: Object.fromEntries(ALL_FRAMEWORKS.map((target) => {
      const adapter = TARGET_ADAPTERS[target];
      const categoryModes = { ...adapter.categoryModes };
      if (features.has("slot-projection")) categoryModes["slots-and-composition"] = "HAND_PORTED";
      if (features.has("html-table") || features.has("html-disclosure") || features.has("svg")) categoryModes["platform-semantics"] = "HAND_PORTED";
      return [target, {
        targetFramework: target,
        adapterId: adapter.id,
        categoryModes,
        requiredRuntime: adapter.requiredRuntime,
        syntaxEvidence: adapter.syntaxEvidence,
        runtimeEvidence: adapter.runtimeEvidence,
      } satisfies TargetAdapterPlan];
    })) as Record<Framework, TargetAdapterPlan>,
    canonical: component,
  };
  return { ...canonicalWithoutDigest, irDigest: digest(canonicalWithoutDigest) };
}

export function classifyBlocker(code: string): { category: SemanticCategory; disposition: "HAND_PORTED" | "BLOCKED" } {
  if (code.includes("TYPE") || code.includes("PROP")) return { category: "data-contracts", disposition: "HAND_PORTED" };
  if (code.includes("TAG") || code.includes("ATTRIBUTE")) return { category: "platform-semantics", disposition: "HAND_PORTED" };
  if (code.includes("STATEMENT") || code.includes("HOOK") || code.includes("EXPRESSION") || code.includes("LITERAL")) return { category: "effects-and-resources", disposition: "BLOCKED" };
  if (code.includes("LIST") || code.includes("COLLECTION")) return { category: "derived-collections", disposition: "HAND_PORTED" };
  if (code.includes("SLOT") || code.includes("CHILD")) return { category: "slots-and-composition", disposition: "HAND_PORTED" };
  return { category: "render-tree", disposition: "BLOCKED" };
}
