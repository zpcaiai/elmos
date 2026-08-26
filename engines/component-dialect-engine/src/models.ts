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
  initial: Literal;
  /** True when the source state is explicitly nullable, e.g. `useState<string | null>(null)`. */
  nullable?: boolean;
}

export type BinaryOperator = "+" | "-" | "*" | "/" | "%" | "<" | "<=" | ">" | ">=" | "==" | "!=" | "&&" | "||" | "??";
export const BINARY_OPERATORS: readonly BinaryOperator[] = ["+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||", "??"];
export type StringMethod = "toUpperCase" | "toLowerCase" | "trim" | "replaceAll" | "includes" | "startsWith" | "endsWith" | "slice";
export type NumericFunction = "min" | "max" | "floor" | "ceil" | "abs";
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
    case "cssModuleClass": return false;
    case "regexTest": return usesEventValue(expr.operand);
    case "arrayLength": return usesEventValue(expr.operand);
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
  "small", "code",
] as const;
export type HtmlTag = (typeof HTML_TAGS)[number];

export const ATTR_NAMES = [
  "class", "id", "href", "type", "placeholder", "value", "disabled", "name", "for", "checked",
  "maxLength",
  "role", "aria-hidden", "aria-label", "aria-labelledby", "aria-valuemin", "aria-valuemax", "aria-valuenow", "aria-valuetext",
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
      listProps.set(prop.name, prop);
    } else {
      require_(/^on[A-Z]/.test(prop.name), "CERTIFIED_COMPONENT_BAD_CALLBACK_NAME", `callback prop ${JSON.stringify(prop.name)} must start with "on" followed by an uppercase letter`);
      callbackNames.add(prop.name);
    }
  }
  for (const list of component.lists ?? []) {
    require_(!listProps.has(list.name), "CERTIFIED_COMPONENT_DUPLICATE_LIST", `duplicate derived list source ${JSON.stringify(list.name)}`);
    listProps.set(list.name, list);
  }

  const stateNames = new Set<string>();
  for (const s of component.state) {
    checkIdentifier(s.name, "state name");
    require_(!stateNames.has(s.name) && !dataNames.has(s.name) && !callbackNames.has(s.name), "CERTIFIED_COMPONENT_DUPLICATE_STATE", `duplicate/shadowing state name ${JSON.stringify(s.name)}`);
    if (s.initial.type === "null") {
      require_(s.nullable === true, "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(s.name)} is initialized with null but is not declared nullable`);
    } else {
      require_(literalType(s.initial) === s.stateType, "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(s.name)} initial value type does not match declared type`);
    }
    stateNames.add(s.name);
  }

  const readableNames = new Set([...dataNames, ...stateNames]);

  /** Loop variables currently in scope: item name -> the list it came from. */
  type Scope = ReadonlyMap<string, ListPropDef>;
  const EMPTY_SCOPE: Scope = new Map();

  function checkExpr(expr: Expr, scope: Scope): void {
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
        require_(data?.valueShape?.kind !== "object" && data?.valueShape?.kind !== "array",
          "CERTIFIED_COMPONENT_OBJECT_PROP_READ", `structured prop ${JSON.stringify(expr.name)} must be read through a declared field or list usage, not rendered as a bare value`);
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
        require_(shape?.kind === "object", "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `${expr.object}.${expr.field} is outside certified-component-v1: field access requires a declared object prop or list item`);
        require_(Object.prototype.hasOwnProperty.call(shape.fields, expr.field), "CERTIFIED_COMPONENT_UNKNOWN_PROP_FIELD", `${expr.object}.${expr.field} is not a declared field of object prop ${JSON.stringify(expr.object)}`);
        return;
      }
      case "path": {
        const shape = resolvePathShape(expr.object, expr.fields, scope);
        require_(shape !== null, "CERTIFIED_COMPONENT_UNKNOWN_PROP_FIELD", `${expr.object}.${expr.fields.join(".")} is not a declared structured field path`);
        return;
      }
      case "literal":
        return;
      case "binary":
        checkExpr(expr.left, scope);
        checkExpr(expr.right, scope);
        return;
      case "unaryNot":
        checkExpr(expr.operand, scope);
        return;
      case "stringMethod":
        checkExpr(expr.receiver, scope);
        require_(isStringExpression(expr.receiver, scope), "CERTIFIED_COMPONENT_STRING_METHOD_RECEIVER", `${expr.method} requires a certified string expression`);
        const expectedArgs = expr.method === "replaceAll" ? 2 : expr.method === "includes" || expr.method === "startsWith" || expr.method === "endsWith" ? 1 : expr.method === "slice" ? 1 : 0;
        require_(expr.method === "slice" ? expr.args.length <= 2 && expr.args.length >= 1 : expr.args.length === expectedArgs, "CERTIFIED_COMPONENT_STRING_METHOD_ARITY", `${expr.method} expects ${expr.method === "slice" ? "one or two" : expectedArgs} argument(s)`);
        expr.args.forEach((arg) => {
          checkExpr(arg, scope);
          const expectedType = expr.method === "slice" ? "number" : "string";
          require_(arg.kind === "literal" && arg.literal.type === expectedType, "CERTIFIED_COMPONENT_STRING_METHOD_ARGUMENT", `${expr.method} arguments must be ${expectedType} literals`);
        });
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
    if (expr.kind === "ident") {
      const list = scope.get(expr.name);
      if (list !== undefined) return list.element.kind === "primitive" && list.element.primitive === "string";
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.name);
      const shape = data?.valueShape;
      if (data !== undefined) return shape === undefined ? data.propType === "string" : shape.kind === "primitive" && shape.primitive === "string";
      return component.state.some((state) => state.name === expr.name && state.stateType === "string");
    }
    if (expr.kind === "member") {
      const list = scope.get(expr.object);
      if (list?.element.kind === "object") {
        const field = list.element.fields[expr.field];
        return field?.shape.kind === "primitive" && field.shape.primitive === "string";
      }
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.object);
      const shape = data?.valueShape;
      if (shape?.kind !== "object") return false;
      const field = shape.fields[expr.field];
      return field?.shape.kind === "primitive" && field.shape.primitive === "string";
    }
    if (expr.kind === "path") {
      const shape = resolvePathShape(expr.object, expr.fields, scope);
      return shape?.kind === "primitive" && shape.primitive === "string";
    }
    if (expr.kind === "binary" && (expr.operator === "+" || expr.operator === "??")) return isStringExpression(expr.left, scope) && isStringExpression(expr.right, scope);
    if (expr.kind === "ternary") return isStringExpression(expr.then, scope) && isStringExpression(expr.else, scope);
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
      return component.state.some((state) => state.name === expr.name && state.stateType === "number");
    }
    if (expr.kind === "member") {
      const list = scope.get(expr.object);
      if (list?.element.kind === "object") {
        const field = list.element.fields[expr.field];
        return field?.shape.kind === "primitive" && field.shape.primitive === "number";
      }
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.object);
      const shape = data?.valueShape;
      if (shape?.kind !== "object") return false;
      const field = shape.fields[expr.field];
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
    if (expr.kind === "ternary") return isNumberExpression(expr.then, scope) && isNumberExpression(expr.else, scope);
    return false;
  }

  function isArrayExpression(expr: Expr, scope: Scope): boolean {
    if (expr.kind === "ident") {
      const list = scope.get(expr.name);
      if (list !== undefined) return true;
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.name);
      return data?.valueShape?.kind === "array";
    }
    if (expr.kind === "member") {
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.object);
      const shape = data?.valueShape;
      return shape?.kind === "object" && shape.fields[expr.field]?.shape.kind === "array";
    }
    if (expr.kind === "path") return resolvePathShape(expr.object, expr.fields, scope)?.kind === "array";
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
      shape = data?.valueShape;
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
    if (expr.kind === "ident") {
      const list = scope.get(expr.name);
      if (list?.element.kind === "object") return { kind: "object", fields: list.element.fields };
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.name);
      return data?.valueShape ?? null;
    }
    if (expr.kind === "member") {
      const list = scope.get(expr.object);
      if (list?.element.kind === "object") return list.element.fields[expr.field]?.shape ?? null;
      const data = component.props.find((p): p is DataPropDef => p.kind === "data" && p.name === expr.object);
      return data?.valueShape?.kind === "object" ? data.valueShape.fields[expr.field]?.shape ?? null : null;
    }
    if (expr.kind === "path") return resolvePathShape(expr.object, expr.fields, scope);
    if (expr.kind === "eventValue") return { kind: "primitive", primitive: "string" };
    if (expr.kind === "arrayLength") return { kind: "primitive", primitive: "number" };
    if (expr.kind === "stringMethod") return { kind: "primitive", primitive: expr.method === "includes" ? "boolean" : "string" };
    if (expr.kind === "cssModuleClass") return { kind: "primitive", primitive: "string" };
    if (expr.kind === "regexTest") return { kind: "primitive", primitive: "boolean" };
    if (expr.kind === "numericPredicate") return { kind: "primitive", primitive: "boolean" };
    if (expr.kind === "ternary") {
      const thenShape = expressionShape(expr.then, scope);
      const elseShape = expressionShape(expr.else, scope);
      return thenShape?.kind === "object" || thenShape?.kind === "array"
        ? thenShape
        : elseShape?.kind === "object" || elseShape?.kind === "array" ? elseShape : null;
    }
    return null;
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
        require_(shape === null || shape.kind === "primitive", "CERTIFIED_COMPONENT_OBJECT_ITEM_READ", `attribute ${JSON.stringify(attr.name)} must bind a primitive expression`);
      }
    }
    for (const event of node.events) {
      event.body.forEach((s) => checkStmt(s, scope));
    }
    node.children.forEach((c) => checkNode(c, scope));
  }

  checkNode(component.root, EMPTY_SCOPE);
}
