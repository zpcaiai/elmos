/**
 * Parses one standalone Angular component (class + inline template) into
 * the certified-component-v1 canonical model.
 *
 * Two real compilers are used, one per half of the file:
 *  - the TypeScript Compiler API for the `@Component` class (`@Input`,
 *    `@Output`, plain fields);
 *  - the real `@angular/compiler` `parseTemplate` for the template.
 *
 * `@angular/compiler` publishes ESM only, which a CommonJS caller cannot
 * `require`. The template is therefore parsed in a short-lived Node
 * subprocess under native ESM -- the genuine compiler, not a substitute --
 * exactly as `validator.ts` already does for Angular syntax checking.
 *
 * Structural notes the parser has to undo from the emitter:
 *  - `*ngIf` lives on a synthetic `Template` node whose `templateAttrs`
 *    carry `ngIf` and (when present) `ngIfElse`.
 *  - The else branch is a *separate* `<ng-template #ref>` sibling, not a
 *    nested child, so it must be looked up by reference name.
 */
import { execFileSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";
import {
  at, AttrBinding, AttrName, ATTR_NAMES, CallbackPropDef, ComponentDef, DataPropDef, EventName,
  Expr, fail, HtmlTag, HTML_TAGS, ListPropDef, Literal, Node as CNode, PrimitiveType, PropDef, requireDefined,
  require_, StateDef, Stmt, validateComponent, ComponentArg } from "../models";
import { callbackNameForEvent, literalFromNode, parseHandlerStatements, parseTemplateExpression } from "./expressions";
import { inferKeyField, isArrayTypeNode, listElementFromArrayType } from "./react";

const ANGULAR_EVENT: Record<string, EventName> = {
  click: "onClick", change: "onChange", input: "onInput", submit: "onSubmit",
};

const PROPERTY_TO_ATTR: Record<string, AttrName> = { htmlFor: "for" };

/** A JSON-serializable projection of the Angular template AST. The
 * subprocess walks the real compiler's nodes and emits this; the parent
 * never sees Angular's classes, only verified shapes. */
interface NgNode {
  kind: "element" | "text" | "boundText" | "template";
  name?: string;
  value?: string;
  attributes?: { name: string; value: string }[];
  inputs?: { name: string; source: string }[];
  outputs?: { name: string; source: string }[];
  templateAttrs?: { name: string; source: string | null }[];
  references?: string[];
  /** `*ngFor="let row of rows"` binds `row` here, not in templateAttrs. */
  variables?: string[];
  children?: NgNode[];
}

const EXTRACTOR = `
import { parseTemplate } from "@angular/compiler";

function project(node) {
  const ctor = node.constructor && node.constructor.name;
  // Angular 20+ exposes the public AST class name as Text; older bundled
  // compiler builds suffix it (for example Text$3). Both are the same
  // literal-text node. No other unnamed AST node is promoted to an element.
  if (ctor === "Text" || (ctor && ctor.startsWith("Text$"))) {
    return { kind: "text", value: String(node.value) };
  }
  if (ctor === "BoundText") return { kind: "boundText", value: String(node.value.source ?? "") };
  const base = {
    name: node.name,
    attributes: (node.attributes ?? []).map((a) => ({ name: a.name, value: String(a.value) })),
    inputs: (node.inputs ?? []).map((i) => ({ name: i.name, source: String(i.value.source ?? "") })),
    outputs: (node.outputs ?? []).map((o) => ({ name: o.name, source: String(o.handler.source ?? "") })),
    references: (node.references ?? []).map((r) => r.name),
    // *ngFor's loop binding lives here (name "row", value "$implicit"),
    // NOT in templateAttrs -- reading only templateAttrs finds ngForOf but
    // never the item name.
    variables: (node.variables ?? []).map((v) => v.name),
    children: (node.children ?? []).map(project),
  };
  if (ctor === "Template") {
    return {
      kind: "template",
      ...base,
      templateAttrs: (node.templateAttrs ?? []).map((a) => ({
        name: a.name,
        source: a.value && a.value.source !== undefined ? String(a.value.source) : null,
      })),
    };
  }
  return { kind: "element", ...base };
}

const template = JSON.parse(process.argv[2]);
const result = parseTemplate(template, "component.html");
const errors = (result.errors ?? []).map(String);
process.stdout.write(JSON.stringify({ errors, nodes: result.nodes.map(project) }));
`;

function parseTemplateViaSubprocess(template: string): NgNode[] {
  const scratch = path.join(process.env["ELMOS_CDE_SCRATCH"] ?? path.join(process.cwd(), ".cde-scratch"), "angular-parse");
  fs.mkdirSync(scratch, { recursive: true });
  const scriptFile = path.join(scratch, "extract.mjs");
  fs.writeFileSync(scriptFile, EXTRACTOR, "utf8");
  let raw: string;
  try {
    raw = execFileSync(process.execPath, [scriptFile, JSON.stringify(template)], {
      encoding: "utf8", cwd: process.cwd(), stdio: ["ignore", "pipe", "pipe"], timeout: 60_000,
    });
  } catch (error) {
    const err = error as { stderr?: string; message?: string };
    fail("CERTIFIED_COMPONENT_PARSE_FAILED", `could not run @angular/compiler: ${err.stderr || err.message}`);
  }
  const parsed = JSON.parse(raw) as { errors: string[]; nodes: NgNode[] };
  require_(parsed.errors.length === 0, "CERTIFIED_COMPONENT_PARSE_FAILED", `@angular/compiler rejected the template: ${parsed.errors.join("; ")}`);
  return parsed.nodes;
}

function primitiveFromTypeNode(node: ts.TypeNode | undefined, what: string): PrimitiveType {
  const text = requireDefined(node, "CERTIFIED_COMPONENT_MISSING_TYPE", `${what} is missing an explicit type`).getText();
  if (text === "string" || text === "number" || text === "boolean") return text;
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has unsupported type ${JSON.stringify(text)}`);
}

interface ClassInfo {
  name: string;
  props: PropDef[];
  state: StateDef[];
  template: string;
  /** Emitted output name (e.g. "done") -> canonical callback ("onDone"). */
  outputs: Map<string, string>;
}

function decoratorName(decorator: ts.Decorator): string | undefined {
  const expr = decorator.expression;
  if (ts.isCallExpression(expr) && ts.isIdentifier(expr.expression)) return expr.expression.text;
  if (ts.isIdentifier(expr)) return expr.text;
  return undefined;
}

function parseComponentClass(code: string): ClassInfo {
  const file = ts.createSourceFile("component.ts", code, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TS);
  const classDecl = file.statements.find(ts.isClassDeclaration);
  const cls = requireDefined(classDecl, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "file must declare exactly one component class");
  const className = requireDefined(cls.name, "CERTIFIED_COMPONENT_MISSING_NAME", "component class must be named").text;

  const decorators = ts.getDecorators(cls) ?? [];
  const componentDecorator = requireDefined(
    decorators.find((d) => decoratorName(d) === "Component"),
    "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "class must carry an @Component decorator",
  );
  const decoratorCall = componentDecorator.expression as ts.CallExpression;
  const metadata = at(decoratorCall.arguments, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "@Component needs a metadata object");
  require_(ts.isObjectLiteralExpression(metadata), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "@Component metadata must be an object literal");

  let template: string | undefined;
  for (const field of (metadata as ts.ObjectLiteralExpression).properties) {
    if (!ts.isPropertyAssignment(field) || !ts.isIdentifier(field.name)) continue;
    const key = field.name.text;
    if (key === "template") {
      const init = field.initializer;
      require_(ts.isNoSubstitutionTemplateLiteral(init) || ts.isStringLiteral(init), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "the template must be an inline literal (templateUrl is outside certified-component-v1)");
      template = (init as ts.NoSubstitutionTemplateLiteral | ts.StringLiteral).text;
    } else if (key === "templateUrl") {
      fail("CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "templateUrl is outside certified-component-v1; the template must be inline");
    }
  }
  const inlineTemplate = requireDefined(template, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "@Component has no inline template");

  const dataProps: DataPropDef[] = [];
  const listProps: ListPropDef[] = [];
  const callbacks: CallbackPropDef[] = [];
  const state: StateDef[] = [];
  const outputs = new Map<string, string>();

  for (const member of cls.members) {
    require_(ts.isPropertyDeclaration(member) && ts.isIdentifier(member.name), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "component class members must be plain property declarations (no methods, constructors, or lifecycle hooks)");
    const name = (member.name as ts.Identifier).text;
    const memberDecorators = (ts.getDecorators(member) ?? []).map(decoratorName);

    if (memberDecorators.includes("Input")) {
      if (member.type !== undefined && isArrayTypeNode(member.type)) {
        const shape = listElementFromArrayType(member.type, `list @Input ${JSON.stringify(name)}`);
        listProps.push({ kind: "list", name, element: shape, keyField: inferKeyField(shape, `list @Input ${JSON.stringify(name)}`) });
        continue;
      }
      const propType = primitiveFromTypeNode(member.type, `@Input ${name}`);
      const defaultValue: Literal | undefined = member.initializer ? literalFromNode(member.initializer) : undefined;
      // `label!: string` is required; `label?: string` is optional.
      const required = member.exclamationToken !== undefined || (member.questionToken === undefined && defaultValue === undefined);
      dataProps.push({ kind: "data", name, propType, required: required && defaultValue === undefined, defaultValue });
      continue;
    }

    if (memberDecorators.includes("Output")) {
      const init = requireDefined(member.initializer, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", `@Output ${name} must be initialized with new EventEmitter<...>()`);
      require_(ts.isNewExpression(init) && ts.isIdentifier(init.expression) && init.expression.text === "EventEmitter", "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", `@Output ${name} must be a new EventEmitter<...>()`);
      const typeArg = (init as ts.NewExpression).typeArguments?.[0];
      const payload = typeArg && typeArg.getText() !== "void" ? primitiveFromTypeNode(typeArg, `@Output ${name} payload`) : undefined;
      const callbackName = callbackNameForEvent(name);
      outputs.set(name, callbackName);
      callbacks.push({ kind: "callback", name: callbackName, paramType: payload });
      continue;
    }

    // A plain field is component state.
    const stateType = primitiveFromTypeNode(member.type, `field ${name}`);
    const initializer = requireDefined(member.initializer, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", `field ${name} must have a literal initial value`);
    const initial = literalFromNode(initializer);
    require_(initial.type === stateType, "CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH", `field ${name} initial value does not match its declared type`);
    state.push({ name, stateType, initial });
  }

  return {
    name: className.replace(/Component$/, ""),
    props: [...dataProps, ...listProps, ...callbacks],
    state,
    template: inlineTemplate,
    outputs,
  };
}

function attrName(raw: string, what: string): AttrName {
  const canonical = PROPERTY_TO_ATTR[raw] ?? raw;
  require_((ATTR_NAMES as readonly string[]).includes(canonical), "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `${what}: attribute ${JSON.stringify(raw)} is outside certified-component-v1`);
  return canonical as AttrName;
}

interface TemplateContext {
  stateNames: ReadonlySet<string>;
  outputs: Map<string, string>;
  /** Reference name -> the <ng-template> node it labels. */
  elseTemplates: Map<string, NgNode>;
}

function collectElseTemplates(nodes: NgNode[], into: Map<string, NgNode>): void {
  for (const node of nodes) {
    if (node.kind === "template" && (node.references ?? []).length > 0) {
      for (const ref of node.references ?? []) into.set(ref, node);
    }
    collectElseTemplates(node.children ?? [], into);
  }
}

function parseNodes(nodes: NgNode[], ctx: TemplateContext): CNode[] {
  const result: CNode[] = [];
  for (const node of nodes) {
    // A referenced <ng-template> is an else branch consumed by its *ngIf.
    if (node.kind === "template" && (node.references ?? []).length > 0) continue;
    const parsed = parseNode(node, ctx);
    if (parsed !== null) result.push(parsed);
  }
  return result;
}

function parseNode(node: NgNode, ctx: TemplateContext): CNode | null {
  if (node.kind === "text") {
    const text = String(node.value ?? "").trim();
    return text.length === 0 ? null : { kind: "text", value: { kind: "literal", literal: { type: "string", value: text } } };
  }
  if (node.kind === "boundText") {
    // `{{ label }}` -- strip the interpolation braces the compiler keeps.
    const raw = String(node.value ?? "").trim().replace(/^\{\{/, "").replace(/\}\}$/, "").trim();
    return { kind: "text", value: parseTemplateExpression(raw, "interpolation") };
  }

  if (node.kind === "template") {
    const attrs = node.templateAttrs ?? [];
    const ngForOf = attrs.find((a) => a.name === "ngForOf");
    if (ngForOf !== undefined) {
      // `*ngFor="let row of rows"` desugars to `ngForOf` plus a template
      // VARIABLE holding the loop binding, so the item name comes from
      // `variables`, not from the attribute text.
      const itemVar = (node.variables ?? [])[0];
      require_(itemVar !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", "*ngFor must bind a loop variable");
      require_((node.variables ?? []).length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", "an index binding in *ngFor is outside certified-component-v1");
      const source = String(ngForOf.source ?? "").trim();
      require_(/^[A-Za-z_$][\w$]*$/.test(source), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_SOURCE", `*ngFor must iterate a declared list prop directly, got ${JSON.stringify(source)}`);
      const bodyNodes = parseNodes(node.children ?? [], ctx);
      require_(bodyNodes.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_BODY", "an *ngFor body must contain exactly one element");
      return { kind: "list", source, itemName: String(itemVar), body: at(bodyNodes, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_BODY", "empty *ngFor body") };
    }
    // Otherwise this is an *ngIf host.
    const ngIf = attrs.find((a) => a.name === "ngIf");
    require_(ngIf !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_DIRECTIVE", "only *ngIf structural directives are supported");
    const unsupported = attrs.find((a) => a.name !== "ngIf" && a.name !== "ngIfElse");
    require_(unsupported === undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_DIRECTIVE", `structural directive ${JSON.stringify(unsupported?.name)} is outside certified-component-v1`);

    const children = parseNodes(node.children ?? [], ctx);
    require_(children.length === 1, "CERTIFIED_COMPONENT_MULTI_LEVEL_CONDITIONAL", "an *ngIf branch must contain exactly one element");

    const ngIfElse = attrs.find((a) => a.name === "ngIfElse");
    let elseNode: CNode | null = null;
    if (ngIfElse?.source) {
      const ref = ngIfElse.source.trim();
      const template = requireDefined(ctx.elseTemplates.get(ref), "CERTIFIED_COMPONENT_UNSUPPORTED_DIRECTIVE", `*ngIf else references #${ref}, which is not a declared <ng-template>`);
      const elseChildren = parseNodes(template.children ?? [], ctx);
      require_(elseChildren.length === 1, "CERTIFIED_COMPONENT_MULTI_LEVEL_CONDITIONAL", "an else <ng-template> must contain exactly one element");
      elseNode = at(elseChildren, 0, "CERTIFIED_COMPONENT_MULTI_LEVEL_CONDITIONAL", "empty else branch");
    }

    return {
      kind: "conditional",
      condition: parseTemplateExpression(requireDefined(ngIf.source, "CERTIFIED_COMPONENT_UNSUPPORTED_DIRECTIVE", "*ngIf needs a condition"), "*ngIf"),
      then: at(children, 0, "CERTIFIED_COMPONENT_MULTI_LEVEL_CONDITIONAL", "empty *ngIf branch"),
      else: elseNode,
    };
  }

  const tag = String(node.name ?? "");

  // Angular has no capitalised component tags -- a child is addressed by
  // its kebab-case selector. The `app-` prefix is what this engine emits,
  // so the reverse mapping is exact rather than guessed.
  if (tag.startsWith("app-")) {
    const name = tag.slice(4).split("-").filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join("");
    const componentProps: ComponentArg[] = [];
    for (const attr of node.attributes ?? []) {
      componentProps.push({ name: attr.name, value: { kind: "literal", literal: { type: "string", value: attr.value } } });
    }
    for (const input of node.inputs ?? []) {
      componentProps.push({ name: input.name, value: parseTemplateExpression(input.source, `<${tag}> [${input.name}]`) });
    }
    require_((node.outputs ?? []).length === 0, "CERTIFIED_COMPONENT_UNSUPPORTED_EVENT", `<${tag}> binds an output; component event bindings are outside certified-component-v1`);
    return { kind: "component", name, props: componentProps };
  }

  require_((HTML_TAGS as readonly string[]).includes(tag), "CERTIFIED_COMPONENT_UNSUPPORTED_TAG", `tag ${JSON.stringify(tag)} is outside certified-component-v1`);

  const attrs: AttrBinding[] = [];
  for (const attr of node.attributes ?? []) {
    attrs.push({ kind: "static", name: attrName(attr.name, `<${tag}>`), value: attr.value });
  }
  for (const input of node.inputs ?? []) {
    attrs.push({ kind: "dynamic", name: attrName(input.name, `<${tag}>`), value: parseTemplateExpression(input.source, `<${tag}> [${input.name}]`) });
  }

  const events: { name: EventName; body: Stmt[] }[] = [];
  for (const output of node.outputs ?? []) {
    const eventName = requireDefined(ANGULAR_EVENT[output.name], "CERTIFIED_COMPONENT_UNSUPPORTED_EVENT", `<${tag}>: event ${JSON.stringify(output.name)} is outside certified-component-v1`);
    const body = parseHandlerStatements(output.source, {
      stateNames: ctx.stateNames,
      eventToCallback: (name) => ctx.outputs.get(name) ?? null,
      matchEmitCall: (call) => {
        // Angular emits with `outputName.emit(payload)`.
        if (ts.isPropertyAccessExpression(call.expression) && call.expression.name.text === "emit" && ts.isIdentifier(call.expression.expression)) {
          return { eventName: call.expression.expression.text, args: [...call.arguments] };
        }
        return null;
      },
    }, `<${tag}> (${output.name})`);
    events.push({ name: eventName, body });
  }

  return { kind: "element", tag: tag as HtmlTag, attrs, events, children: parseNodes(node.children ?? [], ctx) };
}

export function parseAngularComponent(source: string, fileName = "component.ts"): ComponentDef {
  void fileName;
  const info = parseComponentClass(source);
  const nodes = parseTemplateViaSubprocess(info.template);

  const elseTemplates = new Map<string, NgNode>();
  collectElseTemplates(nodes, elseTemplates);

  const ctx: TemplateContext = {
    stateNames: new Set(info.state.map((s) => s.name)),
    outputs: info.outputs,
    elseTemplates,
  };

  const roots = parseNodes(nodes, ctx);
  require_(roots.length === 1, "CERTIFIED_COMPONENT_MULTIPLE_ROOTS", `certified-component-v1 requires exactly one root element, found ${roots.length}`);

  const component: ComponentDef = {
    name: info.name,
    props: info.props,
    state: info.state,
    root: at(roots, 0, "CERTIFIED_COMPONENT_MULTIPLE_ROOTS", "missing root element"),
  };
  validateComponent(component);
  return component;
}
