/**
 * Canonical UI component model for the `certified-component-v1` profile.
 *
 * Mirrors the design of `engines/sql-dialect-engine`'s `models.py`: a small,
 * closed, precisely bounded set of constructs. Anything a parser encounters
 * outside this subset must raise `DialectError`, never be silently
 * approximated -- this is the fail-closed boundary of certified-component-v1
 * (see README.md for the full scope statement).
 */

export class RouteError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RouteError";
  }
}

/** Raised whenever input is outside the certified-component-v1 subset, or an
 * emitted component cannot be re-validated in the target framework. This is
 * the fail-closed signal: callers must treat this as BLOCKED, never as a
 * degraded success. */
export class DialectError extends Error {
  readonly code: string;
  readonly reason: string;

  constructor(code: string, reason: string) {
    super(`${code}: ${reason}`);
    this.name = "DialectError";
    this.code = code;
    this.reason = reason;
  }
}

export function fail(code: string, reason: string): never {
  throw new DialectError(code, reason);
}

/** Assertion form so TypeScript narrows on the checked condition -- the
 * fail-closed runtime check and the static narrowing stay in lockstep
 * instead of needing a second redundant `assert`. */
export function require_(condition: unknown, code: string, reason: string): asserts condition {
  if (!condition) fail(code, reason);
}

/** Narrowing form of `require_` for values that must be present. */
export function requireDefined<T>(value: T | undefined | null, code: string, reason: string): T {
  if (value === undefined || value === null) fail(code, reason);
  return value;
}

/** Narrowing indexed access for arrays whose bounds were just checked --
 * keeps `noUncheckedIndexedAccess` on (it catches real bugs) without
 * scattering non-null assertions through the parsers. */
export function at<T>(items: readonly T[], index: number, code: string, reason: string): T {
  const value = items[index];
  if (value === undefined) fail(code, reason);
  return value;
}

export type Framework =
  | "react" | "typescript" | "vue3" | "vue2" | "angular" | "svelte"
  | "react-native" | "miniprogram" | "arkui" | "flutter";

export const ALL_FRAMEWORKS: readonly Framework[] = [
  "react", "typescript", "vue3", "vue2", "angular", "svelte",
  "react-native", "miniprogram", "arkui", "flutter",
];

/**
 * Frameworks certified-component-v1 can use as a translation SOURCE,
 * because a real parser for them is installed and runs here:
 *   react / typescript / react-native -> TypeScript Compiler API (JSX)
 *   vue3                              -> @vue/compiler-sfc
 *   vue2                              -> vue-template-compiler
 *   angular                           -> @angular/compiler
 *   svelte                            -> svelte/compiler
 *   miniprogram                       -> @wxml/parser + TypeScript API
 *
 * `arkui` and `flutter` are deliberately absent. ArkTS's `struct` syntax is
 * not valid TypeScript and has no published standalone parser; Dart needs
 * the Dart SDK, which is not installed. Rather than hand-roll an
 * unverifiable regex "parser" for either, certified-component-v1 treats
 * them as emit-only targets and says so -- the same call
 * `engines/sql-dialect-engine` makes for Oracle/SQL-Server execution
 * validation.
 */
export const PARSEABLE_FRAMEWORKS: ReadonlySet<Framework> = new Set<Framework>([
  "react", "typescript", "vue3", "vue2", "angular", "svelte", "react-native", "miniprogram",
]);

/**
 * Frameworks with a real, dependency-free server renderer available here,
 * so two emitted components can actually be RUN against the same prop
 * values and their rendered DOM compared. This is stronger evidence than
 * syntax checking alone and is what catches "compiles clean, behaves
 * wrong" defects.
 *
 * Excluded, with the honest reason for each:
 *   angular      -- real SSR needs a platform-server application bootstrap
 *   react-native -- needs Metro plus a simulator/device
 *   miniprogram  -- needs the official WeChat devtools runtime
 *   arkui        -- needs DevEco Studio / a HarmonyOS device
 *   flutter      -- needs the Flutter/Dart SDK
 */
export const EXECUTABLE_FRAMEWORKS: ReadonlySet<Framework> = new Set<Framework>(["react", "typescript", "vue3", "vue2", "svelte"]);

export function isParseable(framework: Framework): boolean {
  return PARSEABLE_FRAMEWORKS.has(framework);
}

export type PrimitiveType = "string" | "number" | "boolean";

/**
 * A bounded structural value shape used for data props.
 *
 * The original profile only carried a primitive `propType`.  That made an
 * imported alias such as `CurrentUsageSnapshot["tokens"]` look unsupported
 * even when its fields were fully known to the TypeScript checker.  Keeping
 * the shape in the canonical model lets every emitter preserve the contract
 * without falling back to `any` or a target-specific guess.
 */
export type ValueShape =
  | { kind: "primitive"; primitive: PrimitiveType; nullable?: boolean }
  | { kind: "object"; fields: Record<string, { shape: ValueShape; optional: boolean }>; nullable?: boolean }
  | { kind: "array"; element: ValueShape; nullable?: boolean }
  /** A framework slot such as React's `children`; it is not a data object. */
  | { kind: "slot"; slotName: "children"; nullable?: boolean };

export type Literal =
  | { type: "string"; value: string }
  | { type: "number"; value: number }
  | { type: "boolean"; value: boolean }
  | { type: "null" };

export function literalType(literal: Literal): PrimitiveType {
  require_(literal.type !== "null", "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", "null cannot initialize a non-null primitive state");
  return literal.type;
}

/**
 * The shape of one element in a list prop.
 *
 * Two forms are certified, in increasing order of what real code needs:
 *  - a bare primitive (`string[]`), read in the body as the loop variable
 *    itself;
 *  - an object whose fields retain their structural `ValueShape` (optional /
 *    nullable fields included), read through a validated path such as
 *    `item.build_analysis.total`.
 *
 * The path is still bounded by the declared shape: an undeclared field,
 * nullable traversal, or an object rendered as a scalar fails validation.
 * This is deliberately narrower than general JavaScript property access.
 */
export type ListElementShape =
  | { kind: "primitive"; primitive: PrimitiveType }
  | { kind: "object"; fields: Record<string, { shape: ValueShape; optional: boolean }> };

/** A compile-time collection owned by the source module.  It is admitted
 * only when every item is a closed object of primitive literal fields; the
 * target emitters materialize it as data rather than treating a source
 * module's mutable array as a prop. */
export interface StaticListItem {
  fields: Readonly<Record<string, Literal>>;
}

/** A plain data prop, e.g. `name: string`. */
export interface DataPropDef {
  kind: "data";
  name: string;
  propType: PrimitiveType;
  /** Present for structured/imported props; primitive props keep the legacy
   * `propType` as the compact representation. */
  valueShape?: ValueShape;
  required: boolean;
  /** Only set (and only meaningful) when `required` is false. */
  defaultValue?: Literal;
}

/**
 * An array-typed prop that a list node iterates over, e.g.
 * `items: { id: number; label: string }[]`.
 *
 * List props are a separate kind rather than a `propType` variant because
 * nothing else in the profile may touch them: they cannot be interpolated,
 * bound to an attribute, compared, or passed to a callback. The ONLY legal
 * use is as the source of a `list` render node. That restriction is what
 * keeps every target's rendering provably equivalent.
 */
export interface ListPropDef {
  kind: "list";
  name: string;
  element: ListElementShape;
  /** Present for a list nested under a structured object prop, e.g. `semantic.subjects`. */
  sourceExpression?: Expr;
  /**
   * Field used as the render key. Required for object elements because
   * every target framework needs a stable identity for list diffing
   * (React `key`, Vue `:key`, Svelte `(expr)`, WeChat `wx:key`). For
   * primitive elements the item value itself is the key.
   */
  keyField?: string;
  /** Exact immutable source items for a bounded module-level collection. */
  staticItems?: readonly StaticListItem[];
  /** Exact immutable primitive values for a bounded module-level collection. */
  staticValues?: readonly Literal[];
}

/** A callback prop the component invokes on user interaction, e.g.
 * `onSubmit: (value: string) => void`. Certified-component-v1 supports 0 or
 * 1 parameter -- the exact shape needed for the certified event-handler
 * bodies below, nothing more general. */
export interface CallbackPropDef {
  kind: "callback";
  name: string;
  paramType?: PrimitiveType;
}

