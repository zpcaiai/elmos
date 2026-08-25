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

export type Literal =
  | { type: "string"; value: string }
  | { type: "number"; value: number }
  | { type: "boolean"; value: boolean };

export function literalType(literal: Literal): PrimitiveType {
  return literal.type;
}

/**
 * The shape of one element in a list prop.
 *
 * Two forms are certified, in increasing order of what real code needs:
 *  - a bare primitive (`string[]`), read in the body as the loop variable
 *    itself;
 *  - a FLAT object whose every field is a primitive (`{ id: number;
 *    name: string }[]`), read as `item.<field>`.
 *
 * Nested objects and arrays-of-arrays are deliberately excluded: they would
 * require an unbounded access path, and every target framework spells deep
 * access and null-safety differently.
 */
export type ListElementShape =
  | { kind: "primitive"; primitive: PrimitiveType }
  | { kind: "object"; fields: Record<string, PrimitiveType> };

/** A plain data prop, e.g. `name: string`. */
export interface DataPropDef {
  kind: "data";
  name: string;
  propType: PrimitiveType;
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
}

export type BinaryOperator = "+" | "-" | "*" | "/" | "%" | "<" | "<=" | ">" | ">=" | "==" | "!=" | "&&" | "||";
export const BINARY_OPERATORS: readonly BinaryOperator[] = ["+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||"];

export type Expr =
  | { kind: "ident"; name: string }
  /**
   * A single-level field read off a list's loop variable, e.g. `item.name`.
   * `object` must be the item variable of an enclosing `list` node and
   * `field` must be declared in that list's element shape -- both are
   * enforced by `validateComponent`. Deeper paths are not certified.
   */
  | { kind: "member"; object: string; field: string }
  | { kind: "literal"; literal: Literal }
  | { kind: "binary"; operator: BinaryOperator; left: Expr; right: Expr }
  | { kind: "unaryNot"; operand: Expr }
  | { kind: "ternary"; condition: Expr; then: Expr; else: Expr };

/** One statement inside an event handler body. Certified-component-v1 event
 * handlers are a flat list of these two statement kinds only -- no loops, no
 * conditionals inside a handler body (branch in the render tree instead),
 * no arbitrary function calls, no async. */
export type Stmt =
  | { kind: "setState"; target: string; value: Expr }
  | { kind: "callProp"; target: string; args: Expr[] };

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
  "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "strong", "em",
  "section", "article", "header", "footer", "nav", "main", "aside",
  "small", "code",
] as const;
export type HtmlTag = (typeof HTML_TAGS)[number];

export const ATTR_NAMES = [
  "class", "id", "href", "type", "placeholder", "value", "disabled", "name", "for", "checked",
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
  | { kind: "list"; source: string; itemName: string; body: Node }
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

  const stateNames = new Set<string>();
  for (const s of component.state) {
    checkIdentifier(s.name, "state name");
    require_(!stateNames.has(s.name) && !dataNames.has(s.name) && !callbackNames.has(s.name), "CERTIFIED_COMPONENT_DUPLICATE_STATE", `duplicate/shadowing state name ${JSON.stringify(s.name)}`);
    require_(literalType(s.initial) === s.stateType, "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `state ${JSON.stringify(s.name)} initial value type does not match declared type`);
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
        return;
      }
      case "member": {
        const list = scope.get(expr.object);
        require_(list !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `${expr.object}.${expr.field} is outside certified-component-v1: field access is only supported on a list's loop variable`);
        require_((list as ListPropDef).element.kind === "object", "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `loop variable ${JSON.stringify(expr.object)} has primitive elements and has no field ${JSON.stringify(expr.field)}`);
        const fields = ((list as ListPropDef).element as Extract<ListElementShape, { kind: "object" }>).fields;
        require_(Object.prototype.hasOwnProperty.call(fields, expr.field), "CERTIFIED_COMPONENT_UNKNOWN_LIST_FIELD", `${expr.object}.${expr.field} is not a declared field of list prop ${JSON.stringify(expr.object)}`);
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
      case "ternary":
        checkExpr(expr.condition, scope);
        checkExpr(expr.then, scope);
        checkExpr(expr.else, scope);
        return;
    }
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

  function checkNode(node: Node, scope: Scope): void {
    if (node.kind === "text") {
      checkExpr(node.value, scope);
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
        checkExpr(arg.value, scope);
      }
      return;
    }
    if (node.kind === "list") {
      const list = listProps.get(node.source);
      require_(list !== undefined, "CERTIFIED_COMPONENT_UNKNOWN_LIST_SOURCE", `list node iterates ${JSON.stringify(node.source)}, which is not a declared list prop`);
      checkIdentifier(node.itemName, "list item variable");
      require_(!readableNames.has(node.itemName) && !callbackNames.has(node.itemName), "CERTIFIED_COMPONENT_LIST_ITEM_SHADOWS", `list item variable ${JSON.stringify(node.itemName)} shadows a declared prop or state variable`);
      // Nested lists would need a per-framework nested-key strategy and are
      // not certified; a flat list is what every target renders identically.
      require_(!scope.has(node.itemName), "CERTIFIED_COMPONENT_LIST_ITEM_SHADOWS", `list item variable ${JSON.stringify(node.itemName)} shadows an enclosing loop variable`);
      require_(scope.size === 0, "CERTIFIED_COMPONENT_NESTED_LIST", "nested list rendering is outside certified-component-v1");
      require_(node.body.kind === "element", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_BODY", "a list body must be exactly one element node");
      const inner = new Map(scope);
      inner.set(node.itemName, list as ListPropDef);
      checkNode(node.body, inner);
      return;
    }
    for (const attr of node.attrs) {
      if (attr.kind === "dynamic") checkExpr(attr.value, scope);
    }
    for (const event of node.events) {
      event.body.forEach((s) => checkStmt(s, scope));
    }
    node.children.forEach((c) => checkNode(c, scope));
  }

  checkNode(component.root, EMPTY_SCOPE);
}