export type PropDef = DataPropDef | CallbackPropDef | ListPropDef;

export interface StateDef {
  name: string;
  stateType: PrimitiveType;
  /** Primitive state keeps the legacy stateType/initial representation.  A
   * structured state uses stateShape plus an immutable literal expression;
   * the shape is still closed and target emitters must preserve it. */
  initial: Literal | Expr;
  stateShape?: ValueShape;
  /** True when the source state is explicitly nullable, e.g. `useState<string | null>(null)`. */
  nullable?: boolean;
}

export type BinaryOperator = "+" | "-" | "*" | "/" | "%" | "<" | "<=" | ">" | ">=" | "==" | "!=" | "&&" | "||" | "??";
export const BINARY_OPERATORS: readonly BinaryOperator[] = ["+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||", "??"];
export type StringMethod = "toUpperCase" | "toLowerCase" | "toLocaleLowerCase" | "trim" | "replaceAll" | "includes" | "startsWith" | "endsWith" | "slice";
export type NumericFunction = "min" | "max" | "floor" | "ceil" | "abs" | "round";
export type NumericPredicate = "isFinite";

export type Expr =
  | { kind: "ident"; name: string }
  /**
   * A single-level field read off a list's loop variable, e.g. `item.name`.
   * `object` must be the item variable of an enclosing `list` node and
   * `field` must be declared in that list's element shape -- both are
   * enforced by `validateComponent`. Deeper paths are not certified.
   */
  | { kind: "member"; object: string; field: string }
  | { kind: "path"; object: string; fields: string[] }
  | { kind: "literal"; literal: Literal }
  | { kind: "binary"; operator: BinaryOperator; left: Expr; right: Expr }
  | { kind: "unaryNot"; operand: Expr }
  | { kind: "stringMethod"; method: StringMethod; receiver: Expr; args: Expr[] }
  /** A bounded pure numeric aggregate. It mirrors Math.min/Math.max without
   * opening the expression subset to arbitrary global calls. */
  | { kind: "numericFunction"; function: NumericFunction; args: Expr[] }
  /** A bounded numeric predicate with a target-native spelling. */
  | { kind: "numericPredicate"; predicate: NumericPredicate; operand: Expr }
  /** A bounded fixed-point conversion used by presentation helpers such as
   * `(bps / 100).toFixed(2)`. It is not a general JavaScript method call. */
  | { kind: "numberMethod"; method: "toFixed"; receiver: Expr; fractionDigits: number }
  /** The repository's explicitly allowlisted quota formatter. Keeping this
   * semantic instead of importing arbitrary helpers prevents a target from
   * guessing at locale or rounding behavior. */
  | { kind: "numberFormat"; format: "grouped"; locale?: "zh-CN" | "en-US"; operand: Expr }
  /** A static class token imported from a CSS Module. */
  | { kind: "cssModuleClass"; className: string }
  /** The value supplied by an input/change event; its concrete spelling is
   * selected by each target emitter. */
  | { kind: "eventValue" }
  /** A bounded, stateless regular-expression predicate. Global/sticky flags
   * are excluded because JavaScript's lastIndex makes them stateful across
   * renders and therefore non-equivalent on several targets. */
  | { kind: "regexTest"; pattern: string; flags: string; operand: Expr }
  | { kind: "arrayLength"; operand: Expr }
  /** A cross-target layout primitive for a percentage-sized fill. This is
   * deliberately narrower than accepting arbitrary CSS style objects. */
  | { kind: "percentageWidth"; value: Expr }
  | { kind: "styleObject"; fields: { name: "width"; value: Expr }[] }
  /** A single-pass, read-only list derivation.  The source must resolve to a
   * declared list and the predicate is checked in the derived item scope. */
  | { kind: "collectionFilter"; source: Expr; itemName: string; predicate: Expr }
  /** A read-only projection over a declared list. */
  | { kind: "collectionMap"; source: Expr; itemName: string; projection: Expr }
  /** A bounded numeric fold with an explicit initial value. */
  | { kind: "collectionReduce"; source: Expr; accumulatorName: string; itemName: string; reducer: Expr; initial: Expr }
  /** A numeric maximum over a declared list projection. */
  | { kind: "collectionMax"; source: Expr; itemName: string; operand: Expr }
  /** A bounded join of a string collection with an explicit separator. */
  | { kind: "collectionJoin"; source: Expr; separator: Expr }
  /** A typed lookup on a closed record/object value. */
  | { kind: "objectLookup"; object: Expr; key: Expr }
  /** Closed object/array values used by typed local state.  These are not a
   * general object escape hatch: validation checks every field/item and
   * rejects bare structured reads in rendered text. */
  | { kind: "objectLiteral"; fields: { name: string; value: Expr }[]; computedFields?: { key: Expr; value: Expr }[] }
  | { kind: "arrayLiteral"; items: Expr[] }
  | { kind: "ternary"; condition: Expr; then: Expr; else: Expr };

/** One statement inside an event handler body. Certified-component-v1 event
 * handlers are a flat list of these two statement kinds only -- no loops, no
 * conditionals inside a handler body (branch in the render tree instead),
 * no arbitrary function calls, no async. */
export type Stmt =
  | { kind: "setState"; target: string; value: Expr }
  | { kind: "callProp"; target: string; args: Expr[] };

/** True when an event handler reads the platform-provided input value. This
 * is kept in the canonical model so each emitter can bind the value using
 * its own event convention instead of emitting an unbound `event` name. */
export function usesEventValue(expr: Expr): boolean {
  switch (expr.kind) {
    case "eventValue": return true;
    case "binary": return usesEventValue(expr.left) || usesEventValue(expr.right);
    case "unaryNot": return usesEventValue(expr.operand);
    case "stringMethod": return usesEventValue(expr.receiver) || expr.args.some(usesEventValue);
    case "numericFunction": return expr.args.some(usesEventValue);
    case "numericPredicate": return usesEventValue(expr.operand);
    case "numberMethod": return usesEventValue(expr.receiver);
    case "numberFormat": return usesEventValue(expr.operand);
    case "cssModuleClass": return false;
    case "regexTest": return usesEventValue(expr.operand);
    case "arrayLength": return usesEventValue(expr.operand);
    case "percentageWidth": return usesEventValue(expr.value);
    case "styleObject": return expr.fields.some((field) => usesEventValue(field.value));
    case "collectionFilter": return usesEventValue(expr.source) || usesEventValue(expr.predicate);
    case "collectionMap": return usesEventValue(expr.source) || usesEventValue(expr.projection);
    case "collectionReduce": return usesEventValue(expr.source) || usesEventValue(expr.reducer) || usesEventValue(expr.initial);
    case "collectionMax": return usesEventValue(expr.source) || usesEventValue(expr.operand);
    case "collectionJoin": return usesEventValue(expr.source) || usesEventValue(expr.separator);
    case "objectLookup": return usesEventValue(expr.object) || usesEventValue(expr.key);
    case "objectLiteral": return expr.fields.some((field) => usesEventValue(field.value)) || (expr.computedFields ?? []).some((field) => usesEventValue(field.key) || usesEventValue(field.value));
    case "arrayLiteral": return expr.items.some(usesEventValue);
    case "ternary": return usesEventValue(expr.condition) || usesEventValue(expr.then) || usesEventValue(expr.else);
    default: return false;
  }
}

export function usesEventValueInStatements(statements: readonly Stmt[]): boolean {
  return statements.some((statement) => statement.kind === "setState"
    ? usesEventValue(statement.value)
    : statement.args.some(usesEventValue));
}

/**
 * Bounded element allowlist. Extend only with a verified rendering rule on
 * EVERY target, never on the web ones alone.
 *
 * The semantic containers below (`section`...`aside`) were admitted after a
 * coverage scan of real application code showed them blocking whole files.
 * Each is a plain block container with an honest equivalent everywhere:
 * the same tag on the web targets, `View` on React Native, `view` on
 * WeChat, and a `Column` on ArkUI and Flutter -- exactly what `div`
 * already does.
 *
 * Deliberately still OUT, because there is no honest equivalent on the
 * non-web targets and emitting an approximation would produce a component
 * that compiles and lays out wrongly:
 *
 *   - `table`/`thead`/`tbody`/`tr`/`td`/`th` -- React Native, ArkUI and
 *     Flutter have no table model. Faking one with nested rows changes
 *     column sizing, spanning and accessibility semantics.
 *   - `form` -- React Native has no form element and no submit event;
 *     `onSubmit` would have to be silently dropped.
 *   - `img`/`video` -- need asset resolution and a per-target source
 *     model, which is a feature, not a tag entry.
 */
export const HTML_TAGS = [
  "div", "span", "p", "button", "input", "label", "a",
  "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "strong", "em", "i",
  "section", "article", "header", "footer", "nav", "main", "aside", "dl", "dt", "dd",
  "small", "code", "b", "br",
] as const;
export type HtmlTag = (typeof HTML_TAGS)[number];

export const ATTR_NAMES = [
  "class", "id", "href", "type", "placeholder", "value", "disabled", "name", "for", "checked",
  "maxLength",
  "role", "aria-hidden", "aria-label", "aria-labelledby", "aria-valuemin", "aria-valuemax", "aria-valuenow", "aria-valuetext", "aria-selected",
  "data-label", "tabIndex", "style",
] as const;
export type AttrName = (typeof ATTR_NAMES)[number];

export const EVENT_NAMES = ["onClick", "onChange", "onInput", "onSubmit"] as const;
export type EventName = (typeof EVENT_NAMES)[number];

export type AttrBinding =
  | { kind: "static"; name: AttrName; value: string }
  | { kind: "dynamic"; name: AttrName; value: Expr };

export interface EventBinding {
  name: EventName;
  body: Stmt[];
}

export type Node =
  | { kind: "element"; tag: HtmlTag; attrs: AttrBinding[]; events: EventBinding[]; children: Node[] }
  /** A JSX fragment is a transparent grouping with no rendered DOM node. */
  | { kind: "fragment"; children: Node[] }
  | { kind: "text"; value: Expr }
  | { kind: "conditional"; condition: Expr; then: Node; else: Node | null }
  /**
   * List rendering: `items.map(item => <li>...</li>)`, `v-for`, `wx:for`,
   * `{#each}`, `*ngFor`, `ForEach`, `.map(...).toList()`.
   *
   * `source` names a declared `ListPropDef`; `itemName` binds the loop
   * variable inside `body`; `body` is exactly ONE element node, because
   * every target framework attaches the loop construct to a single element
   * (or would need a framework-specific fragment wrapper that changes the
   * rendered DOM). Nested lists are rejected -- see validateComponent.
   */
  | { kind: "list"; source: string; sourceExpression?: Expr; itemName: string; body: Node; keyField?: string }
  /**
   * A reference to ANOTHER certified component: `<Child label={title} />`.
   *
   * This is what makes the subset compositional instead of a collection of
   * isolated leaves, and a coverage scan of real code showed it was the
   * single most common thing mistaken for an "unsupported tag".
   *
   * Bounded deliberately:
   *
   *  - **No children / slots.** Every target models slot projection
   *    differently (`children`, `<slot>`, `<ng-content>`, `<slot name>`,
   *    ArkUI's `@BuilderParam`), and they differ in whether the content is
   *    evaluated by the parent or the child. That is a separate feature.
   *  - **Props only, no event bindings.** A child's callback prop would
   *    need a handler body in the parent, which is a different scoping
   *    problem from an element's own event.
   *  - **The child must resolve within the same run.** A single-component
   *    translation cannot know whether `Child` exists; the repository
   *    pipeline can and does cross-check it.
   */
  | { kind: "component"; name: string; props: ComponentArg[] };

/** One prop passed to a referenced child component. */
export interface ComponentArg {
  name: string;
  value: Expr;
}

export interface ComponentDef {
  name: string;
  props: PropDef[];
  state: StateDef[];
  root: Node;
  /** Derived list sources are kept out of the public prop signature while remaining typed in the canonical IR. */
  lists?: ListPropDef[];
}

const IDENTIFIER_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
const COMPONENT_NAME_RE = /^[A-Z][A-Za-z0-9]*$/;

export function checkIdentifier(name: string, what: string): void {
  require_(IDENTIFIER_RE.test(name), "CERTIFIED_COMPONENT_UNSUPPORTED_IDENTIFIER", `${what} ${JSON.stringify(name)} is not a plain [A-Za-z_][A-Za-z0-9_]* identifier`);
}

/** Validates a fully-constructed ComponentDef against certified-component-v1's
 * closed-world invariants (mirrors `Table.__post_init__` in the SQL engine's
 * models.py): every identifier referenced in expressions/handlers must
 * resolve to a declared prop or state variable, callback invocations must
 * target a declared callback prop, and there is exactly one root node. */
export function validateComponent(component: ComponentDef): void {
  checkIdentifier(component.name, "component name");
  require_(COMPONENT_NAME_RE.test(component.name), "CERTIFIED_COMPONENT_BAD_NAME", `component name ${JSON.stringify(component.name)} must be PascalCase`);

  const dataNames = new Set<string>();
  const callbackNames = new Set<string>();
  const listProps = new Map<string, ListPropDef>();
  const seenPropNames = new Set<string>();
  const validateStaticItems = (list: ListPropDef): void => {
    if (list.staticItems !== undefined) {
      require_(list.staticValues === undefined, "CERTIFIED_COMPONENT_STATIC_LIST_SHAPE", `static list ${JSON.stringify(list.name)} may not mix object and primitive values`);
      require_(list.element.kind === "object", "CERTIFIED_COMPONENT_STATIC_LIST_SHAPE", `static list ${JSON.stringify(list.name)} must have object elements`);
      const fieldNames = Object.keys(list.element.fields).sort();
      require_(list.staticItems.length > 0, "CERTIFIED_COMPONENT_STATIC_LIST_EMPTY", `static list ${JSON.stringify(list.name)} must contain at least one item so its element shape is explicit`);
      for (const [index, item] of list.staticItems.entries()) {
        const itemNames = Object.keys(item.fields).sort();
        require_(JSON.stringify(itemNames) === JSON.stringify(fieldNames), "CERTIFIED_COMPONENT_STATIC_LIST_SHAPE", `static list ${JSON.stringify(list.name)} item ${index} does not match the declared field set`);
        for (const fieldName of fieldNames) {
          const literal = item.fields[fieldName];
          const field = list.element.fields[fieldName];
          require_(literal !== undefined && field !== undefined, "CERTIFIED_COMPONENT_STATIC_LIST_SHAPE", `static list ${JSON.stringify(list.name)} item ${index} is missing field ${JSON.stringify(fieldName)}`);
          require_(field.shape.kind === "primitive" && literal.type !== "null" && literal.type === field.shape.primitive,
            "CERTIFIED_COMPONENT_STATIC_LIST_SHAPE", `static list ${JSON.stringify(list.name)} field ${JSON.stringify(fieldName)} has a literal type that does not match its declared primitive shape`);
        }
      }
    }
    if (list.staticValues !== undefined) {
      require_(list.staticItems === undefined, "CERTIFIED_COMPONENT_STATIC_LIST_SHAPE", `static list ${JSON.stringify(list.name)} may not mix primitive and object values`);
      require_(list.element.kind === "primitive", "CERTIFIED_COMPONENT_STATIC_LIST_SHAPE", `static list ${JSON.stringify(list.name)} must have primitive elements`);
      require_(list.staticValues.length > 0, "CERTIFIED_COMPONENT_STATIC_LIST_EMPTY", `static list ${JSON.stringify(list.name)} must contain at least one value`);
      for (const value of list.staticValues) {
        require_(value.type !== "null" && value.type === list.element.primitive, "CERTIFIED_COMPONENT_STATIC_LIST_SHAPE", `static list ${JSON.stringify(list.name)} contains a value outside its declared primitive shape`);
      }
    }
  };
  for (const prop of component.props) {
    checkIdentifier(prop.name, "prop name");
    require_(!seenPropNames.has(prop.name), "CERTIFIED_COMPONENT_DUPLICATE_PROP", `duplicate prop name ${JSON.stringify(prop.name)}`);
    seenPropNames.add(prop.name);
    if (prop.kind === "data") {
      dataNames.add(prop.name);
      if (prop.valueShape?.kind === "slot") {
        // Slots are readable as identifiers in the source JSX/template, but
        // are emitted through each target's native projection primitive.
      }
    } else if (prop.kind === "list") {
      if (prop.element.kind === "object") {
        const fieldNames = Object.keys(prop.element.fields);
        require_(fieldNames.length > 0, "CERTIFIED_COMPONENT_EMPTY_LIST_ELEMENT", `list prop ${JSON.stringify(prop.name)} declares an object element with no fields`);
        fieldNames.forEach((f) => checkIdentifier(f, `list element field of ${prop.name}`));
        // Every target needs a stable list identity, and none of them can
        // synthesise one from an object without being told which field it is.
        const keyField = prop.keyField;
        require_(keyField !== undefined, "CERTIFIED_COMPONENT_MISSING_LIST_KEY", `list prop ${JSON.stringify(prop.name)} has object elements and must declare a key field`);
        require_(Object.prototype.hasOwnProperty.call(prop.element.fields, keyField as string), "CERTIFIED_COMPONENT_UNKNOWN_LIST_KEY", `list prop ${JSON.stringify(prop.name)} key field ${JSON.stringify(keyField)} is not one of its declared fields`);
      } else {
        require_(prop.keyField === undefined, "CERTIFIED_COMPONENT_UNEXPECTED_LIST_KEY", `list prop ${JSON.stringify(prop.name)} has primitive elements, which are their own key; keyField must be omitted`);
      }
      validateStaticItems(prop);
      listProps.set(prop.name, prop);
    } else {
      require_(/^on[A-Z]/.test(prop.name) || /^set[A-Z]/.test(prop.name), "CERTIFIED_COMPONENT_BAD_CALLBACK_NAME", `callback prop ${JSON.stringify(prop.name)} must start with "on" or "set" followed by an uppercase letter`);
      callbackNames.add(prop.name);
    }
  }
  for (const list of component.lists ?? []) {
    require_(!listProps.has(list.name), "CERTIFIED_COMPONENT_DUPLICATE_LIST", `duplicate derived list source ${JSON.stringify(list.name)}`);
    validateStaticItems(list);
    listProps.set(list.name, list);
  }

  const stateNames = new Set<string>();
  const stateShapes = new Map<string, ValueShape>();
  for (const s of component.state) {
    checkIdentifier(s.name, "state name");
    require_(!stateNames.has(s.name) && !dataNames.has(s.name) && !callbackNames.has(s.name), "CERTIFIED_COMPONENT_DUPLICATE_STATE", `duplicate/shadowing state name ${JSON.stringify(s.name)}`);
    const shape = s.stateShape ?? { kind: "primitive", primitive: s.stateType } satisfies ValueShape;
    stateShapes.set(s.name, shape);
    if (isLiteralValue(s.initial) && s.initial.type === "null") {
      require_(s.nullable === true || shape.nullable === true, "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(s.name)} is initialized with null but is not declared nullable`);
    } else {
      validateStateInitial(s.initial, shape, s.name);
    }
    require_(shape.kind === "primitive" ? shape.primitive === s.stateType : true, "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(s.name)} legacy type does not match its structural shape`);
    stateNames.add(s.name);
  }
  const readableNames = new Set([...dataNames, ...stateNames]);

  function isLiteralValue(value: Literal | Expr): value is Literal {
    return "type" in value;
  }

  function validateStateInitial(value: Literal | Expr, shape: ValueShape, name: string): void {
    if (isLiteralValue(value)) {
      if (value.type === "null") {
        require_(shape.nullable === true, "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(name)} initial value is null but its structural shape is not nullable`);
        return;
      }
      require_(shape.kind === "primitive" && value.type === shape.primitive, "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(name)} initial literal does not match its declared structural shape`);
      return;
    }
    // Structured literals store their leaf values as Expr nodes so the same
    // canonical representation can be emitted from props, state and derived
    // collections. Unwrap that explicit literal wrapper before validating the
    // leaf shape; do not accept any other expression as a state initializer.
    if (value.kind === "literal") {
      validateStateInitial(value.literal, shape, name);
      return;
    }
    if (value.kind === "arrayLiteral") {
      require_(shape.kind === "array", "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(name)} initial array does not match its declared structural shape`);
      value.items.forEach((item) => validateStateInitial(item, shape.element, name));
      return;
    }
    if (value.kind === "objectLiteral") {
      require_(shape.kind === "object", "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(name)} initial object does not match its declared structural shape`);
      const fields = new Map(shape.fields && Object.entries(shape.fields).map(([field, definition]) => [field, definition]));
      const seen = new Set<string>();
      for (const field of value.fields) {
        checkIdentifier(field.name, `state ${name} field`);
        require_(!seen.has(field.name), "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(name)} initial object repeats field ${JSON.stringify(field.name)}`);
        const definition = fields.get(field.name);
        require_(definition !== undefined, "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(name)} initial object has undeclared field ${JSON.stringify(field.name)}`);
        validateStateInitial(field.value, definition.shape, `${name}.${field.name}`);
        seen.add(field.name);
      }
      for (const [field, definition] of fields) require_(definition.optional || seen.has(field), "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(name)} initial object is missing required field ${JSON.stringify(field)}`);
      return;
    }
    fail("CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", `state ${JSON.stringify(name)} initial value must be a closed literal object or array`);
  }

  /** Loop variables currently in scope: item name -> the list it came from. */
  type Scope = ReadonlyMap<string, ListPropDef>;
  const EMPTY_SCOPE: Scope = new Map();

  function listElementFromValueShape(shape: ValueShape): ListElementShape | undefined {
    if (shape.kind === "primitive" && shape.nullable !== true) return { kind: "primitive", primitive: shape.primitive };
    if (shape.kind === "object" && shape.nullable !== true) return { kind: "object", fields: shape.fields };
    return undefined;
  }

  function sourceListForExpression(expr: Expr): ListPropDef | undefined {
    if (expr.kind === "ident") return listProps.get(expr.name);
    if (expr.kind === "member") return listProps.get(expr.object + "." + expr.field);
    if (expr.kind === "collectionFilter") return sourceListForExpression(expr.source);
    if (expr.kind === "collectionMap") {
      const source = sourceListForExpression(expr.source);
      if (source === undefined) return undefined;
      const inner = new Map<string, ListPropDef>();
      inner.set(expr.itemName, source);
      const projectedShape = expressionShape(expr.projection, inner);
      if (projectedShape === null) return undefined;
      const projected = listElementFromValueShape(projectedShape);
      return projected === undefined ? undefined : { kind: "list", name: `${source.name}.map`, element: projected };
    }
    return undefined;
  }

  function numericBinding(name: string): ListPropDef {
    return { kind: "list", name, element: { kind: "primitive", primitive: "number" } };
  }

  function checkExpr(expr: Expr, scope: Scope, allowStructuredReference = false): void {
    switch (expr.kind) {
      case "ident": {
        const list = scope.get(expr.name);
        if (list !== undefined) {
          // A bare loop variable is only readable when the element is a
          // primitive; an object element has no meaningful string form and
          // every framework would stringify it differently.
          require_(list.element.kind === "primitive", "CERTIFIED_COMPONENT_OBJECT_ITEM_READ", `loop variable ${JSON.stringify(expr.name)} has object elements and must be read as ${expr.name}.<field>`);
          return;
        }
        require_(readableNames.has(expr.name), "CERTIFIED_COMPONENT_UNKNOWN_IDENTIFIER", `identifier ${JSON.stringify(expr.name)} is not a declared prop or state variable`);
        const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.name);
        require_(allowStructuredReference || (data?.valueShape?.kind !== "object" && data?.valueShape?.kind !== "array"),
          "CERTIFIED_COMPONENT_OBJECT_PROP_READ", `structured prop ${JSON.stringify(expr.name)} must be read through a declared field or list usage, not rendered as a bare value`);
        const stateShape = stateShapes.get(expr.name);
        require_(allowStructuredReference || (stateShape?.kind !== "object" && stateShape?.kind !== "array"),
          "CERTIFIED_COMPONENT_OBJECT_PROP_READ", `structured state ${JSON.stringify(expr.name)} must be read through a declared field or list usage, not rendered as a bare value`);
        return;
      }
      case "member": {
        const list = scope.get(expr.object);
        if (list !== undefined) {
          require_((list as ListPropDef).element.kind === "object", "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `loop variable ${JSON.stringify(expr.object)} has primitive elements and has no field ${JSON.stringify(expr.field)}`);
          const fields = ((list as ListPropDef).element as Extract<ListElementShape, { kind: "object" }>).fields;
          require_(Object.prototype.hasOwnProperty.call(fields, expr.field), "CERTIFIED_COMPONENT_UNKNOWN_LIST_FIELD", `${expr.object}.${expr.field} is not a declared field of list prop ${JSON.stringify(expr.object)}`);
          return;
        }
        const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.object);
        const shape = data?.valueShape;
        const stateShape = stateShapes.get(expr.object);
        const objectShape = shape?.kind === "object" ? shape : stateShape?.kind === "object" ? stateShape : undefined;
        require_(objectShape !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `${expr.object}.${expr.field} is outside certified-component-v1: field access requires a declared object prop or state`);
        require_(Object.prototype.hasOwnProperty.call(objectShape.fields, expr.field), "CERTIFIED_COMPONENT_UNKNOWN_PROP_FIELD", `${expr.object}.${expr.field} is not a declared field of structured value ${JSON.stringify(expr.object)}`);
        return;
      }
      case "path": {
        const shape = resolvePathShape(expr.object, expr.fields, scope);
        require_(shape !== null, "CERTIFIED_COMPONENT_UNKNOWN_PROP_FIELD", `${expr.object}.${expr.fields.join(".")} is not a declared structured field path`);
        return;
      }
      case "literal":
        return;
      case "objectLiteral":
        expr.fields.forEach((field) => { checkIdentifier(field.name, "object literal field"); checkExpr(field.value, scope); });
        for (const field of expr.computedFields ?? []) {
          checkExpr(field.key, scope);
          require_(isStringExpression(field.key, scope), "CERTIFIED_COMPONENT_OBJECT_LOOKUP_KEY", "computed object keys must be certified strings");
          checkExpr(field.value, scope);
        }
        return;
      case "arrayLiteral":
        expr.items.forEach((item) => checkExpr(item, scope));
        return;
      case "binary":
        const isNullLiteral = (value: Expr): boolean => value.kind === "literal" && value.literal.type === "null";
        const isStructuredExpression = (value: Expr): boolean => {
          const shape = expressionShape(value, scope);
          return shape?.kind === "object" || shape?.kind === "array" || shape?.kind === "slot";
        };
        const isNullablePresenceCheck = (expr.operator === "==" || expr.operator === "!=")
          && ((isNullLiteral(expr.left) && isStructuredExpression(expr.right)) || (isNullLiteral(expr.right) && isStructuredExpression(expr.left)));
        checkExpr(expr.left, scope, allowStructuredReference || isNullablePresenceCheck);
        checkExpr(expr.right, scope, allowStructuredReference || isNullablePresenceCheck);
        return;
      case "unaryNot":
        checkExpr(expr.operand, scope);
        return;
      case "stringMethod":
        checkExpr(expr.receiver, scope);
        require_(isStringExpression(expr.receiver, scope), "CERTIFIED_COMPONENT_STRING_METHOD_RECEIVER", `${expr.method} requires a certified string expression`);
        const expectedArgs = expr.method === "replaceAll" ? 2 : expr.method === "includes" || expr.method === "startsWith" || expr.method === "endsWith" || expr.method === "toLocaleLowerCase" ? 1 : expr.method === "slice" ? 1 : 0;
        require_(expr.method === "slice" ? expr.args.length <= 2 && expr.args.length >= 1 : expr.args.length === expectedArgs, "CERTIFIED_COMPONENT_STRING_METHOD_ARITY", `${expr.method} expects ${expr.method === "slice" ? "one or two" : expectedArgs} argument(s)`);
        expr.args.forEach((arg) => {
          checkExpr(arg, scope);
          const expectedType = expr.method === "slice" ? "number" : "string";
          require_(expr.method === "slice" ? isNumberExpression(arg, scope) : isStringExpression(arg, scope), "CERTIFIED_COMPONENT_STRING_METHOD_ARGUMENT", `${expr.method} arguments must be ${expectedType} expressions`);
        });
        if (expr.method === "toLocaleLowerCase") {
          require_(expr.args.length === 1 && expr.args[0]?.kind === "literal" && expr.args[0].literal.type === "string" && expr.args[0].literal.value === "zh-CN", "CERTIFIED_COMPONENT_STRING_METHOD_ARGUMENT", "toLocaleLowerCase is limited to the canonical zh-CN locale");
        }
        return;
      case "numericFunction":
        require_(expr.args.length >= 1 && expr.args.length <= 8, "CERTIFIED_COMPONENT_NUMERIC_FUNCTION_ARITY", `${expr.function} expects between 1 and 8 arguments`);
        expr.args.forEach((arg) => {
          checkExpr(arg, scope);
          require_(isNumberExpression(arg, scope), "CERTIFIED_COMPONENT_NUMERIC_FUNCTION_ARGUMENT", `${expr.function} arguments must be certified number expressions`);
        });
        return;
      case "numericPredicate":
        checkExpr(expr.operand, scope);
        require_(isNumberExpression(expr.operand, scope), `${expr.predicate.toUpperCase()}_OPERAND`, `${expr.predicate} requires a certified number expression`);
        return;
      case "numberMethod":
        checkExpr(expr.receiver, scope);
        require_(isNumberExpression(expr.receiver, scope), "CERTIFIED_COMPONENT_NUMBER_METHOD_RECEIVER", "toFixed requires a certified number expression");
        require_(Number.isInteger(expr.fractionDigits) && expr.fractionDigits >= 0 && expr.fractionDigits <= 20,
          "CERTIFIED_COMPONENT_NUMBER_METHOD_ARGUMENT", "toFixed fraction digits must be an integer from 0 through 20");
        return;
      case "numberFormat":
        checkExpr(expr.operand, scope);
        require_(isNumberExpression(expr.operand, scope), "CERTIFIED_COMPONENT_NUMBER_FORMAT_OPERAND", "grouped number formatting requires a certified number expression");
        return;
      case "cssModuleClass":
        checkIdentifier(expr.className, "CSS Module class name");
        return;
      case "eventValue":
        return;
      case "regexTest":
        checkExpr(expr.operand, scope);
        require_(isStringExpression(expr.operand, scope), "CERTIFIED_COMPONENT_REGEX_TEST_OPERAND", "regex test requires a certified string expression");
        require_(expr.pattern.length <= 256, "CERTIFIED_COMPONENT_REGEX_TEST_TOO_LONG", "regex pattern exceeds the 256-character certified bound");
        require_(/^[imsu]*$/.test(expr.flags) && new Set(expr.flags).size === expr.flags.length, "CERTIFIED_COMPONENT_REGEX_TEST_FLAGS", "regex test flags must be unique and limited to i/m/s/u");
        return;
      case "arrayLength":
        checkExpr(expr.operand, scope);
        require_(isArrayExpression(expr.operand, scope), "CERTIFIED_COMPONENT_ARRAY_LENGTH_OPERAND", "length requires a certified array expression");
        return;
      case "percentageWidth":
        checkExpr(expr.value, scope);
        require_(isNumberExpression(expr.value, scope), "CERTIFIED_COMPONENT_PERCENTAGE_WIDTH_VALUE", "percentage width requires a certified number expression");
        return;
      case "styleObject":
        require_(expr.fields.length === 1 && expr.fields[0]?.name === "width", "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "only a single percentage width style is certified");
        expr.fields.forEach((field) => {
          checkExpr(field.value, scope);
          require_(field.value.kind === "percentageWidth", "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "the certified width style must use a percentageWidth expression");
        });
        return;
      case "collectionFilter": {
        checkIdentifier(expr.itemName, "filter item variable");
        const sourceList = sourceListForExpression(expr.source);
        require_(sourceList !== undefined, "CERTIFIED_COMPONENT_FILTER_SOURCE", "filter source must be a declared list prop");
        // A list prop is intentionally not a generally readable value: it
        // may only enter the IR as the source of a list render or this
        // bounded filter.  Calling checkExpr first would reject the exact
        // list identifier we have just resolved as a certified collection.
        const inner = new Map(scope);
        inner.set(expr.itemName, sourceList);
        checkExpr(expr.predicate, inner);
        require_(isBooleanExpression(expr.predicate, inner), "CERTIFIED_COMPONENT_FILTER_PREDICATE", "filter predicate must be a certified boolean expression");
        return;
      }
      case "collectionMap": {
        checkIdentifier(expr.itemName, "map item variable");
        const sourceList = sourceListForExpression(expr.source);
        require_(sourceList !== undefined, "CERTIFIED_COMPONENT_MAP_SOURCE", "map source must be a declared list prop");
        const inner = new Map(scope);
        inner.set(expr.itemName, sourceList);
        checkExpr(expr.projection, inner);
        return;
      }
      case "collectionReduce": {
        checkIdentifier(expr.accumulatorName, "reduce accumulator variable");
        checkIdentifier(expr.itemName, "reduce item variable");
        require_(expr.accumulatorName !== expr.itemName, "CERTIFIED_COMPONENT_REDUCE_BINDING", "reduce accumulator and item variables must be distinct");
        const sourceList = sourceListForExpression(expr.source);
        require_(sourceList !== undefined, "CERTIFIED_COMPONENT_REDUCE_SOURCE", "reduce source must be a declared list prop");
        const inner = new Map(scope);
        inner.set(expr.accumulatorName, numericBinding(expr.accumulatorName));
        inner.set(expr.itemName, sourceList);
        checkExpr(expr.initial, scope);
        require_(isNumberExpression(expr.initial, scope), "CERTIFIED_COMPONENT_REDUCE_INITIAL", "reduce initial value must be a certified number expression");
        checkExpr(expr.reducer, inner);
        require_(isNumberExpression(expr.reducer, inner), "CERTIFIED_COMPONENT_REDUCE_RESULT", "reduce callback must return a certified number expression");
        return;
      }
      case "collectionMax": {
        checkIdentifier(expr.itemName, "max item variable");
        const sourceList = sourceListForExpression(expr.source);
        require_(sourceList !== undefined, "CERTIFIED_COMPONENT_MAX_SOURCE", "max source must be a declared list prop");
        const inner = new Map(scope);
        inner.set(expr.itemName, sourceList);
        checkExpr(expr.operand, inner);
        require_(isNumberExpression(expr.operand, inner), "CERTIFIED_COMPONENT_MAX_OPERAND", "max projection must be a certified number expression");
        return;
      }
      case "collectionJoin": {
        checkExpr(expr.source, scope);
        checkExpr(expr.separator, scope);
        require_(isStringExpression(expr.separator, scope), "CERTIFIED_COMPONENT_JOIN_SEPARATOR", "join separator must be a certified string expression");
        const sourceShape = expressionShape(expr.source, scope);
        require_(sourceShape?.kind === "array" && sourceShape.element.kind === "primitive" && sourceShape.element.primitive === "string",
          "CERTIFIED_COMPONENT_JOIN_SOURCE", "join source must be a certified string collection");
        return;
      }
      case "objectLookup": {
        checkExpr(expr.object, scope, true);
        checkExpr(expr.key, scope);
        require_(isStringExpression(expr.key, scope), "CERTIFIED_COMPONENT_OBJECT_LOOKUP_KEY", "object lookup keys must be certified strings");
        require_(lookupValueShape(expr.object, scope) !== null, "CERTIFIED_COMPONENT_OBJECT_LOOKUP_OBJECT", "object lookup requires a closed object or record with a uniform value shape");
        return;
      }
      case "ternary":
        checkExpr(expr.condition, scope);
        checkExpr(expr.then, scope);
        checkExpr(expr.else, scope);
        return;
    }
  }

  function isStringExpression(expr: Expr, scope: Scope): boolean {
    if (expr.kind === "literal") return expr.literal.type === "string";
    if (expr.kind === "cssModuleClass") return true;
    if (expr.kind === "eventValue") return true;
    if (expr.kind === "stringMethod") return expr.method !== "includes";
    if (expr.kind === "numberMethod" || expr.kind === "numberFormat") return true;
    if (expr.kind === "ident") {
      const list = scope.get(expr.name);
      if (list !== undefined) return list.element.kind === "primitive" && list.element.primitive === "string";
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.name);
      const shape = data?.valueShape;
      if (data !== undefined) return shape === undefined ? data.propType === "string" : shape.kind === "primitive" && shape.primitive === "string";
      const stateShape = stateShapes.get(expr.name);
      return stateShape?.kind === "primitive" && stateShape.primitive === "string";
    }
    if (expr.kind === "member") {
      const list = scope.get(expr.object);
      if (list?.element.kind === "object") {
        const field = list.element.fields[expr.field];
        return field?.shape.kind === "primitive" && field.shape.primitive === "string";
      }
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.object);
      const shape = data?.valueShape;
      const stateShape = stateShapes.get(expr.object);
      const objectShape = shape?.kind === "object" ? shape : stateShape?.kind === "object" ? stateShape : undefined;
      if (objectShape === undefined) return false;
      const field = objectShape.fields[expr.field];
      return field?.shape.kind === "primitive" && field.shape.primitive === "string";
    }
    if (expr.kind === "path") {
      const shape = resolvePathShape(expr.object, expr.fields, scope);
      return shape?.kind === "primitive" && shape.primitive === "string";
    }
    if (expr.kind === "binary" && expr.operator === "+") {
      const left = expressionShape(expr.left, scope);
      const right = expressionShape(expr.right, scope);
      return left?.kind === "primitive" && right?.kind === "primitive"
        && (left.primitive === "string" || right.primitive === "string");
    }
    if (expr.kind === "binary" && expr.operator === "??") return isStringExpression(expr.left, scope) && isStringExpression(expr.right, scope);
    if (expr.kind === "ternary") {
      const shape = expressionShape(expr, scope);
      return shape?.kind === "primitive" && shape.primitive === "string";
    }
    if (expr.kind === "collectionJoin") return true;
    if (expr.kind === "objectLookup") {
      const shape = expressionShape(expr, scope);
      return shape?.kind === "primitive" && shape.primitive === "string";
    }
    if (expr.kind === "objectLiteral" || expr.kind === "arrayLiteral") return false;
    return false;
  }

  function isBooleanExpression(expr: Expr, scope: Scope): boolean {
    if (expr.kind === "literal") return expr.literal.type === "boolean";
    if (expr.kind === "ident") {
      const list = scope.get(expr.name);
      if (list !== undefined) return list.element.kind === "primitive" && list.element.primitive === "boolean";
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.name);
      const shape = data?.valueShape;
      if (data !== undefined) return shape === undefined ? data.propType === "boolean" : shape.kind === "primitive" && shape.primitive === "boolean";
      const stateShape = stateShapes.get(expr.name);
      return stateShape?.kind === "primitive" && stateShape.primitive === "boolean";
    }
    if (expr.kind === "member") {
      const list = scope.get(expr.object);
      if (list?.element.kind === "object") {
        const field = list.element.fields[expr.field];
        return field?.shape.kind === "primitive" && field.shape.primitive === "boolean";
      }
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.object);
      const shape = data?.valueShape;
      const stateShape = stateShapes.get(expr.object);
      const objectShape = shape?.kind === "object" ? shape : stateShape?.kind === "object" ? stateShape : undefined;
      if (objectShape === undefined) return false;
      const field = objectShape.fields[expr.field];
      return field?.shape.kind === "primitive" && field.shape.primitive === "boolean";
    }
    if (expr.kind === "path") {
      const shape = resolvePathShape(expr.object, expr.fields, scope);
      return shape?.kind === "primitive" && shape.primitive === "boolean";
    }
    if (expr.kind === "unaryNot" || expr.kind === "numericPredicate" || expr.kind === "regexTest") return true;
    if (expr.kind === "stringMethod") return expr.method === "includes" || expr.method === "startsWith" || expr.method === "endsWith";
    if (expr.kind === "binary") return ["<", "<=", ">", ">=", "==", "!=", "&&", "||"].includes(expr.operator)
      ? expr.operator === "&&" || expr.operator === "||" ? isBooleanExpression(expr.left, scope) && isBooleanExpression(expr.right, scope) : true
      : false;
    if (expr.kind === "ternary") return isBooleanExpression(expr.then, scope) && isBooleanExpression(expr.else, scope);
    if (expr.kind === "objectLookup") {
      const shape = expressionShape(expr, scope);
      return shape?.kind === "primitive" && shape.primitive === "boolean";
    }
    if (expr.kind === "objectLiteral" || expr.kind === "arrayLiteral") return false;
    return false;
  }

  function isNumberExpression(expr: Expr, scope: Scope): boolean {
    if (expr.kind === "literal") return expr.literal.type === "number";
    if (expr.kind === "ident") {
      const list = scope.get(expr.name);
      if (list !== undefined) return list.element.kind === "primitive" && list.element.primitive === "number";
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.name);
      const shape = data?.valueShape;
      if (data !== undefined) return shape === undefined ? data.propType === "number" : shape.kind === "primitive" && shape.primitive === "number";
      const stateShape = stateShapes.get(expr.name);
      return stateShape?.kind === "primitive" && stateShape.primitive === "number";
    }
    if (expr.kind === "member") {
      const list = scope.get(expr.object);
      if (list?.element.kind === "object") {
        const field = list.element.fields[expr.field];
        return field?.shape.kind === "primitive" && field.shape.primitive === "number";
      }
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.object);
      const shape = data?.valueShape;
      const stateShape = stateShapes.get(expr.object);
      const objectShape = shape?.kind === "object" ? shape : stateShape?.kind === "object" ? stateShape : undefined;
      if (objectShape === undefined) return false;
      const field = objectShape.fields[expr.field];
      return field?.shape.kind === "primitive" && field.shape.primitive === "number";
    }
    if (expr.kind === "path") {
      const shape = resolvePathShape(expr.object, expr.fields, scope);
      return shape?.kind === "primitive" && shape.primitive === "number";
    }
    if (expr.kind === "binary") {
      return ["+", "-", "*", "/", "%"].includes(expr.operator)
        && isNumberExpression(expr.left, scope)
        && isNumberExpression(expr.right, scope);
    }
    if (expr.kind === "numericFunction") return expr.args.length > 0 && expr.args.every((arg) => isNumberExpression(arg, scope));
    if (expr.kind === "numberMethod") return false;
    if (expr.kind === "percentageWidth") return false;
    if (expr.kind === "collectionMax" || expr.kind === "collectionReduce") return true;
    if (expr.kind === "collectionJoin") return false;
    if (expr.kind === "ternary") return isNumberExpression(expr.then, scope) && isNumberExpression(expr.else, scope);
    if (expr.kind === "objectLookup") {
      const shape = expressionShape(expr, scope);
      return shape?.kind === "primitive" && shape.primitive === "number";
    }
    if (expr.kind === "objectLiteral" || expr.kind === "arrayLiteral") return false;
    return false;
  }

  function isArrayExpression(expr: Expr, scope: Scope): boolean {
    if (expr.kind === "ident") {
      const list = scope.get(expr.name);
      if (list !== undefined) return true;
      if (listProps.has(expr.name)) return true;
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.name);
      return data?.valueShape?.kind === "array" || stateShapes.get(expr.name)?.kind === "array";
    }
    if (expr.kind === "member") {
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.object);
      const shape = data?.valueShape;
      const stateShape = stateShapes.get(expr.object);
      const objectShape = shape?.kind === "object" ? shape : stateShape?.kind === "object" ? stateShape : undefined;
      return objectShape?.fields[expr.field]?.shape.kind === "array";
    }
    if (expr.kind === "path") return resolvePathShape(expr.object, expr.fields, scope)?.kind === "array";
    if (expr.kind === "collectionFilter") return isArrayExpression(expr.source, scope);
    if (expr.kind === "collectionMap") return true;
    if (expr.kind === "collectionJoin") return false;
    return false;
  }

  function resolvePathShape(object: string, fields: readonly string[], scope: Scope): ValueShape | null {
    let shape: ValueShape | undefined;
    const list = scope.get(object);
    if (list !== undefined) {
      if (list.element.kind !== "object") return null;
      const first = fields[0];
      if (first === undefined) return null;
      shape = list.element.fields[first]?.shape;
      fields = fields.slice(1);
    } else {
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === object);
      shape = data?.valueShape ?? stateShapes.get(object);
    }
    for (const field of fields) {
      if (shape?.kind !== "object") return null;
      shape = shape.fields[field]?.shape;
    }
    return shape ?? null;
  }

  function checkStmt(stmt: Stmt, scope: Scope): void {
    if (stmt.kind === "setState") {
      require_(stateNames.has(stmt.target), "CERTIFIED_COMPONENT_UNKNOWN_STATE_TARGET", `setState target ${JSON.stringify(stmt.target)} is not a declared state variable`);
      checkExpr(stmt.value, scope);
    } else {
      require_(callbackNames.has(stmt.target), "CERTIFIED_COMPONENT_UNKNOWN_CALLBACK_TARGET", `callProp target ${JSON.stringify(stmt.target)} is not a declared callback prop`);
      require_(stmt.args.length <= 1, "CERTIFIED_COMPONENT_TOO_MANY_CALLBACK_ARGS", `callProp ${JSON.stringify(stmt.target)} passes more than one argument`);
      stmt.args.forEach((a) => checkExpr(a, scope));
    }
  }

  /** Returns the structural shape when it is knowable.  Text and attribute
   * bindings may consume primitive values, but must never stringify an
   * object/array differently on each target. */
  function expressionShape(expr: Expr, scope: Scope): ValueShape | null {
    if (expr.kind === "literal") {
      return expr.literal.type === "null" ? null : { kind: "primitive", primitive: expr.literal.type };
    }
    if (expr.kind === "ident") {
      const list = scope.get(expr.name);
      if (list?.element.kind === "object") return { kind: "object", fields: list.element.fields };
      if (list?.element.kind === "primitive") return { kind: "primitive", primitive: list.element.primitive };
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.name);
      return data?.valueShape ?? stateShapes.get(expr.name) ?? null;
    }
    if (expr.kind === "member") {
      const list = scope.get(expr.object);
      if (list?.element.kind === "object") return list.element.fields[expr.field]?.shape ?? null;
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.object);
      const stateShape = stateShapes.get(expr.object);
      const objectShape = data?.valueShape?.kind === "object" ? data.valueShape : stateShape?.kind === "object" ? stateShape : undefined;
      return objectShape?.fields[expr.field]?.shape ?? null;
    }
    if (expr.kind === "path") return resolvePathShape(expr.object, expr.fields, scope);
    if (expr.kind === "eventValue") return { kind: "primitive", primitive: "string" };
    if (expr.kind === "binary") {
      const left = expressionShape(expr.left, scope);
      const right = expressionShape(expr.right, scope);
      if (expr.operator === "??") return right ?? left;
      if (expr.operator === "+") {
        if (left?.kind === "primitive" && right?.kind === "primitive") {
          if (left.primitive === "string" || right.primitive === "string") return { kind: "primitive", primitive: "string" };
          if (left.primitive === "number" && right.primitive === "number") return { kind: "primitive", primitive: "number" };
        }
      }
      if (["-", "*", "/", "%"].includes(expr.operator) && isNumberExpression(expr.left, scope) && isNumberExpression(expr.right, scope)) {
        return { kind: "primitive", primitive: "number" };
      }
      if (["<", "<=", ">", ">=", "==", "!=", "&&", "||"].includes(expr.operator)) return { kind: "primitive", primitive: "boolean" };
      return null;
    }
    if (expr.kind === "unaryNot" || expr.kind === "numericPredicate" || expr.kind === "regexTest") return { kind: "primitive", primitive: "boolean" };
    if (expr.kind === "numericFunction" || expr.kind === "arrayLength") return { kind: "primitive", primitive: "number" };
    if (expr.kind === "stringMethod") return { kind: "primitive", primitive: expr.method === "includes" ? "boolean" : "string" };
    if (expr.kind === "numberMethod" || expr.kind === "numberFormat") return { kind: "primitive", primitive: "string" };
    if (expr.kind === "cssModuleClass") return { kind: "primitive", primitive: "string" };
    if (expr.kind === "percentageWidth") return { kind: "primitive", primitive: "string" };
    if (expr.kind === "styleObject") return { kind: "object", fields: { width: { shape: { kind: "primitive", primitive: "string" }, optional: false } } };
    if (expr.kind === "objectLiteral") {
      const fields: Record<string, { shape: ValueShape; optional: boolean }> = {};
      for (const field of expr.fields) {
        const shape = expressionShape(field.value, scope);
        if (shape === null) return null;
        fields[field.name] = { shape, optional: false };
      }
      return { kind: "object", fields };
    }
    if (expr.kind === "arrayLiteral") {
      const shapes = expr.items.map((item) => expressionShape(item, scope)).filter((shape): shape is ValueShape => shape !== null);
      if (shapes.length !== expr.items.length) return null;
      const first = shapes[0];
      if (first === undefined) return { kind: "array", element: { kind: "primitive", primitive: "string" } };
      require_(shapes.every((shape) => JSON.stringify(shape) === JSON.stringify(first)), "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", "array literal items must have one exact structural shape");
      return { kind: "array", element: first };
    }
    if (expr.kind === "collectionFilter") {
      const source = sourceListForExpression(expr.source);
      return source === undefined ? null : { kind: "array", element: source.element.kind === "primitive" ? { kind: "primitive", primitive: source.element.primitive } : { kind: "object", fields: source.element.fields } };
    }
    if (expr.kind === "collectionMap") {
      const source = sourceListForExpression(expr.source);
      if (source === undefined) return null;
      const inner = new Map(scope);
      inner.set(expr.itemName, source);
      const element = expressionShape(expr.projection, inner);
      return element === null ? null : { kind: "array", element };
    }
    if (expr.kind === "collectionReduce" || expr.kind === "collectionMax") return { kind: "primitive", primitive: "number" };
    if (expr.kind === "collectionJoin") return { kind: "primitive", primitive: "string" };
    if (expr.kind === "objectLookup") return lookupValueShape(expr.object, scope);
    if (expr.kind === "ternary") {
      const thenShape = expressionShape(expr.then, scope);
      const elseShape = expressionShape(expr.else, scope);
      if (thenShape?.kind === "primitive" && elseShape?.kind === "primitive" && thenShape.primitive === elseShape.primitive) {
        return { kind: "primitive", primitive: thenShape.primitive, ...(thenShape.nullable || elseShape.nullable ? { nullable: true } : {}) };
      }
      return thenShape !== null && elseShape !== null && JSON.stringify(thenShape) === JSON.stringify(elseShape)
        ? thenShape
        : thenShape?.kind === "primitive" && expr.else.kind === "literal" && expr.else.literal.type === "null"
          ? { ...thenShape, nullable: true }
          : elseShape?.kind === "primitive" && expr.then.kind === "literal" && expr.then.literal.type === "null"
            ? { ...elseShape, nullable: true }
        : thenShape?.kind === "object" || thenShape?.kind === "array"
          ? thenShape
          : elseShape?.kind === "object" || elseShape?.kind === "array" ? elseShape : null;
    }
    return null;
  }

  function lookupValueShape(object: Expr, scope: Scope): ValueShape | null {
    if (object.kind === "binary" && object.operator === "??") {
      const left = lookupValueShape(object.left, scope);
      const right = lookupValueShape(object.right, scope);
      if (left !== null && right !== null && JSON.stringify(left) === JSON.stringify(right)) return left;
      return right ?? left;
    }
    if (object.kind === "objectLiteral") {
      const shapes = [
        ...object.fields.map((field) => expressionShape(field.value, scope)),
        ...(object.computedFields ?? []).map((field) => expressionShape(field.value, scope)),
      ].filter((shape): shape is ValueShape => shape !== null);
      const first = shapes[0];
      if (first === undefined || !shapes.every((shape) => JSON.stringify(shape) === JSON.stringify(first))) return null;
      return first;
    }
    const shape = expressionShape(object, scope);
    if (shape?.kind !== "object") return null;
    const fields = Object.values(shape.fields).map((field) => field.shape);
    const first = fields[0];
    return first !== undefined && fields.every((field) => JSON.stringify(field) === JSON.stringify(first)) ? first : null;
  }

  function checkNode(node: Node, scope: Scope): void {
    if (node.kind === "fragment") {
      node.children.forEach((child) => checkNode(child, scope));
      return;
    }
    if (node.kind === "text") {
      checkExpr(node.value, scope);
      const shape = expressionShape(node.value, scope);
      require_(shape === null || shape.kind === "primitive", "CERTIFIED_COMPONENT_OBJECT_ITEM_READ", "structured list or prop values must be rendered through a primitive field");
      return;
    }
    if (node.kind === "conditional") {
      checkExpr(node.condition, scope);
      checkNode(node.then, scope);
      if (node.else) checkNode(node.else, scope);
      return;
    }
    if (node.kind === "component") {
      require_(COMPONENT_NAME_RE.test(node.name), "CERTIFIED_COMPONENT_BAD_NAME", `referenced component ${JSON.stringify(node.name)} must be PascalCase`);
      require_(node.name !== component.name, "CERTIFIED_COMPONENT_SELF_REFERENCE", `${node.name} renders itself; recursive components are outside certified-component-v1 because they have no termination proof here`);
      const seen = new Set<string>();
      for (const arg of node.props) {
        checkIdentifier(arg.name, "component prop");
        require_(!seen.has(arg.name), "CERTIFIED_COMPONENT_DUPLICATE_PROP", `prop ${JSON.stringify(arg.name)} is passed twice to ${node.name}`);
        seen.add(arg.name);
        // Passing a declared structured prop through to a child preserves the
        // object contract; it is not the same as interpolating that object in
        // a text node. The child contract is checked when the repository
        // pipeline resolves the referenced component.
        if (arg.value.kind === "ident") {
          const valueName = arg.value.name;
          const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === valueName);
          if (data?.valueShape?.kind === "object" || data?.valueShape?.kind === "array" || data?.valueShape?.kind === "slot") continue;
        }
        checkExpr(arg.value, scope);
      }
      return;
    }
    if (node.kind === "list") {
      const list = listProps.get(node.source);
      require_(list !== undefined, "CERTIFIED_COMPONENT_UNKNOWN_LIST_SOURCE", `list node iterates ${JSON.stringify(node.source)}, which is not a declared list prop`);
      if (node.sourceExpression !== undefined) checkExpr(node.sourceExpression, scope);
      checkIdentifier(node.itemName, "list item variable");
      require_(!readableNames.has(node.itemName) && !callbackNames.has(node.itemName), "CERTIFIED_COMPONENT_LIST_ITEM_SHADOWS", `list item variable ${JSON.stringify(node.itemName)} shadows a declared prop or state variable`);
      // Nested lists would need a per-framework nested-key strategy and are
      // not certified; a flat list is what every target renders identically.
      require_(!scope.has(node.itemName), "CERTIFIED_COMPONENT_LIST_ITEM_SHADOWS", `list item variable ${JSON.stringify(node.itemName)} shadows an enclosing loop variable`);
      require_(scope.size === 0, "CERTIFIED_COMPONENT_NESTED_LIST", "nested list rendering is outside certified-component-v1");
      require_(node.body.kind === "element", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_BODY", "a list body must be exactly one element node");
      if (node.keyField !== undefined) {
        require_(list.element.kind === "object", "CERTIFIED_COMPONENT_UNEXPECTED_LIST_KEY", `list node ${JSON.stringify(node.source)} declares a field key but its elements are primitive`);
        require_(Object.prototype.hasOwnProperty.call(list.element.fields, node.keyField), "CERTIFIED_COMPONENT_UNKNOWN_LIST_KEY", `list node ${JSON.stringify(node.source)} key field ${JSON.stringify(node.keyField)} is not declared on its element`);
        require_(list.keyField === undefined || list.keyField === node.keyField, "CERTIFIED_COMPONENT_CONFLICTING_LIST_KEY", `list node ${JSON.stringify(node.source)} key ${JSON.stringify(node.keyField)} conflicts with its declared list key ${JSON.stringify(list.keyField)}`);
      }
      const inner = new Map(scope);
      inner.set(node.itemName, list as ListPropDef);
      checkNode(node.body, inner);
      return;
    }
    for (const attr of node.attrs) {
      if (attr.kind === "dynamic") {
        checkExpr(attr.value, scope);
        const shape = expressionShape(attr.value, scope);
        if (attr.name === "style") {
          require_(attr.value.kind === "styleObject", "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "style must use the certified percentage width object");
        } else {
          require_(shape === null || shape.kind === "primitive", "CERTIFIED_COMPONENT_OBJECT_ITEM_READ", `attribute ${JSON.stringify(attr.name)} must bind a primitive expression`);
        }
      }
    }
    for (const event of node.events) {
      event.body.forEach((s) => checkStmt(s, scope));
    }
    node.children.forEach((c) => checkNode(c, scope));
  }

  checkNode(component.root, EMPTY_SCOPE);
}
